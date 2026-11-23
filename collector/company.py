"""회사 규모(기업형태·사원수·매출액·설립·업종) 붙이기 — 민간 기업 공고만.

- 사람인 기업정보 화면(/zf_user/company-info/view?csn=…, robots.txt에서 Allow)을 회사당 한 번 읽어
  docs/data/companies.json 에 저장하고 REFRESH_DAYS 동안 다시 받지 않는다.
- 공공기관·정부출연기관 공고는 규모를 붙이지 않는다 (화면에서 '공공기관'으로 따로 표시).
- SARAMIN_WEB=1 일 때만 새로 받는다. 꺼져 있어도 저장해 둔 값은 붙인다.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from . import config
from .http import SourceError, get

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "docs" / "data" / "companies.json"
URL = "https://www.saramin.co.kr/zf_user/company-info/view"
HEADERS = {"Accept-Language": "ko-KR,ko;q=0.9", "Referer": "https://www.saramin.co.kr/"}
PUBLIC_TYPES = ("공기업·공공기관", "정부출연·연구기관")
TYPE_TO_ORG = {"대기업": "대기업·주요 식품기업", "외국계": "외국계", "공공기관": "공기업·공공기관"}

sleep = time.sleep


def revenue_eok(text: str) -> float | None:
    """'1조 2,345억 6,789만원' → 12345.6789 (억원)."""
    t = (text or "").replace(",", "")
    if not re.search(r"\d", t):
        return None
    jo = re.search(r"(\d+(?:\.\d+)?)\s*조", t)
    eok = re.search(r"(\d+(?:\.\d+)?)\s*억", t)
    man = re.search(r"(\d+(?:\.\d+)?)\s*만", t)
    v = (float(jo.group(1)) * 10000 if jo else 0) + (float(eok.group(1)) if eok else 0) \
        + (float(man.group(1)) / 10000 if man else 0)
    return round(v, 2) if v else None


def parse_company(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    out: dict = {}
    for li in soup.select("li.company_summary_item"):
        desc_el = li.select_one(".company_summary_desc")
        desc = desc_el.get_text(" ", strip=True) if desc_el else ""
        if desc_el:
            desc_el.extract()
        val = re.sub(r"\s+", " ", li.get_text(" ", strip=True))
        if desc.endswith("설립"):
            m = re.search(r"(\d{4})년", desc)
            out["founded"] = int(m.group(1)) if m else None
        elif desc == "기업형태":
            m = re.search(r"대기업|중견기업|중소기업|외국계|공공기관|공기업|스타트업|비영리|협회|단체", val)
            out["type"] = m.group(0) if m else (val.split() or [""])[0][:12]
        elif desc == "사원수":
            m = re.search(r"([\d,]+)\s*명", val)
            if m:
                out["employees"] = int(m.group(1).replace(",", ""))
                src = re.search(r"출처\s*[:：]\s*(\S+)", val)
                out["employees_src"] = src.group(1) if src else None
        elif desc == "매출액":
            out["revenue"] = val[:30]
            out["revenue_eok"] = revenue_eok(val)
    for g in soup.select("div.company_details_group"):
        dt, dd = g.select_one("dt"), g.select_one("dd")
        if dt and dd and dt.get_text(strip=True) == "업종":
            out["industry"] = re.sub(r"\s+", " ", dd.get_text(" ", strip=True))[:60]
    return {k: v for k, v in out.items() if v is not None}


def load(path: Path = PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def size_band(info: dict | None) -> str:
    n = (info or {}).get("employees")
    if n is None:
        return "정보 없음"
    return "1,000명 이상" if n >= 1000 else "300~999명" if n >= 300 else "50~299명" if n >= 50 else "50명 미만"


def attach(jobs: list[dict], today: date, fetch_new: bool, path: Path = PATH) -> dict:
    """공고에 company 정보를 붙이고 상태를 돌려준다. 실패해도 예외를 던지지 않는다."""
    table = load(path)
    items: dict = table.get("items") or {}
    budget, fetched, failed = config.COMPANY_FETCH_MAX, 0, 0
    first = True
    for j in jobs:
        csn = j.get("csn")
        if not csn or j.get("org_type") in PUBLIC_TYPES:
            continue
        cur = items.get(csn)
        stale = not cur or (today - date.fromisoformat(cur.get("checked", "2000-01-01"))).days >= config.COMPANY_REFRESH_DAYS
        if stale and fetch_new and budget > 0:
            budget -= 1
            try:
                if not first:
                    sleep(config.SARAMIN_WEB_DELAY)
                first = False
                info = parse_company(get(URL, {"csn": csn}, headers=HEADERS, retries=2).text)
                cur = {**info, "name": j.get("org"), "checked": today.isoformat()}
                items[csn] = cur
                fetched += 1
            except SourceError:
                failed += 1
        if not cur:
            continue
        info = {k: cur[k] for k in ("type", "employees", "employees_src", "revenue", "revenue_eok", "founded", "industry") if k in cur}
        if info:
            j["company"] = info
            hint = TYPE_TO_ORG.get(info.get("type", ""))
            if hint and j.get("org_type") == "중견·중소기업":
                j["org_type"] = hint  # 이름 목록으로 못 잡은 대기업·외국계를 기업형태로 보정
    if fetched:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"updated": today.isoformat(), "source": "사람인 기업정보", "items": items},
                                   ensure_ascii=False, indent=0), encoding="utf-8")
    return {"fetched": fetched, "failed": failed, "cached": len(items)}
