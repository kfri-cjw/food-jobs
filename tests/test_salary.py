import json
from datetime import date
from pathlib import Path

from collector import salary as S

FIX = Path(__file__).parent / "fixtures" / "alio_salary.json"


def table():
    rows = json.loads(FIX.read_text(encoding="utf-8"))["data"]["result"]
    return {"updated": "2026-11-19", "items": S.parse_alio_rows(rows, 2026)}


def test_parse_years_and_skip_zero():
    items = table()["items"]
    assert items["(재)축산환경관리원"]["by_year"]["2026"] == 39621
    assert items["(재)축산환경관리원"]["by_year"]["2025"] == 38369
    assert "(재)한국통계정보원" not in items  # 0만 있으면 제외


def test_attach_public_start():
    jobs = [
        {"source": "alio", "org": "(재)축산환경관리원", "emp": ["계약직"]},
        {"source": "alio", "org": "한국농수산식품유통공사", "emp": ["정규직"]},
        {"source": "alio", "org": "없는기관", "emp": ["정규직"]},
        {"source": "work24", "org": "가나다식품", "emp": ["정규직"], "salary": {"kind": "posting", "text": "연봉 3200만원"}},
    ]
    n = S.attach(jobs, table(), date(2026, 11, 19))
    assert n == 3
    a, b, c, d = jobs
    # 작년(2025) 값을 우선 사용, 천원 → 만원
    assert a["salary"] == {"kind": "public_start", "amount": 3837, "year": 2025, "regular": False}
    assert b["salary"]["amount"] == 3902 and b["salary"]["regular"] is True
    assert "salary" not in c
    assert d["salary"]["kind"] == "posting"


def test_org_name_normalization():
    assert S.norm_org("(재)축산환경관리원") == S.norm_org("축산환경관리원")
    assert S.norm_org("한국서부발전(주)") == S.norm_org("한국서부발전")


def test_posting_salary():
    assert S.posting_salary("연봉 3200만원 ~ 3600만원") == {"kind": "posting", "text": "연봉 3200만원 ~ 3600만원"}
    assert S.posting_salary("면접후 결정") is None
    assert S.posting_salary("회사내규에 따름") is None
    assert S.posting_salary("") is None


def test_refresh_keeps_old_on_failure(tmp_path):
    p = tmp_path / "salary_public.json"
    st = S.refresh_public(date(2026, 11, 19), p, fetch=lambda y: table()["items"] | {f"기관{i}": {"type": "", "by_year": {"2025": 1}} for i in range(60)})
    assert st["state"] == "ok" and p.exists()
    # 7일 안에는 다시 받지 않음
    assert S.refresh_public(date(2026, 11, 20), p, fetch=lambda y: 1 / 0)["state"] == "cached"
    # 오래됐는데 실패하면 예전 표 유지
    st = S.refresh_public(date(2026, 12, 30), p, fetch=lambda y: 1 / 0)
    assert st["state"] == "error" and st["count"] > 0
    assert json.loads(p.read_text(encoding="utf-8"))["updated"] == "2026-11-19"
