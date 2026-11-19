"""공통 HTTP 도우미 — 재시도, 타임아웃, 오류 메시지에서 인증키 가리기."""
from __future__ import annotations

import re
import time

import requests

UA = "food-jobs-collector/1.0 (+https://github.com)"


class SourceError(RuntimeError):
    pass


def mask(text: str, *secrets: str) -> str:
    text = str(text)
    for s in secrets:
        if s:
            text = text.replace(s, "***")
            text = text.replace(requests.utils.quote(s, safe=""), "***")
    return re.sub(r"(serviceKey|authKey|access-key)=[^&\s]+", r"\1=***", text)


def get(url: str, params: dict, *, headers: dict | None = None, secrets=(), retries: int = 3,
        timeout: int = 25) -> requests.Response:
    h = {"User-Agent": UA}
    h.update(headers or {})
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=h, timeout=timeout)
            if r.status_code >= 500 or r.status_code == 429:
                raise SourceError(f"HTTP {r.status_code}")
            if r.status_code >= 400:
                raise SourceError(f"HTTP {r.status_code}: {r.text[:200]}")
            return r
        except (requests.RequestException, SourceError) as e:
            last = e
            if isinstance(e, SourceError) and "HTTP 4" in str(e) and "429" not in str(e):
                break
            time.sleep(2 * (attempt + 1))
    raise SourceError(mask(f"{url} 요청 실패: {last}", *secrets))
