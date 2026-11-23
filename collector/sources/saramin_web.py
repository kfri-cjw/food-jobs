"""사람인 검색 화면 읽기 — 사람인 OPEN API 키(SARAMIN_KEY)가 없을 때만 쓰는 개인용 대체 수집기.

- SARAMIN_WEB=1 일 때만 동작 (기본은 꺼짐). SARAMIN_KEY를 넣으면 자동으로 공식 API로 바뀜.
- 로그인 없이 보이는 공개 화면만 읽음. robots.txt에서 막지 않은 경로만 사용
    목록: /zf_user/search/recruit   상세: /zf_user/jobs/relay/view-detail
- 요청마다 config.SARAMIN_WEB_DELAY초 쉬고, 상세는 처음 보는 공고만 받음 (이전 결과 재사용)
- 화면 구조가 바뀌면 0건이 되므로 그때는 오류로 표시하고 이전 데이터를 유지함
"""
from __future__ import annotations

import re
import time
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from .. import classify as C
from .. import config
from ..http import SourceError, get

BASE = "https://www.saramin.co.kr"
SEARCH_URL = BASE + "/zf_user/search/recruit"
DETAIL_URL = BASE + "/zf_user/jobs/relay/view-detail"
VIEW_URL = BASE + "/zf_user/jobs/relay/view"
SOURCE = "saramin"
HEADERS = {"Accept-Language": "ko-KR,ko;q=0.9", "Referer": BASE + "/"}
DETAIL_KEYS = ("quals", "salary", "salary_note", "address", "headcount")

sleep = time.sleep  # 테스트에서 바꿔 끼움


# ── 목록 ────────────────────────────────────────────────
def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def _rec_idx(item) -> str:
    v = (item.get("value") or "").strip()
    if v.isdigit():
        return v
    a = item.select_one("h2.job_tit a[href]")
    if a:
        q = parse_qs(urlsplit(a["href"]).query)
        return (q.get("rec_idx") or [""])[0]
    return ""


def parse_list(html: str) -> list[dict]:
    """검색 결과 화면 → 공고 카드 목록 (가공 전 값)."""
    out = []
    for it in BeautifulSoup(html, "html.parser").select("div.item_recruit"):
        rid = _rec_idx(it)
        a = it.select_one("h2.job_tit a")
        corp = it.select_one("strong.corp_name a[href]")
        csn = (parse_qs(urlsplit(corp["href"]).query).get("csn") or [""])[0] if corp else ""
        if not rid or not a:
            continue
        cond = {"location": "", "career": "", "edu": "", "emp": "", "pay": ""}
        for sp in it.select("div.job_condition > span"):
            t = _text(sp)
            if not t:
                continue
            if sp.select_one("a[href*='area']") and not cond["location"]:
                cond["location"] = t
            elif re.search(r"\d[\d,]*\s*(만\s*)?원", t):
                cond["pay"] = t
            elif re.search(r"신입|경력", t):
                cond["career"] = t
            elif re.search(r"졸|학력|석사|박사", t):
                cond["edu"] = t
            elif re.search(r"정규|계약|인턴|파견|기간제|프리랜서|아르바이트|위촉|병역", t):
                cond["emp"] = t
            elif not cond["location"]:
                cond["location"] = t
        out.append({
            "rec_idx": rid,
            "title": (a.get("title") or _text(a)).strip(),
            "org": _text(it.select_one("strong.corp_name")),
            "csn": csn,
            **cond,
            "deadline_text": _text(it.select_one("div.job_date .date")),
            "day_text": _text(it.select_one("span.job_day")),
            "sectors": [_text(x) for x in it.select("div.job_sector a")][:8],
        })
    return out


