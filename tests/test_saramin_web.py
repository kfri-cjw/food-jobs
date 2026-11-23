"""사람인 검색 화면 대체 수집기 + 회사 규모 붙이기 (가짜 HTML로만 검사, 네트워크 없음)."""
import json
from datetime import date
from pathlib import Path

import pytest

from collector import classify as C
from collector import company as CO
from collector import config
from collector import main as M
from collector.http import SourceError
from collector.sources import saramin_web as W

FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 11, 19)


class Resp:
    def __init__(self, text):
        self.text = text


def fake_web_get(calls):
    def _get(url, params, **kw):
        calls.append((url, dict(params)))
        if "search/recruit" in url:
            page = params.get("recruitPage", 1)
            return Resp((FIX / "saramin_web_search.html").read_text(encoding="utf-8") if page == 1 else "<html></html>")
        if "view-detail" in url:
            return Resp((FIX / "saramin_web_detail.html").read_text(encoding="utf-8"))
        if "relay/view" in url:
            return Resp('<meta name="description" content="예시, 경력:경력3년↑, 회사내규에 따름, 마감일:채용시">')
        if "company-info" in url:
            return Resp((FIX / "saramin_web_company.html").read_text(encoding="utf-8"))
        raise AssertionError(url)
    return _get


@pytest.fixture
def web(monkeypatch):
    calls = []
    g = fake_web_get(calls)
    monkeypatch.setattr(W, "get", g)
    monkeypatch.setattr(CO, "get", g)
    monkeypatch.setattr(W, "sleep", lambda s: None)
    monkeypatch.setattr(CO, "sleep", lambda s: None)
    monkeypatch.setattr(config, "SARAMIN_WEB_KEYWORDS", ["식품연구", "HACCP"])
    monkeypatch.setattr(C, "today_kst", lambda: TODAY)
    return calls


def test_parse_list_fields():
    rows = W.parse_list((FIX / "saramin_web_search.html").read_text(encoding="utf-8"))
    assert [r["rec_idx"] for r in rows] == ["90000001", "90000002", "90000003", "90000004", "90000005"]
    r = rows[0]
    assert r["title"] == "식품 연구개발(R&D) 신입 채용" and r["org"] == "(주)예시푸드" and r["csn"] == "CSN_A"
    assert r["location"] == "충북 청주시" and r["career"] == "신입" and r["edu"] == "대졸↑"
    assert r["emp"] == "정규직" and r["pay"] == "3,400 만원" and r["deadline_text"] == "~ 12/20(일)"


def test_to_job_filters_and_normalizes():
    rows = {r["rec_idx"]: r for r in W.parse_list((FIX / "saramin_web_search.html").read_text(encoding="utf-8"))}
    j = W.to_job(rows["90000001"], TODAY)
    assert j["id"] == "saramin:90000001" and j["regions"] == ["충북"] and j["career"] == "신입"
    assert j["edu"] == "대졸(4년) 이상" and j["deadline"] == "2026-12-20" and j["posted"] == "2026-11-18"
    assert j["salary"] == {"kind": "posting", "text": "연봉 3,400만원"} and j["jobs"][0] == "R&D·제품개발"
    assert j["url"].endswith("rec_idx=90000001")
    j = W.to_job(rows["90000002"], TODAY)
    assert j["deadline"] is None and j["deadline_note"] == "채용시까지" and "계약직" in j["emp"]
    assert W.to_job(rows["90000003"], TODAY) is None   # 헤드헌팅
    assert W.to_job(rows["90000004"], TODAY) is None   # 상하차·아르바이트
    assert W.to_job(rows["90000005"], TODAY) is None   # 식품 무관


def test_deadline_year_rollover_and_pay_units():
    assert W._deadline("~ 01/05(화)", date(2026, 12, 28)) == ("2027-01-05", None)
    assert W._deadline("~ 12/20(일)", date(2026, 12, 28)) == ("2026-12-20", None)  # 막 지난 마감은 올해로 둠
    assert W._deadline("오늘마감", TODAY) == ("2026-11-19", None)
    assert W.pay_from_list("240 만원") == "월급 240만원"
    assert W.pay_from_list("10,320 원") == "시급 10,320원"


def test_parse_detail():
    d = W.parse_detail((FIX / "saramin_web_detail.html").read_text(encoding="utf-8"))
    assert d["salary_text"] == "연봉 3,400~3,800만원"
    assert d["address"] == "충북 청주시 흥덕구 예시로 12"
    assert d["headcount"] == 2
    q = d["quals"]
    assert q["certs"] == ["식품기사", "HACCP 교육"] and q["langs"] == ["TOEIC 700"]
    assert q["text"].startswith("• 식품공학") and "우대" not in q["text"] and "HACCP" in q["pref"]
    assert W.parse_detail("<html><img src=x></html>") == {}   # 이미지뿐인 공고


