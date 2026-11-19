"""예상 연봉 붙이기.

- 공공기관(잡알리오) 공고: 알리오 경영공시 「신입사원 초임」(기관별, 일반정규직 기준)
  → docs/data/salary_public.json 에 기관별 표로 저장해 두고, 일주일에 한 번만 새로 받는다.
  (알리오 통계 화면이 쓰는 공개 JSON. 받기에 실패하면 저장해 둔 표를 그대로 쓴다)
- 민간(고용24·사람인) 공고: 공고에 적힌 급여 문구를 그대로 쓴다.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .http import get

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_PATH = ROOT / "docs" / "data" / "salary_public.json"
ALIO_STAT_URL = "https://www.alio.go.kr/statisticsSearch/findSingleItemSearchList.json"
ALIO_STAT_PARAMS = {"reportFormNo": "20601", "itemNo": "GI0208"}  # 신입사원 초임 > 합계
REFRESH_DAYS = 7
YEARS_IN_RESPONSE = 6  # yy0 = 올해, yy1 = 작년, … yy5



def norm_org(name: str) -> str:
    s = re.sub(r"\((주|재|사)\)|㈜|주식회사|재단법인|사단법인|학교법인", "", name or "")
    return re.sub(r"[\s·・.,\-]+", "", s)


# ── 알리오 신입사원 초임 표 ────────────────────────────────
def parse_alio_rows(rows: list[dict], this_year: int) -> dict:
    items = {}
    for r in rows:
        name = (r.get("apbaNa") or "").strip()
        if not name:
            continue
        by_year = {}
        for i in range(YEARS_IN_RESPONSE):
            v = str(r.get(f"yy{i}") or "").replace(",", "").strip()
            if v.isdigit() and int(v) > 0:
                by_year[str(this_year - i)] = int(v)  # 단위: 천원
        if by_year:
            items[name] = {"type": r.get("apbaTypeNm") or "", "by_year": by_year}
    return items


def fetch_alio_starting(this_year: int) -> dict:
    rows, page = [], 1
    while True:
        r = get(ALIO_STAT_URL, {**ALIO_STAT_PARAMS, "pageNo": page, "countPerPage": 100},
                headers={"Accept": "application/json", "Referer": "https://www.alio.go.kr/"}, retries=2)
        data = (r.json() or {}).get("data") or {}
        got = data.get("result") or []
        rows.extend(got)
        total = int(data.get("cnt") or 0)
        if not got or len(rows) >= total or page >= 20:
            break
        page += 1
    items = parse_alio_rows(rows, this_year)
    if len(items) < 50:  # 형식이 바뀌었거나 일부만 온 경우 — 저장하지 않음
        raise ValueError(f"알리오 신입사원 초임 표가 비정상적으로 작음({len(items)}건)")
    return items


def load_public(path: Path = PUBLIC_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def refresh_public(today: date, path: Path = PUBLIC_PATH, fetch=fetch_alio_starting) -> dict:
    """표가 없거나 오래됐으면 새로 받는다. 실패해도 예외를 던지지 않고 상태만 돌려준다."""
    cur = load_public(path)
    last = cur.get("updated")
    if last and (today - date.fromisoformat(last)).days < REFRESH_DAYS and cur.get("items"):
        return {"state": "cached", "updated": last, "count": len(cur["items"])}
    try:
        items = fetch(today.year)
    except Exception as e:  # noqa: BLE001 — 연봉 표는 없어도 사이트는 돌아가야 함
        return {"state": "error", "updated": last, "count": len(cur.get("items", {})),
                "message": str(e)[:200]}
    data = {"updated": today.isoformat(), "unit": "천원",
            "source": "알리오 경영공시 · 신입사원 초임(일반정규직, 무기계약직 제외)", "items": items}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    return {"state": "ok", "updated": data["updated"], "count": len(items)}


def _pick_year(by_year: dict, this_year: int):
    """작년(마감된 해) 값을 우선, 없으면 가장 최근 값."""
    years = sorted((int(y) for y in by_year), reverse=True)
    for y in years:
        if y < this_year:
            return y, by_year[str(y)]
    return (years[0], by_year[str(years[0])]) if years else (None, None)


# ── 공고에 붙이기 ─────────────────────────────────────────
def averages(table: dict, today: date) -> dict:
    """공시 기관 단순평균(만원): 전체, 기관유형별. 각 기관의 '_pick_year' 값 기준."""
    by_type: dict[str, list[int]] = {}
    year_seen = []
    for v in (table.get("items") or {}).values():
        y, val = _pick_year(v["by_year"], today.year)
        if not val:
            continue
        year_seen.append(y)
        by_type.setdefault(_type_group(v.get("type", "")), []).append(val)
    allv = [x for vs in by_type.values() for x in vs]
    if not allv:
        return {}
    mean = lambda xs: round(sum(xs) / len(xs) / 10)
    return {"all": mean(allv), "n": len(allv),
            "year": max(set(year_seen), key=year_seen.count),
            "by_type": {k: mean(vs) for k, vs in by_type.items() if len(vs) >= 5}}


def _type_group(t: str) -> str:
    return "공기업" if t.startswith("공기업") else "준정부기관" if t.startswith("준정부") else "기타공공기관"


def attach(jobs: list[dict], table: dict, today: date) -> int:
    index = {norm_org(k): v for k, v in (table.get("items") or {}).items()}
    avg = averages(table, today)
    n = 0
    for j in jobs:
        if j.get("salary"):
            n += 1
            continue
        if j.get("source") != "alio":
            continue
        hit = index.get(norm_org(j.get("org", "")))
        if not hit:
            continue
        year, val = _pick_year(hit["by_year"], today.year)
        if not val:
            continue
        tg = _type_group(hit.get("type", ""))
        j["salary"] = {
            "kind": "public_start",
            "amount": round(val / 10),  # 천원 → 만원
            "year": year,
            "regular": "정규직" in (j.get("emp") or []),
            "type": tg,
            "avg_all": avg.get("all"),
            "avg_type": (avg.get("by_type") or {}).get(tg),
        }
        n += 1
    return n


def posting_salary(text: str) -> dict | None:
    """민간 공고에 적힌 급여 문구. 숫자가 없는 것('회사내규에 따름', '면접후 결정')은 버린다."""
    t = re.sub(r"\s+", " ", text or "").strip()
    if not re.search(r"\d", t):
        return None
    return {"kind": "posting", "text": t}
