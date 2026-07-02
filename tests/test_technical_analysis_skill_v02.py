# encoding:utf-8
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import numpy as np


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


def test_v02_csi_index_symbol_uses_sh_prefixed_akshare_symbol(monkeypatch, tmp_path):
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
            "931250.CSI",
            output_dir=str(tmp_path),
            name="中证样例指数",
            asset_type="index",
            market="CSI",
            ts_code="931250.CSI",
        )

    assert captured["config"]["asset_type"] == "index"
    assert captured["config"]["data_func"] == "stock_zh_index_daily"
    assert captured["config"]["data_args"] == {"symbol": "sh931250"}
    assert captured["config"]["baostock_symbol"] == ""


def test_v02_short_csi_index_symbol_infers_index_and_h_prefixed_tushare(monkeypatch, tmp_path):
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
        module.run_analysis("20444.CSI", output_dir=str(tmp_path))

    assert captured["config"]["asset_type"] == "index"
    assert captured["config"]["data_func"] == "stock_zh_index_daily"
    assert captured["config"]["data_args"] == {"symbol": "sh20444"}
    assert captured["config"]["tushare_symbol"] == "H20444.CSI"


def test_v02_h_prefixed_csi_index_keeps_tushare_symbol_but_strips_h_for_akshare(monkeypatch, tmp_path):
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
        module.run_analysis("H20444.CSI", output_dir=str(tmp_path))

    assert captured["config"]["asset_type"] == "index"
    assert captured["config"]["data_args"] == {"symbol": "sh20444"}
    assert captured["config"]["tushare_symbol"] == "H20444.CSI"


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


def test_v02_probe_window_ranks_data_sources_by_latest_date(monkeypatch):
    module = _load_v02_skill_module()
    calls = []

    def frame(start, periods):
        return pd.DataFrame(
            {
                "date": pd.date_range(start, periods=periods, freq="D"),
                "open": range(periods),
                "high": range(1, periods + 1),
                "low": range(periods),
                "close": range(1, periods + 1),
                "volume": range(100, 100 + periods),
            }
        )

    monkeypatch.setattr(module, "_fetch_akshare_main", lambda _config: calls.append("akshare") or frame("2026-05-02", 60))
    monkeypatch.setattr(module, "_fetch_tushare_stock", lambda _symbol, _token: calls.append("tushare") or frame("2026-05-03", 60))
    monkeypatch.setattr(module, "_fetch_baostock_stock", lambda _symbol: calls.append("baostock") or frame("2026-05-01", 60))
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    monkeypatch.setenv("TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_START", "15:30")
    monkeypatch.setenv("TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_END", "18:00")
    monkeypatch.setenv("TECHNICAL_ANALYSIS_NOW", "2026-07-01T15:45:00+08:00")
    monkeypatch.setitem(sys.modules, "akshare", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "baostock", SimpleNamespace())

    df = module.fetch_data(
        {"data_func": "stock_zh_a_hist", "data_args": {"symbol": "600519"}},
        symbol_code="600519",
    )

    assert calls == ["akshare", "tushare", "baostock"]
    assert df["date"].max().strftime("%Y-%m-%d") == "2026-07-01"


def test_v02_on_demand_refetch_stops_after_good_first_source(monkeypatch):
    module = _load_v02_skill_module()
    calls = []

    def frame(start=1.0, step=0.01, periods=80):
        closes = [start + step * index for index in range(periods)]
        return pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=periods, freq="D"),
                "open": closes,
                "high": [value + 0.01 for value in closes],
                "low": [value - 0.01 for value in closes],
                "close": closes,
                "volume": range(100, 100 + periods),
            }
        )

    monkeypatch.setattr(module, "_fetch_akshare_main", lambda _config: calls.append("akshare") or frame())
    monkeypatch.setattr(module, "_fetch_tushare_stock", lambda _symbol, _token: calls.append("tushare") or frame())
    monkeypatch.setattr(module, "_fetch_baostock_stock", lambda _symbol: calls.append("baostock") or frame())
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    monkeypatch.setenv("TECHNICAL_ANALYSIS_NOW", "2026-07-01T12:00:00+08:00")
    monkeypatch.setitem(sys.modules, "akshare", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "baostock", SimpleNamespace())

    df = module.fetch_data(
        module._dynamic_config("600519", asset_type="a_share", market="SH", ts_code="600519.SH"),
        symbol_code="600519",
    )

    assert len(df) == 80
    assert calls == ["akshare"]


