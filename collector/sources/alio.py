"""잡알리오 — 공공데이터포털 「재정경제부_공공기관 채용정보 조회서비스」 (data.go.kr 15125273).

GET https://apis.data.go.kr/1051000/recruitment/list
  serviceKey, pageNo, numOfRows(최대 100), ongoingYn=Y(접수 중만)
"""
from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from urllib.parse import unquote

from .. import classify as C
from .. import config
from ..http import SourceError, get

URL = "https://apis.data.go.kr/1051000/recruitment/list"
SOURCE = "alio"
OK_CODES = {"0", "00", "000", "0000", "200"}


def _key(raw: str) -> str:
    raw = (raw or "").strip()
    return unquote(raw) if "%" in raw else raw


def _parse(text: str) -> tuple[int, list[dict]]:
    text = text.strip()
    if text.startswith("<"):
        # 게이트웨이 오류는 XML로 옴
        root = ET.fromstring(text)
        msg = " ".join(filter(None, (root.findtext(".//returnAuthMsg"), root.findtext(".//errMsg"),
                                     root.findtext(".//resultMsg"))))
        code = root.findtext(".//resultCode") or root.findtext(".//returnReasonCode") or ""
        items = [{c.tag: (c.text or "") for c in it} for it in root.iter("item")]
        if items:
            total = int(root.findtext(".//totalCount") or len(items))
            return total, items
        raise SourceError(f"잡알리오 API 오류: {msg or code or text[:200]}")
    data = json.loads(text)
    if "response" in data:  # 혹시 표준 data.go.kr 래퍼로 올 때
        body = data["response"].get("body", {})
        header = data["response"].get("header", {})
        code = str(header.get("resultCode", "00"))
        data = {"resultCode": code, "resultMsg": header.get("resultMsg"),
                "totalCount": body.get("totalCount"), "result": body.get("items")}
    code = str(data.get("resultCode", "200"))
    if code not in OK_CODES:
        raise SourceError(f"잡알리오 API 오류 {code}: {data.get('resultMsg')}")
    result = data.get("result") or []
    if isinstance(result, dict):
        result = result.get("item") or []
    if isinstance(result, dict):
        result = [result]
    items = [r.get("item", r) if isinstance(r, dict) else {} for r in result]
    total = int(data.get("totalCount") or len(items))
    return total, items


def fetch(service_key: str) -> list[dict]:
    key = _key(service_key)
    params = {"serviceKey": key, "numOfRows": 100, "ongoingYn": "Y"}
    headers = {"Accept": "application/json"}
    out: list[dict] = []
    total, items = _parse(get(URL, {**params, "pageNo": 1}, headers=headers, secrets=(key,)).text)
    out.extend(items)
    pages = min(math.ceil(total / 100), config.ALIO_MAX_PAGES)
    for page in range(2, pages + 1):
        _, items = _parse(get(URL, {**params, "pageNo": page}, headers=headers, secrets=(key,)).text)
        if not items:
            break
        out.extend(items)
    return out


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v if x)
    return str(v).strip()


def to_job(r: dict) -> dict | None:
    title = _s(r.get("recrutPbancTtl"))
    org = _s(r.get("instNm"))
    if not title:
        return None
    ncs = _s(r.get("ncsCdNmLst"))
    if str(r.get("ongoingYn", "Y")).upper() == "N":
        return None
    if C.is_public_noise(title):
        return None
    food_job = C.is_food_job(title) or C.contains_any(ncs, config.FOOD_NCS)
    food_org = C.is_food_institution(org)
    if not (food_job or food_org):
        return None

    jobs = C.job_categories(title)
    if jobs == [config.JOB_DEFAULT]:
        fb = [v for k, v in config.NCS_JOB_FALLBACK.items() if k in ncs]
        jobs = list(dict.fromkeys(fb)) or jobs
    hire = _s(r.get("hireTypeNmLst"))
    if _s(r.get("replmprYn")).upper() == "Y":
        hire += " 대체인력"
    sn = _s(r.get("recrutPblntSn"))
    url = f"https://job.alio.go.kr/recruitview.do?idx={sn}" if sn.isdigit() else (
        _s(r.get("srcUrl")) or "https://job.alio.go.kr/recruit.do")
    region_text = _s(r.get("workRgnNmLst"))
    return {
        "id": f"{SOURCE}:{sn or title}",
        "source": SOURCE,
        "title": title,
        "org": org,
        "org_type": C.org_type(org, SOURCE),
        "jobs": jobs,
        "emp": C.emp_types(hire, title),
        "career": C.career_norm(_s(r.get("recrutSeNm"))),
        "edu": _s(r.get("acbgCondNmLst")),
        "regions": C.regions(region_text),
        "region_text": region_text,
        "posted": C.parse_date(r.get("pbancBgngYmd")),
        "deadline": C.parse_date(r.get("pbancEndYmd")),
        "deadline_note": None,
        "url": url,
        "food": "직무" if food_job else "기관",
        "detail": ncs,
    }
