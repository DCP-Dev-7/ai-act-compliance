import json
import os
import stat
from datetime import timezone

import pytest

from app.evidence import GENESIS, EvidenceStore, FilesystemBackend, S3ObjectLockBackend, WriteOnceViolation
from app.models import Customer


@pytest.fixture()
def store(env):
    return EvidenceStore(FilesystemBackend(env / "evidence"))


def cid(db):
    return db.query(Customer).first().id


def add3(db, store):
    c = cid(db)
    items = [store.append(db, c, kind="test", title=f"증적 {i}", data=f"내용 {i}", created_by="t") for i in range(3)]
    db.commit()
    return c, items


def test_hash_chain_links_and_verify_ok(db, store):
    c, items = add3(db, store)
    assert items[0].prev_hash == GENESIS and items[0].seq == 1
    assert items[1].prev_hash == items[0].chain_hash and items[2].prev_hash == items[1].chain_hash
    assert len({i.sha256 for i in items}) == 3
    r = store.verify(db, c)
    assert r["ok"] and r["count"] == 3 and r["head_hash"] == items[2].chain_hash


def test_retention_is_five_years(db, store):
    c, items = add3(db, store)
    it = items[0]
    created, until = it.created_at, it.retention_until
    assert until.year - created.year == 5 and (until.month, until.day) == (created.month, created.day)
    entry = store.backend.list_ledger(c)[0]
    assert entry["retention_until"].startswith(str(created.year + 5))


def test_files_are_read_only_and_write_once(db, store, env):
    c, items = add3(db, store)
    obj = env / "evidence" / f"customer-{c}" / "objects" / items[0].sha256
    led = env / "evidence" / f"customer-{c}" / "ledger" / "00000001.json"
    for p in (obj, led):
        assert stat.S_IMODE(p.stat().st_mode) == 0o444
    with pytest.raises(WriteOnceViolation):
        store.backend.put_ledger(c, 1, {"x": 1})
    assert json.loads(led.read_text())["seq"] == 1  # 원본 유지


def test_no_update_or_delete_api():
    for name in dir(EvidenceStore) + dir(FilesystemBackend):
        assert not any(w in name.lower() for w in ("delete", "remove", "update", "overwrite")), name


def test_tampered_object_detected(db, store, env):
    c, items = add3(db, store)
    obj = env / "evidence" / f"customer-{c}" / "objects" / items[1].sha256
    os.chmod(obj, 0o644)
    obj.write_text("변조된 내용")
    r = store.verify(db, c)
    assert not r["ok"] and any(p["seq"] == 2 and "객체 해시 불일치" in p["problem"] for p in r["problems"])


def test_tampered_ledger_detected(db, store, env):
    c, _ = add3(db, store)
    led = env / "evidence" / f"customer-{c}" / "ledger" / "00000002.json"
    e = json.loads(led.read_text())
    e["title"] = "바꿔치기"
    os.chmod(led, 0o644)
    led.write_text(json.dumps(e, ensure_ascii=False))
    r = store.verify(db, c)
    assert not r["ok"] and any("chain_hash" in p["problem"] for p in r["problems"])


def test_consistently_rewritten_ledger_detected_by_db_index(db, store, env):
    """공격자가 원장 항목과 chain_hash 를 일관되게 다시 계산해도 DB 색인과 달라 탐지된다."""
    from app.evidence import canonical, chain_hash

    c, _ = add3(db, store)
    led = env / "evidence" / f"customer-{c}" / "ledger" / "00000003.json"
    e = json.loads(led.read_text())
    e["title"] = "조작"
    body = {k: v for k, v in e.items() if k != "chain_hash"}
    e["chain_hash"] = chain_hash(e["prev_hash"], body)
    os.chmod(led, 0o644)
    led.write_bytes(canonical(e))
    r = store.verify(db, c)
    assert not r["ok"] and any("DB 색인" in p["problem"] for p in r["problems"])


def test_deleted_object_and_ledger_detected(db, store, env):
    c, items = add3(db, store)
    (env / "evidence" / f"customer-{c}" / "objects" / items[0].sha256).unlink()
    r = store.verify(db, c)
    assert any("객체 파일 없음" in p["problem"] for p in r["problems"])
    (env / "evidence" / f"customer-{c}" / "ledger" / "00000003.json").unlink()
    r = store.verify(db, c)
    assert any("원장에 없음" in p["problem"] for p in r["problems"])


def test_same_content_twice_is_two_ledger_entries(db, store):
    c = cid(db)
    a = store.append(db, c, kind="t", title="a", data=b"same")
    b = store.append(db, c, kind="t", title="b", data=b"same")
    db.commit()
    assert a.sha256 == b.sha256 and a.chain_hash != b.chain_hash and store.verify(db, c)["ok"]


def test_empty_chain_ok(db, store):
    r = store.verify(db, cid(db))
    assert r["ok"] and r["count"] == 0


def test_s3_backend_is_stub():
    with pytest.raises(NotImplementedError):
        S3ObjectLockBackend()