def test_v02_on_demand_refetch_tries_next_source_when_key_levels_poor(monkeypatch):
    module = _load_v02_skill_module()
    calls = []

    def frame(values):
        return pd.DataFrame(
            {
                "date": pd.date_range("2026-01-01", periods=len(values), freq="D"),
                "open": values,
                "high": [value + 0.01 for value in values],
                "low": [value - 0.01 for value in values],
                "close": values,
                "volume": range(100, 100 + len(values)),
            }
        )

    flat_values = [1.0] * 80
    trend_values = [1.0 + 0.01 * index for index in range(80)]
    monkeypatch.setattr(module, "_fetch_akshare_main", lambda _config: calls.append("akshare") or frame(flat_values))
    monkeypatch.setattr(module, "_fetch_tushare_stock", lambda _symbol, _token: calls.append("tushare") or frame(trend_values))
    monkeypatch.setattr(module, "_fetch_baostock_stock", lambda _symbol: calls.append("baostock") or frame(trend_values))
    monkeypatch.setenv("TUSHARE_TOKEN", "token")
    monkeypatch.setenv("TECHNICAL_ANALYSIS_NOW", "2026-07-01T12:00:00+08:00")
    monkeypatch.setitem(sys.modules, "akshare", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "baostock", SimpleNamespace())

    df = module.fetch_data(
        module._dynamic_config("600519", asset_type="a_share", market="SH", ts_code="600519.SH"),
        symbol_code="600519",
    )

    assert df["close"].iloc[-1] > df["close"].iloc[0]
    assert calls == ["akshare", "tushare"]


def test_v02_tushare_index_fallback_uses_index_daily(monkeypatch):
    module = _load_v02_skill_module()
    requested = []

    class FakePro:
        def index_daily(self, **kwargs):
            requested.append(kwargs)
            return pd.DataFrame(
                [
                    {
                        "trade_date": "20260701",
                        "open": 1,
                        "high": 2,
                        "low": 1,
                        "close": 2,
                        "vol": 100,
                    }
                ]
            )

    monkeypatch.setitem(sys.modules, "tushare", SimpleNamespace(pro_api=lambda _token: FakePro()))

    df = module._fetch_tushare_index("931250.CSI", "token")

    assert requested == [{"ts_code": "931250.CSI", "start_date": "20200101"}]
    assert df["date"].max().strftime("%Y-%m-%d") == "2026-07-01"


def test_v02_prepare_source_frame_normalizes_tushare_string_ohlcv():
    module = _load_v02_skill_module()

    df = module._prepare_source_frame(
        pd.DataFrame(
            [
                {
                    "trade_date": "20260701",
                    "open": "1234.56",
                    "high": "1240.00",
                    "low": "1200.10",
                    "close": "1230.50",
                    "vol": "123456",
                }
            ]
        )
    )

    assert df["date"].max().strftime("%Y-%m-%d") == "2026-07-01"
    for column in ["open", "high", "low", "close", "volume"]:
        assert np.issubdtype(df[column].dtype, np.floating)


def test_v02_prepare_source_frame_fills_close_only_index_ohlcv():
    module = _load_v02_skill_module()

    df = module._prepare_source_frame(
        pd.DataFrame(
            [
                {
                    "trade_date": "20260701",
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": "12330.0555",
                    "vol": None,
                }
            ]
        )
    )

    assert len(df) == 1
    assert df["date"].max().strftime("%Y-%m-%d") == "2026-07-01"
    assert df.loc[0, "open"] == pytest.approx(12330.0555)
    assert df.loc[0, "high"] == pytest.approx(12330.0555)
    assert df.loc[0, "low"] == pytest.approx(12330.0555)
    assert df.loc[0, "volume"] == pytest.approx(0.0)


