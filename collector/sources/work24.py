"""고용24 채용정보 OPEN-API (옛 워크넷). 기업회원 로그인 후 인증키 신청·승인 필요.

GET https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do
  authKey, callTp=L, returnType=XML, startPage, display(최대 100), keyword, coTp
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .. import classify as C
from .. import salary as S
from .. import config
from ..http import SourceError, get

URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do"
SOURCE = "work24"
COTP_HINT = {"01": "대기업·주요 식품기업", "04": "공기업·공공기관", "05": "외국계"}
EMP_CODE = {"10": "정규직", "11": "정규직", "20": "계약직", "21": "계약직", "4": "파견", "Y": "대체인력"}


def _parse(text: str) -> tuple[int, list[dict]]:
    try:
        root = ET.fromstring(text.strip())
    except ET.ParseError as e:
        raise SourceError(f"고용24 응답을 읽지 못함: {text[:150]}") from e
    items = [{c.tag: (c.text or "").strip() for c in w} for w in root.iter("wanted")]
    if not items:
        msg = root.findtext(".//message") or root.findtext(".//messageCd") or root.findtext(".//error")
        if msg and not (root.findtext(".//total") or "").strip().isdigit():
            raise SourceError(f"고용24 API 오류: {msg}")
    total = int((root.findtext(".//total") or "0").strip() or 0)
    return total, items


def _query(key: str, keyword: str, max_pages: int, co_tp: str | None = None) -> list[dict]:
    out = []
    for page in range(1, max_pages + 1):
        params = {"authKey": key, "callTp": "L", "returnType": "XML", "startPage": page,
                  "display": 100, "keyword": keyword}
        if co_tp:
            params["coTp"] = co_tp
        total, items = _parse(get(URL, params, secrets=(key,)).text)
        out.extend(items)
        if page * 100 >= total or not items:
            break
    return out


def fetch(auth_key: str) -> list[dict]:
    key = auth_key.strip()
    seen: dict[str, dict] = {}
    for kw in config.WORK24_KEYWORDS:
        for it in _query(key, kw, config.WORK24_MAX_PAGES):
            seen.setdefault(it.get("wantedAuthNo") or it.get("wantedInfoUrl") or it.get("title"), it)
    # 기업형태 태깅 (대기업·공공기관·외국계)
    for co_tp, hint in COTP_HINT.items():
        for kw in config.WORK24_COTP_KEYWORDS:
            for it in _query(key, kw, 1, co_tp):
                k = it.get("wantedAuthNo") or it.get("wantedInfoUrl") or it.get("title")
                seen.setdefault(k, it).setdefault("_hint", hint)
    return list(seen.values())


def to_job(r: dict) -> dict | None:
    title = r.get("title", "").strip()
    org = r.get("company", "").strip()
    if not title or C.is_noise(title):
        return None
    ind = r.get("indTpNm", "")
    if not C.is_food_job(title, ind, org):
        return None
    emp_txt = EMP_CODE.get(str(r.get("empTpCd", "")).strip(), "")
    close = r.get("closeDt", "")
    note = "채용시까지" if "채용시" in close else None
    region_text = r.get("region", "")
    sal = " ".join(x for x in (r.get("salTpNm"), r.get("sal")) if x)
    return {
        "id": f"{SOURCE}:{r.get('wantedAuthNo') or title}",
        "source": SOURCE,
        "title": title,
        "org": org,
        "org_type": C.org_type(org, SOURCE, r.get("_hint")),
        "jobs": C.job_categories(title),
        "emp": C.emp_types(emp_txt, title),
        "career": C.career_norm(r.get("career", "")),
        "edu": r.get("minEdubg", ""),
        "regions": C.regions(region_text),
        "region_text": region_text,
        "posted": C.parse_date(r.get("regDt")),
        "deadline": C.parse_date(close),
        "deadline_note": note,
        "url": r.get("wantedInfoUrl") or r.get("wantedMobileInfoUrl") or "https://www.work24.go.kr",
        "food": "직무",
        "detail": ind,
        "salary": S.posting_salary(sal),
        "salary_note": S.posting_note(sal),
    }
