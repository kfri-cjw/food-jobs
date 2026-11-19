"""예시 데이터(docs/data/sample.json) 만들기 — 인증키 없이 화면을 미리 볼 때 사용.
python -m tests.make_sample
"""
from pathlib import Path

from collector import main as M
from tests.fake_api import FAKE_ENV, patch_all

if __name__ == "__main__":
    patch_all()
    out = Path(__file__).resolve().parent.parent / "docs" / "data" / "sample.json"
    if out.exists():
        out.unlink()
    # 예시 기관용 가짜 신입 초임 표 (실제 기관 아님)
    data = M.collect(out, FAKE_ENV, salary_path=Path(__file__).resolve().parent / "fixtures" / "salary_sample.json")
    print(f"예시 {data['total']}건 → {out}")
