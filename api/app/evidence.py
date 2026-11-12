"""M6 증적 저장소: append-only + SHA-256 해시 체인.

- 기본 백엔드: 로컬 파일시스템. 객체와 원장(ledger) 항목을 각각 1회만 쓰고(O_EXCL) 읽기 전용(0444)으로 바꾼다.
  수정·삭제 API는 제공하지 않는다.
- 체인: chain_hash = SHA256(prev_hash + canonical_json(entry))  (entry 에 객체 sha256 포함)
- verify: 객체 해시 재계산 + 체인 재계산 + DB 색인과 대조.
- 운영 환경에서는 WORM 스토리지(S3 Object Lock 호환)를 써야 한다. S3 백엔드는 인터페이스만 있는 스텁이다.
주의: 파일 권한은 OS 관리자(root)를 막지 못한다. 변조 '방지'가 아니라 '탐지'를 목표로 한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import EvidenceItem

GENESIS = "0" * 64


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(entry: dict[str, Any]) -> bytes:
    return json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def chain_hash(prev_hash: str, entry: dict[str, Any]) -> str:
    return sha256_hex(prev_hash.encode("ascii") + canonical(entry))


def add_years(dt: datetime, years: int) -> datetime:
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:  # 2월 29일
        return dt.replace(year=dt.year + years, day=28)


class WriteOnceViolation(RuntimeError):
    pass


class EvidenceBackend(Protocol):
    name: str

    def put_object(self, customer_id: int, sha256: str, data: bytes) -> None: ...
    def get_object(self, customer_id: int, sha256: str) -> bytes: ...
    def put_ledger(self, customer_id: int, seq: int, entry: dict[str, Any]) -> None: ...
    def list_ledger(self, customer_id: int) -> list[dict[str, Any]]: ...


class FilesystemBackend:
    name = "filesystem"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _dir(self, customer_id: int, sub: str) -> Path:
        d = self.root / f"customer-{int(customer_id)}" / sub
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def _write_once(path: Path, data: bytes) -> None:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        except FileExistsError as e:
            raise WriteOnceViolation(f"이미 존재하는 증적은 덮어쓸 수 없습니다: {path.name}") from e
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chmod(path, 0o444)

    def put_object(self, customer_id: int, sha256: str, data: bytes) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("잘못된 해시")
        path = self._dir(customer_id, "objects") / sha256
        if path.exists():
            if sha256_hex(path.read_bytes()) == sha256:
                return  # 동일 내용(내용 주소 지정) — 재기록 불필요
            raise WriteOnceViolation("같은 해시 이름의 객체가 다른 내용으로 존재합니다(변조 의심)")
        self._write_once(path, data)

    def get_object(self, customer_id: int, sha256: str) -> bytes:
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("잘못된 해시")
        return (self._dir(customer_id, "objects") / sha256).read_bytes()

    def put_ledger(self, customer_id: int, seq: int, entry: dict[str, Any]) -> None:
        self._write_once(self._dir(customer_id, "ledger") / f"{int(seq):08d}.json", canonical(entry))

    def list_ledger(self, customer_id: int) -> list[dict[str, Any]]:
        d = self._dir(customer_id, "ledger")
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))]


class S3ObjectLockBackend:
    """S3 Object Lock(Compliance 모드) 백엔드 스텁 — 미구현.

    운영 시 DCP 국내 데이터센터의 S3 호환 스토리지(Object Lock 지원)에 연결하도록 같은 인터페이스로 구현한다.
    put_object/put_ledger 는 ObjectLockMode=COMPLIANCE, RetainUntilDate=retention_until 로 올려야 한다.
    """

    name = "s3"

    def __init__(self, *args: Any, **kwargs: Any):
        raise NotImplementedError("S3 Object Lock 백엔드는 이 데모에서 구현되지 않았습니다(EVIDENCE_BACKEND=filesystem 사용)")


def get_backend() -> EvidenceBackend:
    s = get_settings()
    if s.evidence_backend == "s3":
        return S3ObjectLockBackend()
    return FilesystemBackend(s.evidence_dir)


class EvidenceStore:
    """증적 추가(append)와 검증만 제공한다. 수정·삭제 메서드는 의도적으로 없다."""

    def __init__(self, backend: EvidenceBackend | None = None):
        self.backend = backend or get_backend()

    def append(self, db: Session, customer_id: int, *, kind: str, title: str, data: bytes | str,
               content_type: str = "application/octet-stream", meta: dict[str, Any] | None = None,
               created_by: str = "system") -> EvidenceItem:
        if isinstance(data, str):
            data = data.encode("utf-8")
        last = db.scalars(select(EvidenceItem).where(EvidenceItem.customer_id == customer_id)
                          .order_by(EvidenceItem.seq.desc()).limit(1)).first()
        seq = (last.seq + 1) if last else 1
        prev = last.chain_hash if last else GENESIS
        now = datetime.now(timezone.utc).replace(microsecond=0)
        retention = add_years(now, get_settings().retention_years)
        digest = sha256_hex(data)
        entry = {
            "seq": seq, "customer_id": customer_id, "kind": kind, "title": title, "content_type": content_type,
            "size": len(data), "sha256": digest, "prev_hash": prev, "created_at": now.isoformat(),
            "retention_until": retention.isoformat(), "created_by": created_by, "meta": meta or {},
        }
        ch = chain_hash(prev, entry)
        self.backend.put_object(customer_id, digest, data)
        self.backend.put_ledger(customer_id, seq, {**entry, "chain_hash": ch})
        item = EvidenceItem(customer_id=customer_id, seq=seq, kind=kind, title=title, content_type=content_type,
                            size=len(data), sha256=digest, prev_hash=prev, chain_hash=ch, retention_until=retention,
                            meta=meta or {}, created_by=created_by, created_at=now)
        db.add(item)
        db.flush()
        return item

    def read(self, customer_id: int, sha256: str) -> bytes:
        return self.backend.get_object(customer_id, sha256)

    def verify(self, db: Session, customer_id: int) -> dict[str, Any]:
        problems: list[dict[str, Any]] = []
        ledger = self.backend.list_ledger(customer_id)
        rows = db.scalars(select(EvidenceItem).where(EvidenceItem.customer_id == customer_id)
                          .order_by(EvidenceItem.seq)).all()
        prev = GENESIS
        for i, e in enumerate(ledger, 1):
            entry = {k: v for k, v in e.items() if k != "chain_hash"}
            seq = e.get("seq")
            if seq != i:
                problems.append({"seq": seq, "problem": f"원장 순번 불연속(기대 {i})"})
            if e.get("prev_hash") != prev:
                problems.append({"seq": seq, "problem": "prev_hash 불일치(체인 끊김)"})
            if chain_hash(e.get("prev_hash", ""), entry) != e.get("chain_hash"):
                problems.append({"seq": seq, "problem": "chain_hash 재계산 불일치(원장 변조 의심)"})
            try:
                data = self.backend.get_object(customer_id, e["sha256"])
                if sha256_hex(data) != e["sha256"]:
                    problems.append({"seq": seq, "problem": "객체 해시 불일치(파일 변조 의심)"})
                elif len(data) != e.get("size"):
                    problems.append({"seq": seq, "problem": "객체 크기 불일치"})
            except FileNotFoundError:
                problems.append({"seq": seq, "problem": "객체 파일 없음(삭제 의심)"})
            prev = e.get("chain_hash", "")
        by_seq = {e.get("seq"): e for e in ledger}
        for r in rows:
            e = by_seq.get(r.seq)
            if e is None:
                problems.append({"seq": r.seq, "problem": "DB 색인에는 있으나 원장에 없음(삭제 의심)"})
            elif e.get("chain_hash") != r.chain_hash or e.get("sha256") != r.sha256:
                problems.append({"seq": r.seq, "problem": "DB 색인과 원장의 해시 불일치"})
        if len(ledger) > len(rows):
            problems.append({"seq": None, "problem": "원장 항목이 DB 색인보다 많음"})
        return {"customer_id": customer_id, "ok": not problems, "count": len(ledger),
                "head_hash": prev if ledger else GENESIS, "problems": problems,
                "backend": self.backend.name, "verified_at": datetime.now(timezone.utc).isoformat()}


def evidence_count(db: Session, customer_id: int | None = None) -> int:
    q = select(func.count(EvidenceItem.id))
    if customer_id is not None:
        q = q.where(EvidenceItem.customer_id == customer_id)
    return int(db.scalar(q) or 0)
