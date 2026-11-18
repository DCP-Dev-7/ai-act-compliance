#!/usr/bin/env bash
# 사용 가이드를 웹 앱 안으로 복사한다. 원본은 항상 docs/ 쪽이다.
#   docs/USER_GUIDE.md  → web/content/USER_GUIDE.md   (화면 /guide 가 읽는 파일)
#   docs/guide/img/*    → web/public/guide/img/*      (가이드 캡처)
# 웹 Docker 빌드 컨텍스트가 ./web 이라 ../docs 를 빌드 때 읽을 수 없어서 사본을 커밋해 둔다.
#   scripts/sync_guide.sh           복사(가이드를 고친 뒤 실행하고 사본도 함께 커밋)
#   scripts/sync_guide.sh --check   사본이 원본과 같은지만 확인. 다르면 종료 코드 1
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_MD="$ROOT/docs/USER_GUIDE.md"
SRC_IMG="$ROOT/docs/guide/img"
DST_MD="$ROOT/web/content/USER_GUIDE.md"
DST_IMG="$ROOT/web/public/guide/img"

[ -f "$SRC_MD" ] || { echo "원본이 없습니다: $SRC_MD" >&2; exit 2; }
[ -d "$SRC_IMG" ] || { echo "원본이 없습니다: $SRC_IMG" >&2; exit 2; }

case "${1:-}" in
  --check)
    fail=0
    if ! cmp -s "$SRC_MD" "$DST_MD"; then
      echo "다름: web/content/USER_GUIDE.md ≠ docs/USER_GUIDE.md" >&2; fail=1
    fi
    if [ ! -d "$DST_IMG" ]; then
      echo "없음: web/public/guide/img" >&2; fail=1
    elif ! out="$(diff -rq "$SRC_IMG" "$DST_IMG" 2>&1)"; then
      echo "다름: web/public/guide/img ≠ docs/guide/img" >&2; echo "$out" >&2; fail=1
    fi
    if [ "$fail" -ne 0 ]; then
      echo "가이드 사본이 원본(docs/)과 다릅니다. docs/ 쪽을 고친 뒤 scripts/sync_guide.sh 를 실행하세요." >&2
      exit 1
    fi
    echo "가이드 사본이 원본과 같습니다 (USER_GUIDE.md + 이미지 $(find "$SRC_IMG" -type f | wc -l | tr -d ' ')개)"
    ;;
  "")
    mkdir -p "$(dirname "$DST_MD")" "$DST_IMG"
    cp "$SRC_MD" "$DST_MD"
    # 원본에서 지운 이미지는 사본에서도 지운다
    find "$DST_IMG" -mindepth 1 -delete
    cp -R "$SRC_IMG"/. "$DST_IMG"/
    echo "복사 완료: web/content/USER_GUIDE.md, web/public/guide/img ($(find "$DST_IMG" -type f | wc -l | tr -d ' ')개)"
    ;;
  *)
    echo "사용법: scripts/sync_guide.sh [--check]" >&2; exit 2
    ;;
esac
