# encoding:utf-8
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


def _load_v02_skill_module():
    script = (
        Path(__file__).resolve().parents[1]
        / "builtin"
        / "components"
        / "technical-analysis"
        / "scripts"
        / "analyze_universal.py"
    )
    if not script.is_file():
        pytest.skip(f"technical analysis component script is not tracked in this checkout: {script}")
    sys.path.insert(0, str(script.parent))
    spec = importlib.util.spec_from_file_location("technical_analysis_v02_under_test", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v02_tushare_fallback_infers_a_share_suffix_from_code_prefix(monkeypatch):
    module = _load_v02_skill_module()
    requested = []

    class FakePro:
        def daily(self, **kwargs):
            requested.append(kwargs["ts_code"])
            return pd.DataFrame(
                [
                    {
                        "trade_date": "20260608",
                        "open": 1,
                        "high": 2,
                        "low": 1,
                        "close": 2,
                        "vol": 100,
                    }
                ]
            )

    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda _token: FakePro()))

    module._fetch_tushare_stock("300502", "token")
    module._fetch_tushare_stock("600519", "token")

    assert requested == ["300502.SZ", "600519.SH"]