def fetch(_key: str | None = None) -> list[dict]:
    """키워드별 검색 결과를 모아 공고 번호로 중복 제거."""
    seen: dict[str, dict] = {}
    first = True
    for kw in config.SARAMIN_WEB_KEYWORDS:
        for page in range(1, config.SARAMIN_WEB_MAX_PAGES + 1):
            if not first:
                sleep(config.SARAMIN_WEB_DELAY)
            first = False
            params = {"searchType": "search", "searchword": kw, "recruitPage": page,
                      "recruitPageCount": 100, "recruitSort": "reg_dt"}
            items = parse_list(get(SEARCH_URL, params, headers=HEADERS).text)
            for r in items:
                seen.setdefault(r["rec_idx"], r)
            if len(items) < 100:
                break
    if not seen:
        raise SourceError("사람인 검색 화면에서 0건 — 화면 구조가 바뀌었거나 접속이 막혔을 수 있음")
    return list(seen.values())


# ── 목록 카드 → 공고 ─────────────────────────────────────
_EDU = [("학력무관", "무관"), ("박사", "박사"), ("석사", "석사 이상"), ("초대졸", "대졸(2~3년) 이상"),
        ("대졸", "대졸(4년) 이상"), ("고졸", "고졸 이상")]


def _edu(t: str) -> str:
    for k, v in _EDU:
        if k in (t or ""):
            return v
    return t or ""


def _deadline(t: str, today: date) -> tuple[str | None, str | None]:
    t = (t or "").strip()
    if re.search(r"상시", t):
        return None, "상시채용"
    if re.search(r"채용\s*시", t):
        return None, "채용시까지"
    if "오늘마감" in t.replace(" ", ""):
        return today.isoformat(), None
    if "내일마감" in t.replace(" ", ""):
        return (today + timedelta(days=1)).isoformat(), None
    m = re.search(r"(\d{1,2})/(\d{1,2})", t)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        for y in (today.year, today.year + 1):
            try:
                cand = date(y, mo, d)
            except ValueError:
                continue
            if cand >= today - timedelta(days=31):  # 연도가 없으므로 지난 날짜면 내년
                return cand.isoformat(), None
    return C.parse_date(t), None


def _posted(t: str) -> str | None:
    m = re.search(r"(\d{2})/(\d{1,2})/(\d{1,2})", t or "")
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return date(2000 + y, mo, d).isoformat()
    except ValueError:
        return None


def pay_from_list(t: str) -> str | None:
    """목록의 '3,400 만원' / '240 만원' / '10,320 원' → 단위를 붙인 문구. (목록에는 연봉·월급 구분이 없음)"""
    m = re.search(r"(\d[\d,]*)\s*(만\s*)?원", t or "")
    if not m:
        return None
    n = int(m.group(1).replace(",", ""))
    if m.group(2):
        return f"연봉 {n:,}만원" if n >= 1000 else f"월급 {n:,}만원"
    return f"시급 {n:,}원" if n < 100000 else f"{n:,}원"


def is_headhunter(r: dict) -> bool:
    text = " ".join(r.get("sectors") or [])
    return contains(text, config.SARAMIN_WEB_EXCLUDE_SECTORS) or bool(
        re.search(config.HEADHUNTER_ORG_PATTERN, r.get("org") or ""))


def contains(text: str, words) -> bool:
    return any(w in text for w in words)


