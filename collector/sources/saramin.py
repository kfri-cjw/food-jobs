"""사람인 채용공고 OPEN API. 사람인 개발자센터(oapi.saramin.co.kr)에서 이용신청·승인 후 access-key 발급.

GET https://oapi.saramin.co.kr/job-search
  access-key, keywords, start(0부터), count(최대 110), sr=directhire(헤드헌팅·파견 제외), sort=pd
"""
from __future__ import annotations

import html

from .. import classify as C
from .. import config
from ..http import SourceError, get

URL = "https://oapi.saramin.co.kr/job-search"
SOURCE = "saramin"
CLOSE_TYPE = {"2": "채용시까지", "3": "상시채용", "4": "수시채용"}


def _query(key: str, keyword: str, max_pages: int) -> list[dict]:
    out = []
    for page in range(max_pages):
        params = {"access-key": key, "keywords": keyword, "start": page, "count": 110,
                  "sr": "directhire", "sort": "pd"}
        data = get(URL, params, headers={"Accept": "application/json"}, secrets=(key,)).json()
        if "code" in data and "jobs" not in data:
            raise SourceError(f"사람인 API 오류 {data.get('code')}: {data.get('message')}")
        jobs = data.get("jobs", {})
        items = jobs.get("job") or []
        if isinstance(items, dict):
            items = [items]
        out.extend(items)
        total = int(jobs.get("total") or 0)
        if (page + 1) * 110 >= total or not items:
            break
    return out


def fetch(access_key: str) -> list[dict]:
    key = access_key.strip()
    seen: dict[str, dict] = {}
    for kw in config.SARAMIN_KEYWORDS:
        for it in _query(key, kw, config.SARAMIN_MAX_PAGES):
            seen.setdefault(str(it.get("id")), it)
    return list(seen.values())


def _name(obj) -> str:
    if isinstance(obj, dict):
        return html.unescape(str(obj.get("name") or "")).strip()
    return html.unescape(str(obj or "")).strip()


def to_job(r: dict) -> dict | None:
    if str(r.get("active", "1")) != "1":
        return None
    pos = r.get("position") or {}
    title = html.unescape(str(pos.get("title") or "")).strip()
    org = _name((r.get("company") or {}).get("detail"))
    if not title or C.is_noise(title):
        return None
    job_type = _name(pos.get("job-type"))
    if job_type and all(t.strip() in ("아르바이트",) for t in job_type.split(",")):
        return None
    industry = _name(pos.get("industry"))
    mid = _name(pos.get("job-mid-code"))
    codes = _name(pos.get("job-code"))
    keyword = html.unescape(str(r.get("keyword") or ""))
    if not C.is_food_job(title, industry, codes, keyword, org):
        return None

    jobs = [c for c in C.job_categories(title) if c != config.JOB_DEFAULT]
    jobs += [c for c in C.job_categories(mid) if c != config.JOB_DEFAULT and c not in jobs]
    if not jobs:
        jobs = C.job_categories(codes)

    close_code = str((r.get("close-type") or {}).get("code", "1"))
    region_text = _name(pos.get("location"))
    return {
        "id": f"{SOURCE}:{r.get('id')}",
        "source": SOURCE,
        "title": title,
        "org": org,
        "org_type": C.org_type(org, SOURCE),
        "jobs": jobs,
        "emp": C.emp_types(job_type, title),
        "career": C.career_norm(_name(pos.get("experience-level"))),
        "edu": _name(pos.get("required-education-level")),
        "regions": C.regions(region_text),
        "region_text": region_text,
        "posted": C.parse_date(r.get("posting-timestamp")),
        "deadline": None if close_code in CLOSE_TYPE else C.parse_date(r.get("expiration-timestamp")),
        "deadline_note": CLOSE_TYPE.get(close_code),
        "url": r.get("url") or "https://www.saramin.co.kr",
        "food": "직무",
        "detail": " · ".join(x for x in (industry, codes[:60]) if x),
    }
