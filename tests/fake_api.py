"""테스트·예시 데이터용 가짜 API 응답."""
import json
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


class FakeResp:
    def __init__(self, text):
        self.text = text

    def json(self):
        return json.loads(self.text)


def fake_get(url, params, **kw):
    if "apis.data.go.kr" in url:
        return FakeResp((FIX / "alio.json").read_text(encoding="utf-8"))
    if "work24" in url:
        if params.get("coTp") in ("04", "05"):
            return FakeResp("<wantedRoot><total>0</total></wantedRoot>")
        name = "work24_cotp.xml" if params.get("coTp") == "01" else "work24.xml"
        return FakeResp((FIX / name).read_text(encoding="utf-8"))
    if "saramin" in url:
        return FakeResp((FIX / "saramin.json").read_text(encoding="utf-8"))
    raise AssertionError(url)


def patch_all(monkeypatch_or_none=None):
    """pytest monkeypatch 또는 None(직접 교체)."""
    from collector.sources import alio, saramin, work24
    for mod in (alio, work24, saramin):
        if monkeypatch_or_none:
            monkeypatch_or_none.setattr(mod, "get", fake_get)
        else:
            mod.get = fake_get


FAKE_ENV = {"DATA_GO_KR_KEY": "TESTKEY%2B==", "WORK24_KEY": "W24KEY", "SARAMIN_KEY": "SRKEY"}
