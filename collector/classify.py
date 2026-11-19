"""공고 분류: 식품 관련성, 기관유형, 직무, 고용형태, 경력, 지역, 날짜."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

from . import config

KST = timezone(timedelta(hours=9))


def today_kst() -> date:
    return datetime.now(KST).date()


# ── 문자열 매칭 ───────────────────────────────────────────
@lru_cache(maxsize=None)
def _token_regex(word: str) -> re.Pattern:
    """짧은 영문 약어(CJ, NH, hy 등)는 다른 영단어 속에 섞여 있을 때 맞지 않도록 경계를 둔다."""
    if re.fullmatch(r"[A-Za-z&]{1,4}", word):
        return re.compile(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])")
    return re.compile(re.escape(word), re.IGNORECASE if word.isascii() else 0)


def contains_any(text: str, words) -> bool:
    if not text:
        return False
    return any(_token_regex(w).search(text) for w in words)


def _join(*parts) -> str:
    out = []
    for p in parts:
        if not p:
            continue
        if isinstance(p, (list, tuple)):
            out.extend(str(x) for x in p if x)
        else:
            out.append(str(p))
    return " ".join(out)


# ── 식품 관련성 ───────────────────────────────────────────
# '위생사'가 들어가도 식품과 무관한 직종
_NON_FOOD_JOBS = re.compile(r"치과\s*위생사|산업\s*위생사")


def is_food_job(*texts) -> bool:
    return contains_any(_NON_FOOD_JOBS.sub(" ", _join(*texts)), config.FOOD_KEYWORDS)


def is_food_institution(org: str) -> bool:
    return contains_any(org or "", config.FOOD_INSTITUTIONS)


def is_noise(title: str) -> bool:
    return contains_any(title or "", config.NOISE_KEYWORDS)


def is_public_noise(title: str) -> bool:
    """공공기관 공고 중 청소·경비 등 비전공 직무이거나 보훈·장애인 제한경쟁인 것."""
    t = title or ""
    return contains_any(t, config.PUBLIC_NOISE_KEYWORDS) or any(
        re.search(p, t) for p in config.RESTRICTED_PATTERNS)


# ── 기관 유형 ────────────────────────────────────────────
def org_type(name: str, source: str, hint: str | None = None) -> str:
    """source: alio / work24 / saramin.  hint: API가 알려준 기업형태(예: 고용24 coTp)."""
    name = name or ""
    if source == "alio":
        if contains_any(name, config.RESEARCH_NAME_PATTERNS):
            return "정부출연·연구기관"
        if contains_any(name, config.INSTITUTION_NAME_PATTERNS) and "병원" in name:
            return "병원·학교·복지기관"
        return "공기업·공공기관"
    if hint in config.ORG_TYPES:
        return hint
    if contains_any(name, config.FOREIGN_COMPANIES):
        return "외국계"
    if contains_any(name, config.BIG_FOOD_COMPANIES):
        return "대기업·주요 식품기업"
    if contains_any(name, config.INSTITUTION_NAME_PATTERNS):
        return "병원·학교·복지기관"
    if re.search(r"^(한국|국립|국가)", name) and contains_any(name, config.RESEARCH_NAME_PATTERNS):
        return "정부출연·연구기관"
    if contains_any(name, config.PUBLIC_NAME_PATTERNS):
        return "공기업·공공기관"
    return "중견·중소기업"


# ── 직무 ────────────────────────────────────────────────
_JOB_RX = [(cat, re.compile("|".join(pats), re.IGNORECASE)) for cat, pats in config.JOB_CATEGORIES]


def job_categories(*texts) -> list[str]:
    text = _join(*texts)
    cats = [cat for cat, rx in _JOB_RX if rx.search(text)]
    # '영양'만 있고 연구·품질 공고인 경우(예: 영양성분 분석)는 급식으로 보지 않음
    if "영양사·급식·조리" in cats and not re.search(r"영양사|영양교사|급식|조리|식단|셰프|쿡", text):
        if len(cats) > 1:
            cats.remove("영양사·급식·조리")
    return cats or [config.JOB_DEFAULT]


# ── 고용형태 ─────────────────────────────────────────────
def emp_types(*texts) -> list[str]:
    text = _join(*texts)
    out = []
    if re.search(r"인턴|체험형|연수생|교육생", text):
        out.append("인턴")
    if re.search(r"무기계약|공무직", text):
        out.append("무기계약직")
    if re.search(r"(?<!무기)계약|비정규|기간제|기간 정함 있는|대체인력|촉탁|위촉|임시", text):
        out.append("계약직")
    if re.search(r"파견|도급|프리랜서|아르바이트|병역특례", text):
        out.append("파견·기타")
    if re.search(r"정규직|기간 정함 없는|정규", text) and "정규직" not in out:
        # '비정규'만 있는 경우는 제외
        if re.search(r"(?<!비)정규", text):
            out.insert(0, "정규직")
    return out or ["기타"]


# ── 경력 ────────────────────────────────────────────────
def career_norm(text: str) -> str:
    t = (text or "").strip()
    if re.search(r"무관|관계없음", t) or t == "Z":
        return "무관"
    new = bool(re.search(r"신입", t)) or t == "N"
    exp = bool(re.search(r"경력", t)) or t == "E"
    if new and exp:
        return "신입·경력"
    if new:
        return "신입"
    if exp:
        return "경력"
    return "무관"


# ── 지역 ────────────────────────────────────────────────
def regions(text: str) -> list[str]:
    """'서울 강남구, 경기 성남시' → ['서울','경기'].  여러 지역이면 등장 순서대로."""
    if not text:
        return []
    found = []
    for chunk in re.split(r"[,/·|;]|\s{2,}|&gt;|>", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        best = None
        for norm, aliases in config.REGION_ALIASES:
            for a in aliases:
                i = chunk.find(a)
                if i >= 0 and (best is None or i < best[0]):
                    best = (i, norm)
        if best and best[1] not in found:
            found.append(best[1])
    return found


# ── 날짜 ────────────────────────────────────────────────
def parse_date(value) -> str | None:
    """여러 API 날짜 형식을 'YYYY-MM-DD'로. 상시/채용시 등은 None."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit() and len(value) >= 10):
        try:
            return datetime.fromtimestamp(int(value), KST).date().isoformat()
        except (ValueError, OSError, OverflowError):
            return None
    s = str(value).strip()
    m = re.search(r"(\d{4})[-./]?(\d{1,2})[-./]?(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"(?<!\d)(\d{2})[-./](\d{1,2})[-./](\d{1,2})(?!\d)", s)
        if not m:
            return None
        y, mo, d = map(int, m.groups())
        y += 2000
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None
