"""수집 실행: python -m collector.main

환경변수(없는 소스는 건너뜀)
  DATA_GO_KR_KEY  공공데이터포털 일반 인증키(Decoding)  → 잡알리오(공공기관)
  WORK24_KEY      고용24 OPEN-API 인증키                 → 민간 전반
  SARAMIN_KEY     사람인 OPEN API access-key             → 대기업·식품기업
  SARAMIN_WEB=1   SARAMIN_KEY가 없을 때 사람인 검색 화면을 대신 읽음 (개인용, 키를 넣으면 자동으로 API 사용)
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import classify as C
from . import company as CO
from . import salary as S
from .http import mask
from .sources import alio, saramin, saramin_web, work24

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data" / "jobs.json"

SOURCES = [
    # (이름, 환경변수, 모듈, 화면 표시명, 키가 없을 때 대신 쓸 모듈과 그 스위치 환경변수)
    ("alio", "DATA_GO_KR_KEY", alio, "잡알리오(공공기관)", None),
    ("work24", "WORK24_KEY", work24, "고용24", None),
    ("saramin", "SARAMIN_KEY", saramin, "사람인", (saramin_web, "SARAMIN_WEB")),
]


def _norm(s: str) -> str:
    s = re.sub(r"\(주\)|㈜|주식회사|\(재\)|재단법인|\[[^\]]*\]|\([^)]*\)", "", s or "")
    return re.sub(r"[\s\W_]+", "", s).lower()


def load_previous(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def collect(out_path: Path = OUT, env=None, salary_path: Path | None = None,
            company_path: Path | None = None) -> dict:
    env = os.environ if env is None else env
    today = C.today_kst()
    prev = load_previous(out_path)
    prev_jobs = prev.get("jobs", [])
    prev_by_id = {j["id"]: j for j in prev_jobs}

    status, jobs = {}, []
    for name, env_name, mod, label, fallback in SOURCES:
        key = (env.get(env_name) or "").strip()
        mode = "api"
        if not key and fallback and (env.get(fallback[1]) or "").strip() == "1":
            mod, mode = fallback[0], "web"
        elif not key:
            status[name] = {"label": label, "state": "no_key", "count": 0,
                            "message": f"{env_name} 미설정 — 건너뜀"}
            continue
        try:
            raw = mod.fetch(key)
            items = [j for j in (mod.to_job(r) for r in raw) if j]
            if hasattr(mod, "enrich"):
                items = mod.enrich(items, prev_by_id, today)
            status[name] = {"label": label, "state": "ok", "raw": len(raw), "count": len(items),
                            "message": None, "mode": mode}
            if mode == "web":
                got = sum(1 for j in items if j.get("detail_checked"))
                status[name]["message"] = (f"{env_name} 없음 → 검색 화면에서 수집 (상세 확인 {got}/{len(items)}건)")
            if raw and isinstance(raw[0], dict):
                status[name]["fields"] = sorted(raw[0].keys())[:60]
        except Exception as e:  # 한 소스가 실패해도 나머지는 계속
            msg = mask(str(e), key)
            items = [j for j in prev_jobs if j.get("source") == name]
            status[name] = {"label": label, "state": "error", "count": len(items), "mode": mode,
                            "message": f"{msg[:300]} (이전 데이터 {len(items)}건 유지)"}
            print(f"[경고] {label}: {msg}", file=sys.stderr)
        jobs.extend(items)

    # 같은 공고가 여러 곳에 올라온 경우 하나로 (먼저 나온 소스 우선)
    merged: dict[str, dict] = {}
    for j in jobs:
        k = _norm(j["org"]) + "|" + _norm(j["title"])
        if k in merged:
            alt = merged[k].setdefault("also", [])
            if j["source"] != merged[k]["source"] and j["source"] not in [a["source"] for a in alt]:
                alt.append({"source": j["source"], "url": j["url"]})
            continue
        merged[k] = j

    today_s = today.isoformat()
    result = []
    for j in merged.values():
        if j.get("deadline") and j["deadline"] < today_s:
            continue  # 마감 지난 공고 제거
        j["first_seen"] = prev_by_id.get(j["id"], {}).get("first_seen") or today_s
        result.append(j)

    sal_table = S.load_public(salary_path or out_path.parent / "salary_public.json")
    with_salary = S.attach(result, sal_table, today)
    comp = CO.attach(result, today, fetch_new=(env.get("SARAMIN_WEB") or "").strip() == "1",
                     path=company_path or out_path.parent / "companies.json")

    result.sort(key=lambda j: (j.get("deadline") or "9999-99-99", -(int((j.get("posted") or "0").replace("-", "") or 0))))
    new_today = sum(1 for j in result if j["first_seen"] == today_s)
    data = {
        "updated_at": datetime.now(C.KST).strftime("%Y-%m-%d %H:%M"),
        "today": today_s,
        "sources": status,
        "total": len(result),
        "new_today": new_today,
        "salary": {"count": with_salary, "public_updated": sal_table.get("updated"),
                   "public_avg": S.averages(sal_table, today)},
        "company": {**comp, "count": sum(1 for j in result if j.get("company"))},
        "jobs": result,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def _summary(data: dict) -> str:
    lines = [f"## 식품 채용공고 수집 결과 ({data['updated_at']} KST)", "",
             f"- 전체 {data['total']}건 · 오늘 새로 들어온 공고 {data['new_today']}건",
             f"- 예상 연봉 표시 {data.get('salary', {}).get('count', 0)}건 "
             f"(알리오 신입 초임 표 갱신일 {data.get('salary', {}).get('public_updated') or '없음'})",
             f"- 회사 규모 표시 {data.get('company', {}).get('count', 0)}건 "
             f"(이번에 새로 받은 회사 {data.get('company', {}).get('fetched', 0)}곳)", "",
             "| 소스 | 상태 | 건수 | 메모 |", "|---|---|---|---|"]
    icon = {"ok": "✅", "error": "⚠️", "no_key": "⏸️"}
    for s in data["sources"].values():
        lines.append(f"| {s['label']} | {icon.get(s['state'], s['state'])} | {s['count']} | {s.get('message') or ''} |")
    soon = [j for j in data["jobs"] if j.get("deadline") and
            j["deadline"] <= (datetime.fromisoformat(data["today"]) + timedelta(days=3)).date().isoformat()]
    if soon:
        lines += ["", f"### 3일 안에 마감 ({len(soon)}건)"]
        lines += [f"- {j['deadline']} · {j['org']} — {j['title']}" for j in soon[:15]]
    return "\n".join(lines)


def main() -> int:
    st = S.refresh_public(C.today_kst())
    print(f"[연봉] 알리오 신입사원 초임 표: {st}")
    if st["state"] == "error":
        print(f"[경고] 알리오 신입사원 초임 표를 새로 받지 못했습니다: {st.get('message')}", file=sys.stderr)
    data = collect()
    text = _summary(data)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text + "\n")
    ok = any(s["state"] == "ok" for s in data["sources"].values())
    keys = any(s["state"] != "no_key" for s in data["sources"].values())
    if not keys:
        print("[안내] 인증키가 하나도 설정되지 않았습니다. README의 '인증키 등록'을 참고하세요.", file=sys.stderr)
    return 0 if ok or not keys else 1


if __name__ == "__main__":
    sys.exit(main())
