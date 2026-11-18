"""웹 앱 안의 사용 가이드 사본(web/content, web/public/guide/img)이 원본(docs/)과 같은지 확인한다.

원본을 고치고 scripts/sync_guide.sh 를 돌리지 않으면 이 테스트가 실패한다.
"""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "sync_guide.sh"


@pytest.mark.skipif(not SCRIPT.exists(), reason="저장소 전체가 아닌 곳(예: api 이미지 안)에서는 건너뜀")
def test_guide_copies_match_docs():
    r = subprocess.run(["bash", str(SCRIPT), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, f"가이드 사본이 docs/ 와 다릅니다. scripts/sync_guide.sh 를 실행하세요.\n{r.stderr}"