def test_parse_company_and_revenue():
    info = CO.parse_company((FIX / "saramin_web_company.html").read_text(encoding="utf-8"))
    assert info == {"founded": 2014, "type": "중소기업", "employees": 1240, "employees_src": "국민연금",
                    "revenue": "1조 2,345억 600만원", "revenue_eok": 12345.06, "industry": "기타 식품 제조업"}
    assert CO.revenue_eok("157억 684만원") == 157.07 and CO.revenue_eok("-") is None
    assert CO.size_band(info) == "1,000명 이상" and CO.size_band(None) == "정보 없음"


def test_collect_web_mode(web, tmp_path):
    out = tmp_path / "jobs.json"
    data = M.collect(out, {"SARAMIN_WEB": "1"})
    st = data["sources"]["saramin"]
    assert st["state"] == "ok" and st["mode"] == "web" and st["count"] == 2
    assert data["sources"]["alio"]["state"] == "no_key"
    j = next(x for x in data["jobs"] if x["id"] == "saramin:90000001")
    assert j["salary"]["text"] == "연봉 3,400~3,800만원"          # 상세 본문 값이 목록 추정값보다 우선
    assert j["address"].startswith("충북 청주시") and j["quals"]["certs"][0] == "식품기사"
    assert j["detail_checked"] == "2026-11-19"
    assert j["company"]["employees"] == 1240 and j["company"]["type"] == "중소기업"
    assert data["company"]["fetched"] == 2 and (tmp_path / "companies.json").exists()
    # 같은 회사·공고는 다음 실행에서 다시 받지 않음
    web.clear()
    data2 = M.collect(out, {"SARAMIN_WEB": "1"})
    assert not [c for c in web if "view-detail" in c[0] or "company-info" in c[0]]
    j2 = next(x for x in data2["jobs"] if x["id"] == "saramin:90000001")
    assert j2["quals"] == j["quals"] and j2["company"] == j["company"] and j2["first_seen"] == j["first_seen"]


def test_detail_budget_and_key_wins(web, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SARAMIN_WEB_DETAIL_MAX", 1)
    data = M.collect(tmp_path / "jobs.json", {"SARAMIN_WEB": "1"})
    assert sum(1 for j in data["jobs"] if j.get("detail_checked")) == 1
    # 키가 있으면 웹이 아니라 API 모듈을 씀
    from collector.sources import saramin
    monkeypatch.setattr(saramin, "fetch", lambda key: [])
    data = M.collect(tmp_path / "jobs2.json", {"SARAMIN_KEY": "K", "SARAMIN_WEB": "1"})
    assert data["sources"]["saramin"]["mode"] == "api"
    assert not any("search/recruit" in c[0] for c in web[-3:])


def test_web_off_by_default_and_zero_results_keeps_old(web, tmp_path, monkeypatch):
    out = tmp_path / "jobs.json"
    assert M.collect(out, {})["sources"]["saramin"]["state"] == "no_key"
    first = M.collect(out, {"SARAMIN_WEB": "1"})
    monkeypatch.setattr(W, "get", lambda *a, **k: Resp("<html>바뀐 화면</html>"))
    second = M.collect(out, {"SARAMIN_WEB": "1"})
    st = second["sources"]["saramin"]
    assert st["state"] == "error" and "0건" in st["message"]
    assert {j["id"] for j in second["jobs"]} == {j["id"] for j in first["jobs"]}


def test_public_jobs_get_no_company(tmp_path):
    jobs = [{"id": "a", "csn": "X", "org_type": "공기업·공공기관"}]
    st = CO.attach(jobs, TODAY, fetch_new=True, path=tmp_path / "c.json")
    assert st["fetched"] == 0 and "company" not in jobs[0]


def test_meta_salary_only_for_image_postings(web, tmp_path, monkeypatch):
    base = W.get

    def image_detail(url, params, **kw):
        if "view-detail" in url:
            web.append((url, dict(params)))
            return Resp("<html><img src='poster.png'></html>")
        return base(url, params, **kw)
    monkeypatch.setattr(W, "get", image_detail)
    data = M.collect(tmp_path / "jobs.json", {"SARAMIN_WEB": "1"})
    j = next(x for x in data["jobs"] if x["id"] == "saramin:90000002")   # 목록에 급여 없음 + 이미지 공고
    assert j["salary"] is None and j["salary_note"] == "회사내규에 따름" and "quals" not in j
    assert sum(1 for c in web if "relay/view" in c[0] and "detail" not in c[0]) == 1  # 급여 있는 공고는 안 받음
    assert j["career_text"] == "경력3년↑" and j["career"] == "경력"
