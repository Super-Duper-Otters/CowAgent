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


def test_v02_tl0_uses_bond_futures_akshare_preset(monkeypatch):
    module = _load_v02_skill_module()
    requested = []

    def fake_futures_zh_daily_sina(**kwargs):
        requested.append(kwargs)
        return pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=60, freq="D"),
                "open": range(60),
                "high": range(1, 61),
                "low": range(60),
                "close": range(1, 61),
                "volume": range(100, 160),
            }
        )

    monkeypatch.setitem(
        sys.modules,
        "akshare",
        SimpleNamespace(futures_zh_daily_sina=fake_futures_zh_daily_sina),
    )

    config = module.PRESET_CONFIGS["TL0"]
    df = module.fetch_data(config, symbol_code="TL0")

    assert config["asset_type"] == "futures"
    assert config["data_func"] == "futures_zh_daily_sina"
    assert requested == [{"symbol": "TL0"}]
    assert len(df) == 60


def test_v02_normalizes_common_akshare_chinese_ohlcv_columns():
    module = _load_v02_skill_module()

    df = module._normalize_columns(
        pd.DataFrame(
            {
                "日期": ["2026-01-01"],
                "开盘": [1.0],
                "最高": [2.0],
                "最低": [0.5],
                "收盘": [1.5],
                "成交量": [1000],
            }
        )
    )

    assert ["date", "open", "high", "low", "close", "volume"] == list(df.columns)


def test_v02_dynamic_index_symbol_uses_index_daily_interface(monkeypatch, tmp_path):
    module = _load_v02_skill_module()
    captured = {}

    class StopAfterConfig(Exception):
        pass

    def fake_fetch_data(config, symbol_code=None):
        captured["config"] = config
        captured["symbol_code"] = symbol_code
        raise StopAfterConfig()

    monkeypatch.setattr(module, "fetch_data", fake_fetch_data)

    with pytest.raises(StopAfterConfig):
        module.run_analysis("sh000852", output_dir=str(tmp_path))

    assert captured["symbol_code"] == "sh000852"
    assert captured["config"]["asset_type"] == "index"
    assert captured["config"]["data_func"] == "stock_zh_index_daily"
    assert captured["config"]["data_args"] == {"symbol": "sh000852"}


@pytest.mark.parametrize(
    ("symbol", "asset_type", "market", "ts_code", "expected_name", "expected_func", "expected_args"),
    [
        ("510300", "etf", "SH", "510300.SH", "沪深300ETF", "fund_etf_hist_sina", {"symbol": "sh510300"}),
        ("HK00700", "hk_stock", "HK", "00700.HK", "腾讯控股", "stock_hk_daily", {"symbol": "00700"}),
        ("AAPL.US", "us_stock", "US", "AAPL", "苹果", "stock_us_daily", {"symbol": "AAPL"}),
        ("113000", "convertible_bond", "SH", "113000.SH", "可转债样例", "bond_zh_hs_cov_daily", {"symbol": "sh113000"}),
    ],
)
def test_v02_explicit_asset_metadata_selects_daily_interface(
    monkeypatch, tmp_path, symbol, asset_type, market, ts_code, expected_name, expected_func, expected_args
):
    module = _load_v02_skill_module()
    captured = {}

    class StopAfterConfig(Exception):
        pass

    def fake_fetch_data(config, symbol_code=None):
        captured["config"] = config
        captured["symbol_code"] = symbol_code
        raise StopAfterConfig()

    monkeypatch.setattr(module, "fetch_data", fake_fetch_data)

    with pytest.raises(StopAfterConfig):
        module.run_analysis(
            symbol,
            output_dir=str(tmp_path),
            name=expected_name,
            asset_type=asset_type,
            market=market,
            ts_code=ts_code,
        )

    assert captured["symbol_code"] == symbol
    assert captured["config"]["name"] == expected_name
    assert captured["config"]["name_short"] == expected_name
    assert captured["config"]["asset_type"] == asset_type
    assert captured["config"]["data_func"] == expected_func
    assert captured["config"]["data_args"] == expected_args


def test_v02_report_header_uses_latest_data_date_not_system_date():
    script = (
        Path(__file__).resolve().parents[1]
        / "builtin"
        / "components"
        / "technical-analysis"
        / "scripts"
        / "analyze_universal.py"
    )
    source = script.read_text(encoding="utf-8")

    assert "latest_data_date = df['date'].iloc[-1].date()" in source
    assert '"**分析日期:** {TODAY}' not in source
    assert "**分析日期:** {latest_data_date}" in source
