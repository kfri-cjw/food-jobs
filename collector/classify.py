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


@lru_cache(maxsize=None)
def _name_regex(word: str) -> re.Pattern:
    """회사 이름 목록용: 한글 이름은 다른 한글 낱말 속에 섞여 있으면 맞지 않게 한다 ('하이랜드' 속 '이랜드' 제외)."""
    if re.match(r"[가-힣]", word):
        return re.compile(rf"(?:(?<![가-힣])|(?<=한국)){re.escape(word)}")  # '한국네슬레'처럼 '한국'은 허용
    return _token_regex(word)


def name_has(name: str, words) -> bool:
    return bool(name) and any(_name_regex(w).search(name) for w in words)


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
    if name_has(name, config.FOREIGN_COMPANIES):
        return "외국계"
    if name_has(name, config.BIG_FOOD_COMPANIES):
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


# ── 지원 자격 요약 ─────────────────────────────────────────
_CERTS = [
    ("영양사 면허", r"(?<!임상)영양사\s*(면허|자격)"),
    ("임상영양사", r"임상\s*영양사"),
    ("위생사", r"(?<!치과)(?<!산업)(?<!치과 )위생사\s*(면허|자격)"),
    ("조리기능사", r"(한식|양식|중식|일식|복어)?\s*조리\s*(기능사|산업기사|기능장)"),
    ("식품기사", r"식품\s*(기사|산업기사|기술사)"),
    ("식품가공기능사", r"식품\s*가공\s*기능사"),
    ("축산·수산 기사", r"(축산|수산제조)\s*(기사|산업기사)"),
    ("제과·제빵기능사", r"제(과|빵)\s*기능사"),
    ("바리스타", r"바리스타\s*(\d급|자격)"),
    ("HACCP 교육", r"(HACCP|해썹)\s*(교육|팀장|이수|자격)"),
    ("운전면허", r"(1종|2종)?\s*(보통|대형)?\s*운전\s*면허"),
    ("컴퓨터활용능력", r"컴퓨터\s*활용\s*능력"),
]
_LANG = r"(TOEIC|토익|TEPS|텝스|OPIc|오픽|TOEFL|토플|JLPT|HSK|TOEIC\s*Speaking|토익\s*스피킹)"
_LIMITS = [
    ("지역 제한", r"(이전\s*)?지역\s*인재|주민등록.{0,15}(거주|소재)|(시|도|군)\s*거주자|거주\s*제한"),
    ("고졸 전형", r"고졸\s*(제한|전형|채용)|고등학교\s*졸업\s*(예정)?자\s*(만|로\s*제한)"),
    ("나이 제한", r"만\s*\d{2}\s*세\s*(이하|미만)"),
    ("병역 필", r"병역\s*(필|을\s*필한|의무를\s*마친)"),
]
_MAJOR_CLAUSE = re.compile(r"([^,.;:()\[\]]{0,40}?)(?:관련\s*)?(?:학과|전공|계열)")
_MAJOR_WORD = re.compile(r"(?:식품|영양|조리|외식|생명|미생물|화학|생물|축산|수산|농업|발효|보건|간호)[가-힣]{0,5}?(?:공학|과학|학)?(?=\s|·|/|,|및|또는|관련|학과|전공|계열|$)")


def qualifications(*texts) -> dict:
    """공고의 지원자격·우대조건 글에서 자격증·어학·전공·제한 조건을 뽑는다."""
    text = re.sub(r"\s+", " ", _join(*texts))
    if not text.strip():
        return {}
    certs = [name for name, pat in _CERTS if re.search(pat, text, re.I)]
    langs = []
    for m in re.finditer(_LANG + r"[^0-9가-힣]{0,6}(\d{3,4}|IM\d?|IH|AL|\d급|N\d)?", text, re.I):
        word = m.group(1).upper().replace("토익", "TOEIC").replace("텝스", "TEPS").replace("오픽", "OPIC").replace("토플", "TOEFL")
        label = f"{word} {m.group(2)}".strip() if m.group(2) else word
        if label not in langs:
            langs.append(label)
    majors = list(dict.fromkeys(w.group(0) for c in _MAJOR_CLAUSE.finditer(text)
                                for w in _MAJOR_WORD.finditer(c.group(1))))[:4]
    limits = [name for name, pat in _LIMITS if re.search(pat, text)]
    return {"certs": certs, "langs": langs[:3], "majors": majors, "limits": limits}
