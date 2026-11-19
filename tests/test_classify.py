from collector import classify as C


def test_org_type_private():
    assert C.org_type("CJ제일제당(주)", "saramin") == "대기업·주요 식품기업"
    assert C.org_type("(주)오뚜기", "saramin") == "대기업·주요 식품기업"
    assert C.org_type("한국네슬레", "work24") == "외국계"
    assert C.org_type("Nestle Korea", "saramin") == "외국계"
    assert C.org_type("가나다식품(주)", "saramin") == "중견·중소기업"
    assert C.org_type("서울대학교병원", "work24") == "병원·학교·복지기관"
    assert C.org_type("가람식품", "work24", "대기업·주요 식품기업") == "대기업·주요 식품기업"


def test_short_tokens_need_boundary():
    # 'CJ'·'NH'·'hy' 같은 약어가 다른 영단어 안에서 맞으면 안 됨
    assert C.org_type("SNHFoods", "saramin") == "중견·중소기업"
    assert C.org_type("hyosung", "saramin") == "중견·중소기업"
    assert C.org_type("NH농협", "saramin") == "대기업·주요 식품기업"


def test_org_type_alio():
    assert C.org_type("한국식품연구원", "alio") == "정부출연·연구기관"
    assert C.org_type("한국농수산식품유통공사", "alio") == "공기업·공공기관"


def test_job_categories():
    assert C.job_categories("식품연구소 제품개발 연구원")[0] == "R&D·제품개발"
    assert C.job_categories("식품 품질관리(QC) 신입")[0] == "품질·식품안전"
    assert C.job_categories("위탁급식 영양사 채용") == ["영양사·급식·조리"]
    assert "인허가·RA" in C.job_categories("건강기능식품 인허가(RA) 담당")
    # '영양성분 분석'은 급식 직무가 아님
    assert "영양사·급식·조리" not in C.job_categories("영양성분 분석 연구원")
    assert C.job_categories("2026 하반기 신입사원 채용") == ["기타"]


def test_emp_types():
    assert C.emp_types("정규직") == ["정규직"]
    assert C.emp_types("비정규직") == ["계약직"]
    assert C.emp_types("무기계약직") == ["무기계약직"]
    assert C.emp_types("청년인턴(체험형)") == ["인턴"]
    assert set(C.emp_types("인턴직,정규직")) == {"정규직", "인턴"}
    assert C.emp_types("") == ["기타"]


def test_career():
    assert C.career_norm("신입") == "신입"
    assert C.career_norm("신입+경력") == "신입·경력"
    assert C.career_norm("신입·경력") == "신입·경력"
    assert C.career_norm("경력 3년↑") == "경력"
    assert C.career_norm("경력무관") == "무관"
    assert C.career_norm("관계없음") == "무관"


def test_regions():
    assert C.regions("서울 > 중구,충북 > 진천군") == ["서울", "충북"]
    assert C.regions("경기 광주시") == ["경기"]
    assert C.regions("광주광역시 북구") == ["광주"]
    assert C.regions("전라북도 완주군") == ["전북"]
    assert C.regions("경기, 인천") == ["경기", "인천"]


def test_dates():
    assert C.parse_date("20261128") == "2026-11-28"
    assert C.parse_date("26-12-05") == "2026-12-05"
    assert C.parse_date("채용시까지 26-12-17") == "2026-12-17"
    assert C.parse_date("1764514800") == "2025-12-01"
    assert C.parse_date("상시") is None
    assert C.parse_date("") is None


def test_food_and_noise():
    assert C.is_food_job("체험형 청년인턴(식품안전 분야)")
    assert not C.is_food_job("2026년 하반기 신입사원 공개채용")
    assert not C.is_food_job("인적 리소스 관리")
    assert C.is_noise("냉장 식품 배송기사 모집")
    assert not C.is_noise("식품 품질관리 신입")


def test_public_noise():
    # 청소·경비 직무와 보훈·장애인 제한경쟁은 제외
    assert C.is_public_noise("한국농어촌공사 청주지사 공무직(청소원) 보훈·장애인 제한경쟁 채용공고")
    assert C.is_public_noise("한국농어촌공사 철원화천지사 공무직(청소원) 보훈ㆍ장애인 제한경쟁 채용 공고")
    assert C.is_public_noise("부산항만공사 기간제 직원(장애인 바리스타) 채용 공고")
    assert C.is_public_noise("OO공단 보훈 제한경쟁 채용")
    # '청소년' 기관·일반 조리직은 남겨야 함
    assert not C.is_public_noise("2026년 제3차 한국청소년활동진흥원 직원(일반직, 공무직) 채용 공고")
    assert not C.is_public_noise("한국폴리텍대학 남대구캠퍼스 업무직(대학운영직_조리사) 채용(3차) 공고")
    assert not C.is_public_noise("식품안전정보원 2026년 제3차 기간제 직원 채용")


def test_non_food_hygienist():
    assert not C.is_food_job("인천적십자병원 비정규직 치과위생사 채용공고")
    assert not C.is_food_job("[순천병원] 기간제(산업위생사) 채용 공고")
    assert C.is_food_job("식품위생 담당 채용")


def test_gongmujik_is_not_production():
    assert "생산·공정관리" not in C.job_categories("OO공사 공무직(조리원) 채용")
    assert "생산·공정관리" in C.job_categories("공장 공무팀 설비 담당")


def test_rural_corp_not_food_institution():
    assert not C.is_food_institution("한국농어촌공사")
