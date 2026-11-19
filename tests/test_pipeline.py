import json
from datetime import date

import pytest

from collector import classify as C
from collector import main as M
from tests.fake_api import FAKE_ENV, patch_all


@pytest.fixture
def run(tmp_path, monkeypatch):
    patch_all(monkeypatch)
    monkeypatch.setattr(C, "today_kst", lambda: date(2026, 11, 19))
    out = tmp_path / "jobs.json"

    def _run(env=FAKE_ENV):
        return M.collect(out, env)
    return _run, out


def by_title(data, part):
    hits = [j for j in data["jobs"] if part in j["title"]]
    assert hits, part
    return hits[0]


def test_collect_filters_and_classifies(run):
    _run, out = run
    data = _run()
    titles = [j["title"] for j in data["jobs"]]
    # 비식품 공공기관 공고, 배송기사, 아르바이트, 마감 지난 공고는 빠짐
    assert not any("한국전력" in j["org"] for j in data["jobs"])
    assert not any("배송" in t for t in titles)
    assert not any("아르바이트" in t for t in titles)
    assert not any("마감" in t and "분석" in t for t in titles)

    r = by_title(data, "연구직(식품가공")
    assert r["org_type"] == "정부출연·연구기관" and r["jobs"][0] == "R&D·제품개발"
    assert r["url"] == "https://job.alio.go.kr/recruitview.do?idx=290001"
    assert r["quals"]["certs"] == ["식품기사"] and r["quals"]["langs"] == ["TOEIC 800"]
    assert r["headcount"] == 2

    r = by_title(data, "영양사(기간제)")
    assert "계약직" in r["emp"] and r["jobs"] == ["영양사·급식·조리"]

    r = by_title(data, "요양원 영양사")
    assert r["org_type"] == "병원·학교·복지기관" and r["deadline_note"] == "채용시까지"
    assert r["regions"] == ["전북"]

    r = by_title(data, "Regulatory Affairs")
    assert r["org_type"] == "외국계" and "인허가·RA" in r["jobs"]

    r = by_title(data, "위탁급식 영양사")
    assert r["deadline"] is None and r["deadline_note"] == "채용시까지"

    r = by_title(data, "R&D/품질")  # HTML 엔티티 복원
    assert r["regions"] == ["서울", "충북"] and r["career"] == "신입"


def test_dedupe_and_cotp_hint(run):
    _run, _ = run
    data = _run()
    same = [j for j in data["jobs"] if "면·소스" in j["title"]]
    assert len(same) == 1  # 고용24·사람인 중복 → 하나
    assert same[0]["source"] == "work24"
    assert same[0]["also"][0]["source"] == "saramin"
    assert same[0]["org_type"] == "대기업·주요 식품기업"  # coTp=01 태깅


def test_first_seen_persists_and_failure_keeps_old(run, monkeypatch):
    _run, out = run
    first = _run()
    ids = {j["id"]: j["first_seen"] for j in first["jobs"]}
    assert set(ids.values()) == {"2026-11-19"}
    assert first["new_today"] == first["total"]

    # 다음 날: first_seen 유지
    monkeypatch.setattr(C, "today_kst", lambda: date(2026, 11, 20))
    from collector.sources import saramin

    def boom(*a, **k):
        from collector.http import SourceError
        raise SourceError("https://oapi.saramin.co.kr/job-search?access-key=SRKEY 요청 실패: HTTP 500")
    monkeypatch.setattr(saramin, "get", boom)
    second = M.collect(out, FAKE_ENV)
    assert second["sources"]["saramin"]["state"] == "error"
    assert "SRKEY" not in json.dumps(second, ensure_ascii=False)  # 키 노출 금지
    assert any(j["source"] == "saramin" for j in second["jobs"])  # 이전 데이터 유지
    for j in second["jobs"]:
        if j["id"] in ids:
            assert j["first_seen"] == ids[j["id"]]
    # 11/20에는 11/21 마감 공고가 아직 남아 있어야 함
    assert any("청년인턴" in j["title"] for j in second["jobs"])


def test_no_keys(run):
    _run, out = run
    data = _run({})
    assert data["total"] == 0
    assert all(s["state"] == "no_key" for s in data["sources"].values())
