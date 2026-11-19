# 식품·영양 채용공고 모아보기

식품공학·식품영양·식품 관련 전공 학생을 위한 채용공고 모음 사이트입니다.
공식 Open API 세 곳에서 공고를 모아 **기관 유형 · 직무 · 고용 형태 · 경력 · 지역**으로 나눠 보여주고,
GitHub Actions가 **하루 두 번(06:17, 18:17)** 자동으로 새 공고를 받아 사이트를 갱신합니다.

| 출처 | 내용 | 필요한 키 (GitHub Secret 이름) |
|---|---|---|
| 잡알리오 (공공데이터포털) | 공공기관 전체 공고 중 식품 직무 + 식품 관련 기관 공고 | `DATA_GO_KR_KEY` |
| 고용24 | 민간 공고 (중견·중소 식품기업 많음) | `WORK24_KEY` |
| 사람인 | 민간 공고 (대기업·식품사 많음) | `SARAMIN_KEY` |

키는 있는 것만 넣어도 됩니다. 없는 출처는 건너뛰고 나머지로 동작합니다.

---

## 처음 한 번만 하는 설정 (약 30분 + 키 승인 대기)

### 1. 인증키 받기

**① 공공데이터포털 — 잡알리오 (가장 먼저, 거의 바로 발급)**
1. https://www.data.go.kr 회원가입 → 로그인
2. [재정경제부_공공기관 채용정보 조회서비스](https://www.data.go.kr/data/15125273/openapi.do) → **활용신청** (개발계정 자동승인, 하루 1,000회)
3. 마이페이지 → 데이터활용 → Open API → 활용신청 현황 → **일반 인증키(Decoding)** 복사
   - 승인 직후 1~2시간은 "등록되지 않은 키" 오류가 날 수 있습니다.

**② 고용24 (선택)**
1. https://www.work24.go.kr 에서 **기업회원**으로 가입 (OPEN-API는 기업회원 전용)
2. 로그인 → 고객센터 → OPEN-API → 서비스 소개 및 신청 → **채용정보** API 신청
3. 담당자 심사 후 발급된 인증키 복사

**③ 사람인 (선택)**
1. https://oapi.saramin.co.kr 에서 **채용검색 API 이용신청** (사용 목적: 대학 학생 대상 식품 전공 채용정보 안내)
2. 승인 후 로그인 → 앱 등록 → **access-key** 복사

### 2. GitHub 저장소 만들기

1. GitHub에서 새 저장소 생성 (예: `food-jobs`, **Public** — 무료 GitHub Pages는 공개 저장소에서 동작)
2. 이 폴더 전체를 올립니다.
   ```bash
   cd food-jobs
   git init && git add . && git commit -m "first commit"
   git branch -M main
   git remote add origin https://github.com/<아이디>/food-jobs.git
   git push -u origin main
   ```
   (명령어가 낯설면 GitHub 웹에서 *Add file → Upload files*로 폴더 내용을 끌어다 놓아도 됩니다. 단 `.github` 폴더도 꼭 함께 올리세요.)

### 3. 사이트 켜기 (GitHub Pages)

저장소 → **Settings → Pages → Build and deployment → Source: `GitHub Actions`** 선택

### 4. 인증키 등록 (Secrets)

저장소 → **Settings → Secrets and variables → Actions → New repository secret**

| Name | Secret |
|---|---|
| `DATA_GO_KR_KEY` | 공공데이터포털 일반 인증키(Decoding) |
| `WORK24_KEY` | 고용24 인증키 |
| `SARAMIN_KEY` | 사람인 access-key |

키는 GitHub에 암호화돼 저장되고, 사이트·로그에는 노출되지 않습니다 (오류 메시지에서도 가려짐).

### 5. 첫 실행

저장소 → **Actions → 채용공고 업데이트 → Run workflow**

- 끝나면 실행 결과 화면 아래 **Summary**에 출처별 수집 건수와 3일 내 마감 공고가 표로 나옵니다.
- 사이트 주소: `https://<아이디>.github.io/food-jobs/`
- 키 없이 화면만 먼저 보려면: `https://<아이디>.github.io/food-jobs/?demo=1` (예시 데이터)

이후로는 매일 06:17, 18:17에 자동으로 갱신됩니다. 수집이 전부 실패한 날은 Actions가 실패로 표시되고 GitHub이 메일로 알려줍니다 (사이트는 직전 데이터 유지).

---

## 사이트 기능

- **빠른 필터 카드**: 새 공고(최근 3일) · 3일 내 마감 · 신입 지원 가능
- **필터**: 기관 유형 / 직무 / 고용 형태 / 지역 / 출처 + 검색 — 각 항목 옆 숫자는 현재 조건에서의 건수
- **필터 링크 복사**: 고른 조건이 담긴 주소를 복사 → 학과 단톡방에 "신입 + R&D 공고" 링크로 공유
- **기업·기관 바로가기** 탭: 주요 식품기업 채용 홈페이지, 식품 관련 공공·연구기관, 채용 포털
- 휴대폰 화면·다크 모드 지원

### 분류 체계

| 구분 | 값 |
|---|---|
| 기관 유형 | 공기업·공공기관 / 정부출연·연구기관 / 대기업·주요 식품기업 / 외국계 / 중견·중소기업 / 병원·학교·복지기관 |
| 직무 | R&D·제품개발 / 품질·식품안전 / 영양사·급식·조리 / 생산·공정관리 / 인허가·RA / 영업·마케팅·MD / 구매·물류·SCM / 행정·사무 / 기타 |
| 고용 형태 | 정규직 / 무기계약직 / 계약직 / 인턴 / 파견·기타 |
| 경력 | 신입 / 신입·경력 / 경력 / 무관 |

---

## 고치고 싶을 때

| 하고 싶은 것 | 고칠 파일 |
|---|---|
| 검색 키워드 추가·삭제 | `collector/config.py` → `SARAMIN_KEYWORDS`, `WORK24_KEYWORDS` |
| 대기업·외국계 목록, 식품 관련 기관 목록 | `collector/config.py` → `BIG_FOOD_COMPANIES`, `FOREIGN_COMPANIES`, `FOOD_INSTITUTIONS` |
| 걸러낼 단순직 낱말 (배송·알바 등) | `collector/config.py` → `NOISE_KEYWORDS` |
| 직무 분류 규칙 | `collector/config.py` → `JOB_CATEGORIES` |
| 바로가기 탭의 기업·기관 | `docs/data/links.json` |
| 수집 시각 | `.github/workflows/update.yml` → `cron` (UTC 기준, 한국시간 −9시간) |

규칙을 바꾼 뒤에는 `python -m pytest -q`로 테스트를 돌려 보세요 (Actions에서도 매번 먼저 돌아갑니다).

## 내 컴퓨터에서 돌려보기

```bash
pip install -r requirements-dev.txt
python -m pytest -q                     # 테스트
python -m tests.make_sample             # 예시 데이터 다시 만들기 (docs/data/sample.json)
DATA_GO_KR_KEY=발급받은키 python -m collector.main   # 실제 수집 → docs/data/jobs.json
cd docs && python -m http.server 8000   # http://localhost:8000 에서 확인
```
(Windows PowerShell: `$env:DATA_GO_KR_KEY="발급받은키"; python -m collector.main`)

## 폴더 구조

```
collector/            수집·분류 (Python)
  config.py           키워드·기업 목록·분류 규칙  ← 주로 여기만 고치면 됨
  classify.py         분류 함수
  sources/            출처별 API 호출 (alio.py, work24.py, saramin.py)
  main.py             실행 진입점: 합치기·중복 제거·NEW 표시·마감 공고 제거
docs/                 사이트 (GitHub Pages로 배포)
  index.html          화면
  data/jobs.json      수집 결과 (Actions가 자동 갱신)
  data/sample.json    예시 데이터 (?demo=1)
  data/links.json     바로가기 탭 내용
tests/                테스트와 가짜 API 응답
.github/workflows/    자동 실행 설정
```

## 문제가 생기면

| 증상 | 확인할 것 |
|---|---|
| 잡알리오 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` | 승인 후 1~2시간 대기, Decoding 키를 넣었는지, 해당 API를 활용신청했는지 (공공데이터포털은 API마다 따로 신청) |
| 잡알리오 0건인데 오류 없음 | Actions 로그의 Summary 확인. API 응답 항목 이름이 바뀌었으면 `collector/sources/alio.py`의 필드명 수정 |
| 고용24 오류 | 기업회원 인증키인지, 심사 승인됐는지 |
| 사람인 오류 코드 2 / 4 | 2: 키 오류, 4: 일일 호출 한도 초과 → `config.py`에서 키워드 수나 `SARAMIN_MAX_PAGES` 줄이기 |
| 사이트가 안 바뀜 | Settings → Pages의 Source가 `GitHub Actions`인지, Actions 실행이 성공했는지 |
| 60일 넘게 자동 실행이 멈춤 | 공개 저장소는 활동이 없으면 예약 실행이 꺼질 수 있음 → Actions 탭에서 다시 Enable |

## 데이터 이용

- 각 출처의 이용 약관을 따릅니다. 사이트에는 제목·기관명·조건·마감일만 보여주고 **원문 공고로 연결**하며, 출처를 표시합니다.
- 자동 분류라 오분류가 있을 수 있으니 지원 전 원문을 꼭 확인하도록 안내하고 있습니다.