def test_v02_prepare_source_frame_normalizes_akshare_chinese_string_ohlcv():
    module = _load_v02_skill_module()

    df = module._prepare_source_frame(
        pd.DataFrame(
            [
                {
                    "日期": "2026-07-01",
                    "开盘": "10.1",
                    "最高": "10.5",
                    "最低": "9.8",
                    "收盘": "10.3",
                    "成交量": "8888",
                }
            ]
        )
    )

    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert df["date"].max().strftime("%Y-%m-%d") == "2026-07-01"
    for column in ["open", "high", "low", "close", "volume"]:
        assert np.issubdtype(df[column].dtype, np.floating)


def test_v02_indicators_accept_string_open_array():
    script_dir = Path(__file__).resolve().parents[1] / "builtin" / "components" / "technical-analysis" / "scripts"
    sys.path.insert(0, str(script_dir))
    try:
        from indicators_lib import calc_all_indicators
    finally:
        sys.path.remove(str(script_dir))

    high = np.array(["2.0"] * 80, dtype=object)
    low = np.array(["1.0"] * 80, dtype=object)
    close = np.array(["1.5"] * 80, dtype=object)
    volume = np.array(["1000"] * 80, dtype=object)
    open_ = np.array(["1.2"] * 80, dtype=object)

    indicators = calc_all_indicators(high, low, close, volume, open_=open_)

    assert indicators.momentum.bop.shape == (80,)


@pytest.mark.parametrize(
    ("symbol", "asset_type", "market", "ts_code", "expected"),
    [
        (
            "931250.CSI",
            "index",
            "CSI",
            "931250.CSI",
            {
                "akshare_args": {"symbol": "sh931250"},
                "baostock_symbol": "",
                "tushare_api": "index_daily",
                "tushare_symbol": "931250.CSI",
            },
        ),
        (
            "600519",
            "a_share",
            "SH",
            "600519.SH",
            {
                "akshare_args": {"symbol": "600519", "period": "daily", "adjust": "qfq"},
                "baostock_symbol": "sh.600519",
                "tushare_api": "daily",
                "tushare_symbol": "600519.SH",
            },
        ),
        (
            "510300.SH",
            "etf",
            "SH",
            "510300.SH",
            {
                "akshare_args": {"symbol": "sh510300"},
                "baostock_symbol": "sh.510300",
                "tushare_api": "fund_daily",
                "tushare_symbol": "510300.SH",
            },
        ),
        (
            "00700.HK",
            "hk_stock",
            "HK",
            "00700.HK",
            {
                "akshare_args": {"symbol": "00700"},
                "baostock_symbol": "",
                "tushare_api": "hk_daily",
                "tushare_symbol": "00700.HK",
            },
        ),
        (
            "AAPL.US",
            "us_stock",
            "US",
            "AAPL.US",
            {
                "akshare_args": {"symbol": "AAPL"},
                "baostock_symbol": "",
                "tushare_api": "us_daily",
                "tushare_symbol": "AAPL",
            },
        ),
        (
            "111009.SH",
            "convertible_bond",
            "SH",
            "111009.SH",
            {
                "akshare_args": {"symbol": "sh111009"},
                "baostock_symbol": "",
                "tushare_api": "cb_daily",
                "tushare_symbol": "111009.SH",
            },
        ),
        (
            "T0",
            "futures",
            "CFFEX",
            "T0",
            {
                "akshare_args": {"symbol": "T0"},
                "baostock_symbol": "",
                "tushare_api": "fut_daily",
                "tushare_symbol": "T.CFX",
            },
        ),
    ],
)
def test_v02_provider_symbol_plan_centralizes_symbol_and_api_adaptation(
    symbol, asset_type, market, ts_code, expected
):
    module = _load_v02_skill_module()
    config = module._dynamic_config(symbol, asset_type=asset_type, market=market, ts_code=ts_code)

    plan = module._provider_symbol_plan(config, symbol_code=symbol)

    assert plan["akshare_args"] == expected["akshare_args"]
    assert plan["baostock_symbol"] == expected["baostock_symbol"]
    assert plan["tushare_api"] == expected["tushare_api"]
    assert plan["tushare_symbol"] == expected["tushare_symbol"]