def to_job(r: dict, today: date | None = None) -> dict | None:
    today = today or C.today_kst()
    title, org = r.get("title", ""), r.get("org", "")
    if not title or C.is_noise(title) or is_headhunter(r):
        return None
    if r.get("emp") and all(x.strip() == "아르바이트" for x in r["emp"].split("·")):
        return None
    sectors = r.get("sectors") or []
    if not C.is_food_job(title, sectors, org):
        return None
    jobs = [c for c in C.job_categories(title) if c != config.JOB_DEFAULT]
    jobs += [c for c in C.job_categories(sectors) if c != config.JOB_DEFAULT and c not in jobs]
    deadline, note = _deadline(r.get("deadline_text", ""), today)
    pay = pay_from_list(r.get("pay", ""))
    loc = r.get("location", "")
    return {
        "id": f"{SOURCE}:{r['rec_idx']}",
        "source": SOURCE,
        "title": title,
        "org": org,
        "org_type": C.org_type(org, SOURCE),
        "jobs": jobs or [config.JOB_DEFAULT],
        "emp": C.emp_types(r.get("emp", ""), title),
        "career": C.career_norm(r.get("career", "")),
        "career_text": r.get("career") or None,   # '경력3년↑', '경력 5~10년' 같은 원래 표기
        "edu": _edu(r.get("edu", "")),
        "regions": C.regions(loc),
        "region_text": loc,
        "posted": _posted(r.get("day_text", "")),
        "deadline": deadline,
        "deadline_note": note,
        "url": f"{VIEW_URL}?rec_idx={r['rec_idx']}",
        "food": "직무",
        "detail": " · ".join(sectors[:5]),
        "salary": {"kind": "posting", "text": pay} if pay else None,
        "csn": r.get("csn") or None,
    }


# ── 상세(지원자격·급여·근무지) ─────────────────────────────
_HEAD = re.compile(
    r"^[\W_]*(모집\s*분야|모집\s*부문|모집\s*요강|담당\s*업무|주요\s*업무|업무\s*내용|자격\s*요건|지원\s*자격|자격\s*조건|"
    r"필수\s*(요건|사항|조건|자격)|우대\s*(사항|조건|요건)|근무\s*조건|근무\s*환경|복지|혜택|채용\s*절차|전형\s*절차|"
    r"접수\s*(기간|방법)|제출\s*서류|유의\s*사항|기타\s*사항|참고\s*사항)")
_QUAL_HEAD = re.compile(r"자격\s*요건|지원\s*자격|자격\s*조건|필수\s*(요건|사항|조건|자격)")
_PREF_HEAD = re.compile(r"우대\s*(사항|조건|요건)")
_LABEL = {
    "salary": re.compile(r"^[\W_]*(급여|연봉|보수|임금|급여\s*조건)\s*[:：]?\s*(.*)$"),
    "address": re.compile(r"^[\W_]*(근무\s*지|근무\s*지역|근무\s*장소|근무\s*위치|근무처)\s*[:：]?\s*(.*)$"),
}


def _lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for x in soup(["script", "style", "noscript"]):
        x.decompose()
    return [re.sub(r"\s+", " ", ln).strip() for ln in soup.get_text("\n").splitlines() if ln.strip()]


def _section(lines: list[str], head: re.Pattern, limit: int) -> str:
    out, on = [], False
    for ln in lines:
        is_head = bool(_HEAD.match(ln)) and len(ln) <= 30
        if on and is_head and not head.search(ln):
            break
        m = head.search(ln)
        if m and len(ln) <= 30:
            on = True
            rest = ln[m.end():]
            if re.match(r"\s*[:：]", rest):  # '자격요건: 대졸 이상' 처럼 같은 줄에 값이 있을 때만
                out.append(re.sub(r"^\s*[:：]\s*", "", rest))
            continue
        if on:
            out.append(ln)
    return "\n".join(out)[:limit].strip()


_VALID = {
    "salary": re.compile(r"\d[\d,]*\s*(만\s*)?원|면접|내규|협의|결정|추후"),
    "address": re.compile(r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청|충북|충남|전라|전북|전남|경상|경북|경남|제주)|"
                          r"[가-힣]+(시|군|구|읍|면|동|로|길)(\s|$|\d)"),
}


def _labeled(lines: list[str], key: str) -> str:
    rx = _LABEL[key]
    for i, ln in enumerate(lines):
        m = rx.match(ln)
        if not m or len(ln) > 120:
            continue
        val = m.group(2).strip(" :：-·•")
        if val and key == "salary" and m.group(1) == "연봉":
            val = f"연봉 {val}"  # '연봉 : 3,400만원' → 연봉/월급 구분이 남도록
        if not val and i + 1 < len(lines):
            nxt = lines[i + 1].strip(" :：-·•")
            others = [r for k, r in _LABEL.items() if k != key]
            if not _HEAD.match(nxt) and not any(r.match(nxt) for r in others):
                val = nxt
        if val and _VALID[key].search(val):
            return val[:120]
    return ""


def parse_detail(html: str) -> dict:
    """상세 본문 → 지원자격·우대·급여 문구·근무지 주소·모집인원. 이미지로만 된 공고는 빈 값."""
    lines = _lines(html)
    if sum(len(x) for x in lines) < 80:
        return {}
    qual = _section(lines, _QUAL_HEAD, 900)
    pref = _section(lines, _PREF_HEAD, 500)
    out = {"salary_text": _labeled(lines, "salary"), "address": _labeled(lines, "address")}
    m = re.search(r"\((\d{1,3})\s*명\)|모집\s*인원\s*[:：]?\s*(\d{1,3})\s*명", "\n".join(lines))
    if m:
        n = int(m.group(1) or m.group(2))
        out["headcount"] = n if n > 0 else None
    if qual or pref:
        q = C.qualifications(qual, pref)
        q["text"], q["pref"] = qual, pref
        out["quals"] = q
    return out


def parse_meta_salary(html: str) -> str:
    """공고 페이지 meta description의 급여 값 ('연봉:3,400만원' / '면접 후 결정' / '회사내규에 따름')."""
    m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', html)
    if not m:
        return ""
    desc = m.group(1)
    m = re.search(r"(연봉|월급|시급|일급|주급)\s*:\s*([^,]+)", desc)
    if m:
        return f"{m.group(1)} {m.group(2).strip()}"
    m = re.search(r"(면접\s*후\s*결정|회사\s*내규에\s*따름)", desc)
    return m.group(1) if m else ""


def _apply_detail(j: dict, d: dict, meta_salary: str = "") -> None:
    """상세 본문의 급여 문구가 목록 값(단위 추정)보다 정확하므로 숫자가 있으면 덮어씀."""
    text = d.get("salary_text") or meta_salary
    if text and re.search(r"\d", text):
        j["salary"] = {"kind": "posting", "text": text}
    elif text and not j.get("salary"):
        j["salary_note"] = text
    for k in ("address", "headcount", "quals"):
        if d.get(k):
            j[k] = d[k]


def enrich(jobs: list[dict], prev_by_id: dict, today: date | None = None) -> list[dict]:
    """상세 정보 붙이기. 전에 받은 공고는 이전 값을 그대로 쓰고, 새 공고만 최대 N건 받는다."""
    today = today or C.today_kst()
    budget = config.SARAMIN_WEB_DETAIL_MAX
    for j in jobs:
        prev = prev_by_id.get(j["id"]) or {}
        if prev.get("detail_checked"):
            for k in DETAIL_KEYS:
                if prev.get(k) is not None:
                    j[k] = prev[k]
            if j.get("salary"):
                j.pop("salary_note", None)
            j["detail_checked"] = prev["detail_checked"]
            continue
        if budget <= 0:
            continue
        budget -= 1
        rid = j["id"].split(":", 1)[1]
        try:
            sleep(config.SARAMIN_WEB_DELAY)
            d = parse_detail(get(DETAIL_URL, {"rec_idx": rid, "rec_seq": 0}, headers=HEADERS, retries=2).text)
            meta = ""
            if not d and not j.get("salary"):  # 이미지로만 된 공고만 공고 페이지 요약에서 급여 확인 (요청 수 절약)
                sleep(config.SARAMIN_WEB_DELAY)
                meta = parse_meta_salary(get(VIEW_URL, {"rec_idx": rid}, headers=HEADERS, retries=2).text)
        except SourceError:
            continue  # 상세 하나 실패는 넘어가고 다음 실행에 다시 시도
        _apply_detail(j, d, meta)
        j["detail_checked"] = today.isoformat()
    return jobs
