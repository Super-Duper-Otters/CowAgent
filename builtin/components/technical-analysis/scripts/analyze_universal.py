# -*- coding: utf-8 -*-
"""
通用技术形态分析脚本
==================
支持任意标的：国债期货、股票、指数、ETF等
只需修改底部的 SYMBOL_CONFIG 配置即可

用法:
    python analyze_universal.py                        # 使用默认配置
    python analyze_universal.py --symbol T0 --name "十年国债期货"
    python analyze_universal.py --config "custom_config"
"""

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import talib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
import sys
import argparse
import glob
import re
from datetime import datetime

# 字体配置
plt.rcParams['font.sans-serif'] = [
    'SimHei',
    'Microsoft YaHei',
    'Noto Sans CJK SC',
    'Source Han Sans SC',
    'WenQuanYi Micro Hei',
    'WenQuanYi Zen Hei',
    'Arial Unicode MS',
]
plt.rcParams['axes.unicode_minus'] = False


# ==================== K线形态详图绘制函数 ====================
# 共享绑图工具
from chart_helpers import _plot_pattern_detail

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..', '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# ==================== 预设标的配置 ====================

PRESET_CONFIGS = {
    # ---------- 国债期货 ----------
    'T0': {
        'name': '十年国债期货（T主力）',
        'name_short': 'T0',
        'asset_type': 'futures',
        'data_func': 'futures_zh_daily_sina',
        'data_args': {'symbol': 'T0'},
        'price_decimal': 3,  # 价格小数位
        'volume_unit': '手',
        'color_theme': '#1E88E5',  # 蓝色系（债市偏多）
    },
    'TL0': {
        'name': '三十年国债期货（TL主力）',
        'name_short': 'TL0',
        'asset_type': 'futures',
        'data_func': 'futures_zh_daily_sina',
        'data_args': {'symbol': 'TL0'},
        'price_decimal': 3,
        'volume_unit': '手',
        'color_theme': '#1565C0',
    },
    'TF0': {
        'name': '五年国债期货（TF主力）',
        'name_short': 'TF0',
        'asset_type': 'futures',
        'data_func': 'futures_zh_daily_sina',
        'data_args': {'symbol': 'TF0'},
        'price_decimal': 4,
        'volume_unit': '手',
        'color_theme': '#43A047',
    },
    'TS0': {
        'name': '二年国债期货（TS主力）',
        'name_short': 'TS0',
        'asset_type': 'futures',
        'data_func': 'futures_zh_daily_sina',
        'data_args': {'symbol': 'TS0'},
        'price_decimal': 4,
        'volume_unit': '手',
        'color_theme': '#FB8C00',
    },

    # ---------- A股指数 ----------
    'sh000001': {
        'name': '上证综指',
        'name_short': '上证指数',
        'asset_type': 'index',
        'data_func': 'stock_zh_index_daily',
        'data_args': {'symbol': 'sh000001'},
        'price_decimal': 2,
        'volume_unit': '手',
        'color_theme': '#E53935',
    },
    'sz399001': {
        'name': '深证成指',
        'name_short': '深成指',
        'asset_type': 'index',
        'data_func': 'stock_zh_index_daily',
        'data_args': {'symbol': 'sz399001'},
        'price_decimal': 2,
        'volume_unit': '手',
        'color_theme': '#8E24AA',
    },
    'sz399639': {
        'name': '深证AI产业指数',
        'name_short': 'AI指数',
        'asset_type': 'index',
        'data_func': 'stock_zh_index_daily',
        'data_args': {'symbol': 'sz399639'},
        'price_decimal': 2,
        'volume_unit': '手',
        'color_theme': '#00ACC1',
    },
    'sh000300': {
        'name': '沪深300',
        'name_short': '沪深300',
        'asset_type': 'index',
        'data_func': 'stock_zh_index_daily',
        'data_args': {'symbol': 'sh000300'},
        'price_decimal': 2,
        'volume_unit': '手',
        'color_theme': '#5E35B1',
    },

    # ---------- A股个股 ----------
    '000001': {
        'name': '平安银行',
        'name_short': '000001',
        'asset_type': 'stock',
        'data_func': 'stock_zh_a_hist',
        'data_args': {'symbol': '000001', 'period': 'daily', 'adjust': 'qfq'},
        'price_decimal': 2,
        'volume_unit': '手',
        'color_theme': '#F4511E',
    },
    '600519': {
        'name': '贵州茅台',
        'name_short': '茅台',
        'asset_type': 'stock',
        'data_func': 'stock_zh_a_hist',
        'data_args': {'symbol': '600519', 'period': 'daily', 'adjust': 'qfq'},
        'price_decimal': 2,
        'volume_unit': '手',
        'color_theme': '#7CB342',
    },
}

# 默认配置
DEFAULT_CONFIG = 'T0'


# ==================== 数据获取（多源自动切换） ====================

def _normalize_columns(df):
    """统一列名为小写 date/open/high/low/close/volume"""
    df.columns = [str(c).lower().strip() for c in df.columns]
    df = df.rename(
        columns={
            '日期': 'date',
            '时间': 'date',
            'trade_date': 'date',
            '开盘': 'open',
            '最高': 'high',
            '最低': 'low',
            '收盘': 'close',
            '成交量': 'volume',
            'vol': 'volume',
        }
    )
    if 'volume' not in df.columns:
        for vol_col in ['hold']:
            if vol_col in df.columns:
                df = df.rename(columns={vol_col: 'volume'})
                break
    if 'volume' not in df.columns:
        df['volume'] = 0
    for col in ['date', 'open', 'high', 'low', 'close', 'volume']:
        if col not in df.columns:
            raise ValueError(f"数据缺少必要列: {col}，实际列: {df.columns.tolist()}")
    return df


def _fetch_akshare_main(config):
    """数据源 1: AKShare 主接口"""
    import akshare as ak
    func_name = config['data_func']
    args = config['data_args'].copy()
    if not hasattr(ak, func_name):
        raise ValueError(f"AKShare 无此接口: {func_name}")
    func = getattr(ak, func_name)
    df = func(**args)
    normalized_columns = [str(c).lower().strip() for c in df.columns]
    if 'open' in normalized_columns:
        col_map = {c: str(c).lower().strip() for c in df.columns}
        df = df.rename(columns=col_map)
    df.columns = [str(c).lower().strip() for c in df.columns]
    return df


def _fetch_tushare_stock(symbol, api):
    """数据源 2: Tushare 日线（股票/指数）"""
    import tushare as ts
    pro = ts.pro_api(api)
    ts_code = _tushare_daily_symbol(symbol)
    df = pro.daily(ts_code=ts_code, start_date='20200101')
    df = df.rename(columns={'trade_date': 'date', 'vol': 'volume'})
    df['date'] = pd.to_datetime(df['date'])
    return df


def _fetch_tushare_index(symbol, api):
    """数据源 2: Tushare 指数日线"""
    import tushare as ts
    pro = ts.pro_api(api)
    ts_code = symbol.upper()
    df = pro.index_daily(ts_code=ts_code, start_date='20200101')
    df = df.rename(columns={'trade_date': 'date', 'vol': 'volume'})
    df['date'] = pd.to_datetime(df['date'])
    return df


def _fetch_tushare_api(symbol, api, api_name):
    """Tushare dedicated daily-like API by asset type."""
    import tushare as ts
    pro = ts.pro_api(api)
    func = getattr(pro, api_name)
    df = func(ts_code=symbol, start_date='20200101')
    df = df.rename(columns={'trade_date': 'date', 'vol': 'volume'})
    df['date'] = pd.to_datetime(df['date'])
    return df


def _fetch_baostock_stock(code):
    """数据源 3: BaoStock 日线"""
    import baostock as bs
    lg = bs.login()
    if lg.error_code != '0':
        raise RuntimeError(f"baostock login failed: {lg.error_msg}")
    rs = bs.query_history_k_data_plus(code,
        "date,open,high,low,close,volume",
        start_date='2020-01-01', frequency="d", adjustflag="3")
    rows = []
    while rs.next():
        row = rs.get_row_data()
        if row[0] and row[4]:
            rows.append(row)
    bs.logout()
    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0)
    for col in ['open', 'high', 'low', 'close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['close']).reset_index(drop=True)
    return df


def _baostock_symbol(value, market=''):
    prefixed = _prefixed_code(value, market)
    if re.fullmatch(r'(sh|sz|bj)\d{6}', prefixed, flags=re.IGNORECASE):
        return f'{prefixed[:2].lower()}.{prefixed[2:]}'
    return str(value or '').strip()


def _parse_hh_mm(value, fallback):
    match = re.fullmatch(r'([01]\d|2[0-3]):([0-5]\d)', str(value or '').strip())
    if not match:
        return fallback
    return int(match.group(1)), int(match.group(2))


def _technical_analysis_now():
    raw = os.environ.get('TECHNICAL_ANALYSIS_NOW', '').strip()
    if raw:
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return datetime.now()


def _source_date_ranking_enabled():
    start_hour, start_minute = _parse_hh_mm(
        os.environ.get('TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_START', '15:30'),
        (15, 30),
    )
    end_hour, end_minute = _parse_hh_mm(
        os.environ.get('TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_END', '18:00'),
        (18, 0),
    )
    current = _technical_analysis_now().time()
    start = current.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end = current.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    return start <= current <= end


def _trading_calendar_filter_enabled():
    value = os.environ.get('TECHNICAL_ANALYSIS_TRADING_CALENDAR_ENABLED', '').strip().lower()
    return value in {'1', 'true', 'yes', 'on'}


def _accepted_market_dates():
    if not _trading_calendar_filter_enabled():
        return set()
    raw_dates = os.environ.get('TECHNICAL_ANALYSIS_ACCEPTED_MARKET_DATES', '')
    dates = set()
    for item in raw_dates.split(','):
        normalized = _normalize_market_date(item)
        if normalized:
            dates.add(normalized)
    return dates


def _normalize_market_date(value):
    text = str(value or '').strip()
    if not text:
        return ''
    try:
        return pd.to_datetime(text, errors='raise').date().isoformat()
    except Exception:
        return ''


def _market_date_allowed(latest_date, accepted_dates=None):
    if not _trading_calendar_filter_enabled():
        return True
    accepted = accepted_dates if accepted_dates is not None else _accepted_market_dates()
    if not accepted:
        return True
    normalized = _normalize_market_date(latest_date)
    return normalized in accepted


def _max_stale_market_days():
    raw = os.environ.get('TECHNICAL_ANALYSIS_MAX_STALE_MARKET_DAYS', '15')
    try:
        return max(0, int(raw))
    except Exception:
        return 15


def _market_date_stale_fallback_allowed(latest_date):
    normalized = _normalize_market_date(latest_date)
    if not normalized:
        return False
    try:
        market_day = pd.to_datetime(normalized, errors='raise').date()
        reference_text = _normalize_market_date(os.environ.get('TECHNICAL_ANALYSIS_EXPECTED_MARKET_DATE', ''))
        reference_day = pd.to_datetime(reference_text, errors='raise').date() if reference_text else _technical_analysis_now().date()
    except Exception:
        return False
    age_days = (reference_day - market_day).days
    return 0 <= age_days <= _max_stale_market_days()


def _select_stale_source_candidate(candidates, errors):
    allowed = []
    for candidate in candidates:
        if _market_date_stale_fallback_allowed(candidate['latest_date']):
            allowed.append(candidate)
            continue
        latest_label = _normalize_market_date(candidate['latest_date']) or str(candidate['latest_date'])
        errors.append(
            f"{candidate['source_name']}: 最新日期 {latest_label} 超过最大允许滞后 {_max_stale_market_days()} 天"
        )
    return _select_usable_source_candidate(allowed)


def _load_tushare_token():
    tushare_token = os.environ.get('TUSHARE_TOKEN', '')
    token_file = os.path.expanduser('~/.tushare_token')
    if not tushare_token and os.path.exists(token_file):
        with open(token_file, 'r') as f:
            tushare_token = f.read().strip()
    return tushare_token


def _prepare_source_frame(df):
    df = _normalize_columns(df)
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    for column in ['open', 'high', 'low', 'close', 'volume']:
        df[column] = pd.to_numeric(df[column], errors='coerce').astype('float64')
    df = df.dropna(subset=['date', 'close'])
    for column in ['open', 'high', 'low']:
        df[column] = df[column].fillna(df['close']).astype('float64')
    df['volume'] = df['volume'].fillna(0).astype('float64')
    return df.drop_duplicates(subset='date').sort_values('date').reset_index(drop=True)


def _key_level_quality(df):
    """Return whether MA/BOLL references can provide both support and resistance."""
    if df is None or len(df) < 60 or 'close' not in df.columns:
        return False, '数据量不足，无法评估关键位质量'
    close = pd.to_numeric(df['close'], errors='coerce').dropna()
    if len(close) < 60:
        return False, '有效收盘价不足，无法评估关键位质量'
    last_close = float(close.iloc[-1])
    candidates = []
    for window in (5, 10, 20, 60):
        value = float(close.rolling(window).mean().iloc[-1])
        if np.isfinite(value):
            candidates.append(value)
    middle = close.rolling(20).mean()
    std = close.rolling(20).std()
    for value in (middle.iloc[-1] + 2 * std.iloc[-1], middle.iloc[-1], middle.iloc[-1] - 2 * std.iloc[-1]):
        value = float(value)
        if np.isfinite(value):
            candidates.append(value)
    unique = []
    for value in candidates:
        if not any(abs(value - existing) / max(abs(existing), 1e-9) < 0.001 for existing in unique):
            unique.append(value)
    resistances = [value for value in unique if value > last_close]
    supports = [value for value in unique if value <= last_close]
    if resistances and supports:
        return True, f'关键位完整：压力 {len(resistances)} 个，支撑 {len(supports)} 个'
    missing = []
    if not resistances:
        missing.append('无明显压力')
    if not supports:
        missing.append('无明显支撑')
    return False, '、'.join(missing)


def _select_usable_source_candidate(candidates):
    if not candidates:
        return None
    good = [item for item in candidates if item.get('quality_ok')]
    pool = good or candidates
    return max(pool, key=lambda item: (item['latest_date'], item['rows']))


def _source_candidate(source_name, df, latest_date):
    quality_ok, quality_detail = _key_level_quality(df)
    return {
        'latest_date': latest_date,
        'source_name': source_name,
        'df': df,
        'rows': len(df),
        'quality_ok': quality_ok,
        'quality_detail': quality_detail,
    }


def _fetch_data_ranked_by_latest_date(config, symbol_code=None):
    errors = []
    candidates = []
    stale_candidates = []
    accepted_dates = _accepted_market_dates()

    def add_candidate(source_name, df):
        df = _prepare_source_frame(df)
        if len(df) >= 60:
            latest_date = df['date'].max()
            candidate = _source_candidate(source_name, df, latest_date)
            if not _market_date_allowed(latest_date, accepted_dates):
                latest_label = _normalize_market_date(latest_date) or str(latest_date)
                expected_label = os.environ.get('TECHNICAL_ANALYSIS_EXPECTED_MARKET_DATE', '').strip()
                detail = f"{source_name}: 最新日期 {latest_label} 不在交易日历允许范围"
                if expected_label:
                    detail += f"（预期 {expected_label}）"
                errors.append(detail)
                stale_candidates.append(candidate)
                print(f"  日期过旧: {detail}")
                return
            candidates.append(candidate)
            quality_label = '质量通过' if candidate['quality_ok'] else f"质量不足: {candidate['quality_detail']}"
            print(f"  候选: {source_name} {len(df)} 条，最新日期 {latest_date.date()}，{quality_label}")
            return
        errors.append(f"{source_name}: 数据量不足 ({len(df)} < 60)")
        print(f"  数据量不足: {len(df)} < 60")

    try:
        import akshare as ak
        print(f"[数据源1/3] AKShare: {config['data_func']} ...")
        add_candidate("AKShare", _fetch_akshare_main(config))
    except Exception as e:
        errors.append(f"AKShare: {e}")
        print(f"  失败: {e}")

    try:
        import tushare as ts
        tushare_token = _load_tushare_token()
        plan = _provider_symbol_plan(config, symbol_code=symbol_code)
        if tushare_token and plan['tushare_symbol']:
            print(f"[数据源2/3] Tushare: {plan['tushare_symbol']} ...")
            if plan['tushare_api'] == 'index_daily':
                add_candidate("Tushare", _fetch_tushare_index(plan['tushare_symbol'], tushare_token))
            elif plan['tushare_api'] == 'daily':
                add_candidate("Tushare", _fetch_tushare_stock(plan['tushare_symbol'], tushare_token))
            else:
                add_candidate("Tushare", _fetch_tushare_api(plan['tushare_symbol'], tushare_token, plan['tushare_api']))
        else:
            print("  未尝试: 未配置 TUSHARE_TOKEN 或该源适配代码")
            errors.append("Tushare: 未配置访问凭据或适配代码")
    except ImportError:
        errors.append("Tushare: 未安装")
        print("  不可用: tushare 未安装")
    except Exception as e:
        errors.append(f"Tushare: {e}")
        print(f"  失败: {e}")

    try:
        plan = _provider_symbol_plan(config, symbol_code=symbol_code)
        if plan['baostock_symbol']:
            print(f"[数据源3/3] BaoStock: {plan['baostock_symbol']} ...")
            bs_code = plan['baostock_symbol']
            add_candidate("BaoStock", _fetch_baostock_stock(bs_code))
        else:
            errors.append("BaoStock: 未配置该源适配代码")
            print("  未尝试: 未配置 BaoStock 适配代码")
    except ImportError:
        errors.append("BaoStock: 未安装")
        print("  不可用: baostock 未安装")
    except Exception as e:
        errors.append(f"BaoStock: {e}")
        print(f"  失败: {e}")

    selected = _select_usable_source_candidate(candidates)
    if selected:
        quality_label = '质量通过' if selected['quality_ok'] else f"质量不足但已是最佳可用: {selected['quality_detail']}"
        print(f"  选择: {selected['source_name']}，最新日期 {selected['latest_date'].date()}，{selected['rows']} 条，{quality_label}")
        return selected['df']
    stale_selected = _select_stale_source_candidate(stale_candidates, errors)
    if stale_selected:
        quality_label = '质量通过' if stale_selected['quality_ok'] else f"质量不足但已是最新可用: {stale_selected['quality_detail']}"
        print(
            f"  交易日历严格校验无匹配数据，降级选择最新可用: "
            f"{stale_selected['source_name']}，最新日期 {stale_selected['latest_date'].date()}，"
            f"{stale_selected['rows']} 条，{quality_label}"
        )
        return stale_selected['df']

    print("\n所有数据源均失败，错误详情：")
    for i, err in enumerate(errors, 1):
        print(f"  {i}. {err}")
    raise RuntimeError(f"所有数据源失败: {errors}")


def fetch_data(config, symbol_code=None):
    """
    根据配置获取数据（多源自动切换）。
    优先级: AKShare 主接口 → Tushare → BaoStock

    Parameters
    ----------
    config : dict
        标的配置
    symbol_code : str, optional
        标的代码（用于 Tushare/BaoStock fallback）

    Returns
    -------
    pd.DataFrame with columns [date, open, high, low, close, volume]
    """
    if _source_date_ranking_enabled():
        return _fetch_data_ranked_by_latest_date(config, symbol_code=symbol_code)

    errors = []
    candidates = []
    stale_candidates = []
    accepted_dates = _accepted_market_dates()

    def accept_or_continue(source_name, df):
        df = _prepare_source_frame(df)
        if len(df) < 60:
            errors.append(f"{source_name}: 数据量不足 ({len(df)} < 60)")
            print(f"  数据量不足: {len(df)} < 60")
            return None
        latest_date = df['date'].max()
        candidate = _source_candidate(source_name, df, latest_date)
        if not _market_date_allowed(latest_date, accepted_dates):
            latest_label = _normalize_market_date(latest_date) or str(latest_date)
            expected_label = os.environ.get('TECHNICAL_ANALYSIS_EXPECTED_MARKET_DATE', '').strip()
            detail = f"{source_name}: 最新日期 {latest_label} 不在交易日历允许范围"
            if expected_label:
                detail += f"（预期 {expected_label}）"
            errors.append(detail)
            stale_candidates.append(candidate)
            print(f"  日期过旧: {detail}")
            return None
        candidates.append(candidate)
        if candidate['quality_ok']:
            print(f"  成功: {len(df)} 条，质量通过: {candidate['quality_detail']}")
            return df
        print(f"  数据可用但关键位质量不足: {candidate['quality_detail']}，尝试下一数据源")
        return None

    # --- 源 1: AKShare 主接口 ---
    try:
        import akshare as ak
        print(f"[数据源1/3] AKShare: {config['data_func']} ...")
        df = _fetch_akshare_main(config)
        accepted = accept_or_continue("AKShare", df)
        if accepted is not None:
            return accepted
    except Exception as e:
        errors.append(f"AKShare: {e}")
        print(f"  失败: {e}")

    # --- 源 2: Tushare ---
    try:
        import tushare as ts
        tushare_token = _load_tushare_token()
        plan = _provider_symbol_plan(config, symbol_code=symbol_code)
        if tushare_token and plan['tushare_symbol']:
            print(f"[数据源2/3] Tushare: {plan['tushare_symbol']} ...")
            if plan['tushare_api'] == 'index_daily':
                df = _fetch_tushare_index(plan['tushare_symbol'], tushare_token)
            elif plan['tushare_api'] == 'daily':
                df = _fetch_tushare_stock(plan['tushare_symbol'], tushare_token)
            else:
                df = _fetch_tushare_api(plan['tushare_symbol'], tushare_token, plan['tushare_api'])
            accepted = accept_or_continue("Tushare", df)
            if accepted is not None:
                return accepted
        else:
            print("  未尝试: 未配置 TUSHARE_TOKEN 或该源适配代码")
            errors.append("Tushare: 未配置访问凭据或适配代码")
    except ImportError:
        errors.append("Tushare: 未安装")
        print("  不可用: tushare 未安装")
    except Exception as e:
        errors.append(f"Tushare: {e}")
        print(f"  失败: {e}")

    # --- 源 3: BaoStock ---
    try:
        plan = _provider_symbol_plan(config, symbol_code=symbol_code)
        if plan['baostock_symbol']:
            print(f"[数据源3/3] BaoStock: {plan['baostock_symbol']} ...")
            bs_code = plan['baostock_symbol']
            df = _fetch_baostock_stock(bs_code)
            accepted = accept_or_continue("BaoStock", df)
            if accepted is not None:
                return accepted
        else:
            errors.append("BaoStock: 未配置该源适配代码")
            print("  未尝试: 未配置 BaoStock 适配代码")
    except ImportError:
        errors.append("BaoStock: 未安装")
        print("  不可用: baostock 未安装")
    except Exception as e:
        errors.append(f"BaoStock: {e}")
        print(f"  失败: {e}")

    selected = _select_usable_source_candidate(candidates)
    if selected:
        print(
            f"  所有可用数据源关键位质量均不足，选择最佳可用: "
            f"{selected['source_name']}，最新日期 {selected['latest_date'].date()}，"
            f"{selected['rows']} 条，{selected['quality_detail']}"
        )
        return selected['df']
    stale_selected = _select_stale_source_candidate(stale_candidates, errors)
    if stale_selected:
        print(
            f"  交易日历严格校验无匹配数据，降级选择最新可用: "
            f"{stale_selected['source_name']}，最新日期 {stale_selected['latest_date'].date()}，"
            f"{stale_selected['rows']} 条，{stale_selected['quality_detail']}"
        )
        return stale_selected['df']

    # 全部失败
    print("\n所有数据源均失败，错误详情：")
    for i, err in enumerate(errors, 1):
        print(f"  {i}. {err}")
    raise RuntimeError(f"所有数据源失败: {errors}")



# ==================== 主分析函数 ====================

def _is_prefixed_cn_index_symbol(symbol_code):
    return bool(re.fullmatch(r'(sh|sz|bj)\d{6}', str(symbol_code or ''), flags=re.IGNORECASE))


def _bare_code(value):
    text = str(value or '').strip()
    if not text:
        return ''
    if text.upper().startswith('HK') and text[2:].isdigit():
        return text[2:]
    if '.' in text:
        return text.split('.', 1)[0]
    return re.sub(r'^(sh|sz|bj)', '', text, flags=re.IGNORECASE)


def _prefixed_code(value, market=''):
    bare = _bare_code(value)
    upper_value = str(value or '').strip().upper()
    if upper_value.endswith('.CSI') and re.fullmatch(r'H\d{5}', bare.upper()):
        bare = bare[1:]
    market_value = str(market or '').strip().upper()
    if market_value in {'SH', 'SSE', 'CSI'}:
        prefix = 'sh'
    elif market_value in {'SZ', 'SZSE'}:
        prefix = 'sz'
    elif market_value == 'BJ':
        prefix = 'bj'
    else:
        prefix = ''
    if not prefix:
        if upper_value.endswith(('.SH', '.CSI')):
            prefix = 'sh'
        elif upper_value.endswith('.SZ'):
            prefix = 'sz'
        elif upper_value.endswith('.BJ'):
            prefix = 'bj'
    return f'{prefix}{bare}' if prefix and bare else str(value or '').strip()


def _market_suffix_from_prefixed(value):
    text = str(value or '').strip().lower()
    if text.startswith('sh'):
        return 'SH'
    if text.startswith('sz'):
        return 'SZ'
    if text.startswith('bj'):
        return 'BJ'
    return ''


def _tushare_daily_symbol(value):
    ts_code = str(value or '').strip().upper()
    if not ts_code:
        return ''
    if '.' in ts_code:
        return ts_code
    bare = _bare_code(ts_code).upper()
    market = _market_suffix_from_prefixed(ts_code)
    if not market:
        market = 'SH' if bare.startswith('6') else 'SZ'
    return f'{bare}.{market}'


def _normalize_csi_ts_code(value):
    text = str(value or '').strip().upper()
    if not text.endswith('.CSI'):
        return text
    bare = text.rsplit('.', 1)[0]
    if re.fullmatch(r'\d{5}', bare):
        return f'H{bare}.CSI'
    return text


def _tushare_futures_symbol(value):
    text = str(value or '').strip().upper()
    if not text:
        return ''
    if text in {'T0', 'T'}:
        return 'T.CFX'
    if text in {'TF0', 'TF'}:
        return 'TF.CFX'
    if text in {'TS0', 'TS'}:
        return 'TS.CFX'
    if text in {'TL0', 'TL'}:
        return 'TL0.CFX'
    if '.' in text:
        return text
    return f'{text}.CFX'


def _baostock_plan_symbol(asset, source_symbol, market=''):
    asset_value = str(asset or '').strip().lower()
    if asset_value not in {'a_share', 'auto', 'etf', 'fund', 'index'}:
        return ''
    market_value = str(market or '').strip().upper()
    source_text = str(source_symbol or '').strip()
    if asset_value == 'index' and (source_text.upper().endswith('.CSI') or market_value == 'CSI'):
        return ''
    return _baostock_symbol(source_text, market_value)


def _provider_symbol_plan(config, symbol_code=None):
    """Return provider symbol/API choices for fallback data sources."""
    cfg = dict(config or {})
    data_args = dict(cfg.get('data_args') or {})
    asset = str(cfg.get('asset_type') or 'auto').lower()
    source_symbol = str(symbol_code or data_args.get('symbol') or '').strip()
    akshare_args = data_args.copy()
    market = str(cfg.get('market') or '').strip().upper()
    adapter_asset = '' if asset == 'auto' else asset
    from business.market.provider_adapter import (
        classify_asset_target,
        to_baostock_symbol,
        to_tushare_symbol,
    )

    target = classify_asset_target(
        str(cfg.get('tushare_symbol') or source_symbol or data_args.get('symbol') or '').strip(),
        asset_type=adapter_asset,
        market=market,
        ts_code=str(cfg.get('tushare_symbol') or '').strip(),
    )
    tushare_api_map = {
        'index': 'index_daily',
        'etf': 'fund_daily',
        'fund': 'fund_daily',
        'hk_stock': 'hk_daily',
        'hk': 'hk_daily',
        'us_stock': 'us_daily',
        'us': 'us_daily',
        'convertible_bond': 'cb_daily',
        'futures': 'fut_daily',
    }
    if 'baostock_symbol' in cfg:
        baostock_symbol = str(cfg.get('baostock_symbol') or '').strip()
    else:
        baostock_symbol = to_baostock_symbol(target)
    tushare_symbol = str(cfg.get('tushare_symbol') or '').strip().upper() or to_tushare_symbol(target)
    if target.asset_type == 'futures':
        tushare_symbol = str(cfg.get('tushare_symbol') or '').strip().upper() or _tushare_futures_symbol(source_symbol)

    return {
        'akshare_args': akshare_args,
        'baostock_symbol': baostock_symbol,
        'tushare_api': str(cfg.get('tushare_api') or '').strip() or tushare_api_map.get(target.asset_type, 'daily'),
        'tushare_symbol': tushare_symbol,
    }


def _dynamic_config(symbol_code, name='', asset_type='', market='', ts_code=''):
    label = str(name or symbol_code).strip()
    asset = str(asset_type or '').strip().lower()
    code_for_query = str(ts_code or symbol_code).strip()
    if not asset and _is_prefixed_cn_index_symbol(symbol_code):
        asset = 'index'
    if not asset and str(code_for_query or symbol_code).strip().upper().endswith('.CSI'):
        asset = 'index'
        if not market:
            market = 'CSI'

    if asset == 'index':
        normalized_ts_code = _normalize_csi_ts_code(code_for_query or symbol_code)
        query_symbol = _prefixed_code(normalized_ts_code or symbol_code, market).lower()
        return {
            'name': label,
            'name_short': label,
            'asset_type': 'index',
            'market': str(market or '').strip().upper(),
            'data_func': 'stock_zh_index_daily',
            'data_args': {'symbol': query_symbol},
            'baostock_symbol': _baostock_plan_symbol('index', query_symbol, market),
            'tushare_symbol': normalized_ts_code.upper(),
            'price_decimal': 2,
            'volume_unit': '手',
            'color_theme': '#607D8B',
        }
    if asset in {'etf', 'fund'}:
        query_symbol = _prefixed_code(code_for_query or symbol_code, market).lower()
        return {
            'name': label,
            'name_short': label,
            'asset_type': asset,
            'market': str(market or '').strip().upper(),
            'data_func': 'fund_etf_hist_sina',
            'data_args': {'symbol': query_symbol},
            'baostock_symbol': _baostock_symbol(query_symbol, market),
            'tushare_symbol': _tushare_daily_symbol(code_for_query or query_symbol),
            'price_decimal': 3,
            'volume_unit': '份',
            'color_theme': '#607D8B',
        }
    if asset in {'hk_stock', 'hk'}:
        return {
            'name': label,
            'name_short': label,
            'asset_type': 'hk_stock',
            'market': 'HK',
            'data_func': 'stock_hk_daily',
            'data_args': {'symbol': _bare_code(code_for_query or symbol_code).zfill(5)},
            'baostock_symbol': '',
            'tushare_symbol': _tushare_daily_symbol(code_for_query or symbol_code),
            'price_decimal': 3,
            'volume_unit': '股',
            'color_theme': '#607D8B',
        }
    if asset in {'us_stock', 'us'}:
        return {
            'name': label,
            'name_short': label,
            'asset_type': 'us_stock',
            'market': 'US',
            'data_func': 'stock_us_daily',
            'data_args': {'symbol': _bare_code(code_for_query or symbol_code).upper()},
            'baostock_symbol': '',
            'tushare_symbol': _bare_code(code_for_query or symbol_code).upper(),
            'price_decimal': 2,
            'volume_unit': '股',
            'color_theme': '#607D8B',
        }
    if asset == 'convertible_bond':
        return {
            'name': label,
            'name_short': label,
            'asset_type': 'convertible_bond',
            'market': str(market or '').strip().upper(),
            'data_func': 'bond_zh_hs_cov_daily',
            'data_args': {'symbol': _prefixed_code(code_for_query or symbol_code, market).lower()},
            'baostock_symbol': '',
            'tushare_symbol': _tushare_daily_symbol(code_for_query or symbol_code),
            'price_decimal': 3,
            'volume_unit': '张',
            'color_theme': '#607D8B',
        }
    if asset == 'futures':
        return {
            'name': label,
            'name_short': label,
            'asset_type': 'futures',
            'market': str(market or '').strip().upper(),
            'data_func': 'futures_zh_daily_sina',
            'data_args': {'symbol': _bare_code(code_for_query or symbol_code).upper()},
            'baostock_symbol': '',
            'tushare_symbol': _tushare_futures_symbol(code_for_query or symbol_code),
            'price_decimal': 3,
            'volume_unit': '手',
            'color_theme': '#607D8B',
        }
    return {
        'name': label,
        'name_short': label,
        'asset_type': asset or 'auto',
        'market': str(market or '').strip().upper(),
        'data_func': 'stock_zh_a_hist',
        'data_args': {'symbol': _bare_code(code_for_query or symbol_code), 'period': 'daily', 'adjust': 'qfq'},
        'baostock_symbol': _baostock_symbol(code_for_query or symbol_code, market),
        'tushare_symbol': _tushare_daily_symbol(code_for_query or symbol_code),
        'price_decimal': 2,
        'volume_unit': '手',
        'color_theme': '#607D8B',
    }

def run_analysis(symbol_code, config_name=None, chart_days=120, percentile_lookback=756,
                 output_dir=None, show_chart=True, name='', asset_type='', market='', ts_code=''):
    """
    对任意标的执行完整技术分析

    Parameters
    ----------
    symbol_code : str
        标的代码，如 'T0', 'sh000001', '600519'
    config_name : str, optional
        预设配置名，如不填则用 symbol_code 查找
    chart_days : int
        图表显示天数
    percentile_lookback : int
        分位数回看窗口
    output_dir : str, optional
        输出目录
    show_chart : bool
        是否生成图表

    Returns
    -------
    dict : 分析结果汇总
    """

    # output_dir 默认路径（提前解析）
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(SCRIPT_DIR), '..', '技术形态分析')
    os.makedirs(output_dir, exist_ok=True)
    # 每次重跑前清理旧的历史图片，避免报告不引用的历史图片残留在输出目录中。
    for old_adv_chart in glob.glob(os.path.join(output_dir, 'ADV_*.png')):
        try:
            os.remove(old_adv_chart)
        except OSError:
            pass

    # 获取配置
    if config_name and config_name in PRESET_CONFIGS:
        cfg = PRESET_CONFIGS[config_name]
    elif symbol_code in PRESET_CONFIGS:
        cfg = PRESET_CONFIGS[symbol_code]
    else:
        # 动态创建配置
        cfg = _dynamic_config(symbol_code, name=name, asset_type=asset_type, market=market, ts_code=ts_code)
        print(f"[自动配置] 未找到预设，使用动态配置: {cfg['name']}")

    name = cfg['name']
    name_short = cfg['name_short']
    price_decimal = cfg.get('price_decimal', 2)

    TODAY = datetime.now().strftime('%Y-%m-%d')

    print("=" * 60)
    print(f"技术形态分析: {name} ({symbol_code})")
    print(f"分析日期: {TODAY}")
    print("=" * 60)

    # --- 1. 获取数据 ---
    print(f"\n正在获取 {symbol_code} 数据...")
    df = fetch_data(cfg, symbol_code=symbol_code)
    print(f"原始数据: {len(df)} 条, {df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()}")

    # 【修复1】将 percentile_lookback 上限约束到实际可用的数据量
    # 保证分位数计算始终基于真实存在的数据范围，不会因数据不足而产生误导性标签
    effective_lookback = min(percentile_lookback, len(df))
    if effective_lookback < percentile_lookback:
        print(f"[分位数窗口] 请求 {percentile_lookback} 日，仅有 {effective_lookback} 日数据，已自动缩减")
        percentile_lookback = effective_lookback

    # 切片：图表窗口 + 分位数窗口 + 形态胜率回看窗口 + 前后缓冲
    WR_LOOKBACK = 756  # 3年回看窗口
    _max_horizon = 10  # MAX_HORIZON，提前定义供切片使用
    df_full = df.tail(max(chart_days, percentile_lookback, WR_LOOKBACK + _max_horizon) + 60).reset_index(drop=True)
    df = df_full.tail(chart_days).reset_index(drop=True)

    print(f"图表窗口: {df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()} ({len(df)} 交易日)")

    # numpy 数组
    open_p  = np.array(df['open'],   dtype=np.float64)
    high_p  = np.array(df['high'],   dtype=np.float64)
    low_p   = np.array(df['low'],    dtype=np.float64)
    close_p = np.array(df['close'],  dtype=np.float64)
    volume_p= np.array(df['volume'], dtype=np.float64)

    # --- 2. TA-Lib 61种K线形态识别 ---
    print("\n正在识别K线形态...")

    pattern_funcs = {
        'CDL2CROWS': talib.CDL2CROWS, 'CDL3BLACKCROWS': talib.CDL3BLACKCROWS,
        'CDL3INSIDE': talib.CDL3INSIDE, 'CDL3LINESTRIKE': talib.CDL3LINESTRIKE,
        'CDL3OUTSIDE': talib.CDL3OUTSIDE, 'CDL3STARSINSOUTH': talib.CDL3STARSINSOUTH,
        'CDL3WHITESOLDIERS': talib.CDL3WHITESOLDIERS, 'CDLABANDONEDBABY': talib.CDLABANDONEDBABY,
        'CDLADVANCEBLOCK': talib.CDLADVANCEBLOCK, 'CDLBELTHOLD': talib.CDLBELTHOLD,
        'CDLBREAKAWAY': talib.CDLBREAKAWAY, 'CDLCLOSINGMARUBOZU': talib.CDLCLOSINGMARUBOZU,
        'CDLCONCEALBABYSWALL': talib.CDLCONCEALBABYSWALL, 'CDLCOUNTERATTACK': talib.CDLCOUNTERATTACK,
        'CDLDARKCLOUDCOVER': talib.CDLDARKCLOUDCOVER, 'CDLDOJI': talib.CDLDOJI,
        'CDLDOJISTAR': talib.CDLDOJISTAR, 'CDLDRAGONFLYDOJI': talib.CDLDRAGONFLYDOJI,
        'CDLENGULFING': talib.CDLENGULFING, 'CDLEVENINGDOJISTAR': talib.CDLEVENINGDOJISTAR,
        'CDLEVENINGSTAR': talib.CDLEVENINGSTAR, 'CDLGAPSIDESIDEWHITE': talib.CDLGAPSIDESIDEWHITE,
        'CDLGRAVESTONEDOJI': talib.CDLGRAVESTONEDOJI, 'CDLHAMMER': talib.CDLHAMMER,
        'CDLHANGINGMAN': talib.CDLHANGINGMAN, 'CDLHARAMI': talib.CDLHARAMI,
        'CDLHARAMICROSS': talib.CDLHARAMICROSS, 'CDLHIGHWAVE': talib.CDLHIGHWAVE,
        'CDLHIKKAKE': talib.CDLHIKKAKE, 'CDLHIKKAKEMOD': talib.CDLHIKKAKEMOD,
        'CDLHOMINGPIGEON': talib.CDLHOMINGPIGEON, 'CDLIDENTICAL3CROWS': talib.CDLIDENTICAL3CROWS,
        'CDLINNECK': talib.CDLINNECK, 'CDLINVERTEDHAMMER': talib.CDLINVERTEDHAMMER,
        'CDLKICKING': talib.CDLKICKING, 'CDLKICKINGBYLENGTH': talib.CDLKICKINGBYLENGTH,
        'CDLLADDERBOTTOM': talib.CDLLADDERBOTTOM, 'CDLLONGLEGGEDDOJI': talib.CDLLONGLEGGEDDOJI,
        'CDLLONGLINE': talib.CDLLONGLINE, 'CDLMARUBOZU': talib.CDLMARUBOZU,
        'CDLMATCHINGLOW': talib.CDLMATCHINGLOW, 'CDLMATHOLD': talib.CDLMATHOLD,
        'CDLMORNINGDOJISTAR': talib.CDLMORNINGDOJISTAR, 'CDLMORNINGSTAR': talib.CDLMORNINGSTAR,
        'CDLONNECK': talib.CDLONNECK, 'CDLPIERCING': talib.CDLPIERCING,
        'CDLRICKSHAWMAN': talib.CDLRICKSHAWMAN, 'CDLRISEFALL3METHODS': talib.CDLRISEFALL3METHODS,
        'CDLSEPARATINGLINES': talib.CDLSEPARATINGLINES, 'CDLSHOOTINGSTAR': talib.CDLSHOOTINGSTAR,
        'CDLSHORTLINE': talib.CDLSHORTLINE, 'CDLSPINNINGTOP': talib.CDLSPINNINGTOP,
        'CDLSTALLEDPATTERN': talib.CDLSTALLEDPATTERN, 'CDLSTICKSANDWICH': talib.CDLSTICKSANDWICH,
        'CDLTAKURI': talib.CDLTAKURI, 'CDLTASUKIGAP': talib.CDLTASUKIGAP,
        'CDLTHRUSTING': talib.CDLTHRUSTING, 'CDLTRISTAR': talib.CDLTRISTAR,
        'CDLUNIQUE3RIVER': talib.CDLUNIQUE3RIVER, 'CDLUPSIDEGAP2CROWS': talib.CDLUPSIDEGAP2CROWS,
        'CDLXSIDEGAP3METHODS': talib.CDLXSIDEGAP3METHODS,
    }

    # penetration 参数配置（TA-Lib 中部分形态支持额外过滤阈值）
    PATTERN_PENETRATION = {
        'CDLABANDONEDBABY': 0.3,
        'CDLDARKCLOUDCOVER': 0.5,
        'CDLEVENINGDOJISTAR': 0.3,
        'CDLEVENINGSTAR': 0.3,
        'CDLMATHOLD': 0.5,
        'CDLMORNINGDOJISTAR': 0.3,
        'CDLMORNINGSTAR': 0.3,
    }

    name_map_cn = {
        'CDL2CROWS':'两只乌鸦','CDL3BLACKCROWS':'三只乌鸦','CDL3INSIDE':'三内部形态',
        'CDL3LINESTRIKE':'三线打击','CDL3OUTSIDE':'三外部形态','CDL3STARSINSOUTH':'南方三星',
        'CDL3WHITESOLDIERS':'三白兵','CDLABANDONEDBABY':'弃婴形态','CDLADVANCEBLOCK':'待入形态',
        'CDLBELTHOLD':'捉腰带线','CDLBREAKAWAY':'脱离形态','CDLCLOSINGMARUBOZU':'收盘光头光脚',
        'CDLCONCEALBABYSWALL':'藏婴形态','CDLCOUNTERATTACK':'反击形态','CDLDARKCLOUDCOVER':'乌云盖顶',
        'CDLDOJI':'十字星','CDLDOJISTAR':'十字星形态','CDLDRAGONFLYDOJI':'蜻蜓十字',
        'CDLENGULFING':'吞没形态','CDLEVENINGDOJISTAR':'黄昏十字星','CDLEVENINGSTAR':'黄昏之星',
        'CDLGAPSIDESIDEWHITE':'跳空并列阴阳线','CDLGRAVESTONEDOJI':'墓碑十字','CDLHAMMER':'锤子线',
        'CDLHANGINGMAN':'上吊线','CDLHARAMI':'孕线','CDLHARAMICROSS':'十字孕线',
        'CDLHIGHWAVE':'大波十字','CDLHIKKAKE':'陷阱形态','CDLHIKKAKEMOD':'修正陷阱',
        'CDLHOMINGPIGEON':'家鸽形态','CDLIDENTICAL3CROWS':'三胞胎乌鸦','CDLINNECK':'颈内线',
        'CDLINVERTEDHAMMER':'倒锤线','CDLKICKING':'反冲形态','CDLKICKINGBYLENGTH':'长度反冲',
        'CDLLADDERBOTTOM':'梯形底','CDLLONGLEGGEDDOJI':'长脚十字','CDLLONGLINE':'长蜡烛线',
        'CDLMARUBOZU':'光头光脚','CDLMATCHINGLOW':'匹配低形态','CDLMATHOLD':'匹配形态',
        'CDLMORNINGDOJISTAR':'早晨十字星','CDLMORNINGSTAR':'早晨之星','CDLONNECK':'插入形态',
        'CDLPIERCING':'刺透形态','CDLRICKSHAWMAN':'黄包车夫','CDLRISEFALL3METHODS':'上升/下降三法',
        'CDLSEPARATINGLINES':'分离线','CDLSHOOTINGSTAR':'射击之星','CDLSHORTLINE':'短蜡烛线',
        'CDLSPINNINGTOP':'纺锤线','CDLSTALLEDPATTERN':'停顿形态','CDLSTICKSANDWICH':'条形三明治',
        'CDLTAKURI':'探水竿','CDLTASUKIGAP':'田缺口','CDLTHRUSTING':'插入线',
        'CDLTRISTAR':'三星形态','CDLUNIQUE3RIVER':'独特三川','CDLUPSIDEGAP2CROWS':'上方缺口二鸦',
        'CDLXSIDEGAP3METHODS':'扩大三法',
    }

    name_map_en = {
        'CDL2CROWS':'Two Crows','CDL3BLACKCROWS':'Three Black Crows',
        'CDL3INSIDE':'Three Inside','CDL3LINESTRIKE':'Three-Line Strike',
        'CDL3OUTSIDE':'Three Outside','CDL3STARSINSOUTH':'Three Stars In South',
        'CDL3WHITESOLDIERS':'Three White Soldiers','CDLABANDONEDBABY':'Abandoned Baby',
        'CDLADVANCEBLOCK':'Advance Block','CDLBELTHOLD':'Belt Hold',
        'CDLBREAKAWAY':'Breakaway','CDLCLOSINGMARUBOZU':'Closing Marubozu',
        'CDLCONCEALBABYSWALL':'Concealing Baby Swallow','CDLCOUNTERATTACK':'Counterattack',
        'CDLDARKCLOUDCOVER':'Dark Cloud Cover','CDLDOJI':'Doji',
        'CDLDOJISTAR':'Doji Star','CDLDRAGONFLYDOJI':'Dragonfly Doji',
        'CDLENGULFING':'Engulfing','CDLEVENINGDOJISTAR':'Evening Doji Star',
        'CDLEVENINGSTAR':'Evening Star','CDLGAPSIDESIDEWHITE':'Gapping Side-by-Side',
        'CDLGRAVESTONEDOJI':'Gravestone Doji','CDLHAMMER':'Hammer',
        'CDLHANGINGMAN':'Hanging Man','CDLHARAMI':'Harami',
        'CDLHARAMICROSS':'Harami Cross','CDLHIGHWAVE':'High Wave',
        'CDLHIKKAKE':'Hikkake','CDLHIKKAKEMOD':'Modified Hikkake',
        'CDLHOMINGPIGEON':'Homing Pigeon','CDLIDENTICAL3CROWS':'Identical Three Crows',
        'CDLINNECK':'In-Neck Pattern','CDLINVERTEDHAMMER':'Inverted Hammer',
        'CDLKICKING':'Kicking','CDLKICKINGBYLENGTH':'Kicking By Length',
        'CDLLADDERBOTTOM':'Ladder Bottom','CDLLONGLEGGEDDOJI':'Long Legged Doji',
        'CDLLONGLINE':'Long Line','CDLMARUBOZU':'Marubozu',
        'CDLMATCHINGLOW':'Matching Low','CDLMATHOLD':'Mat Hold',
        'CDLMORNINGDOJISTAR':'Morning Doji Star','CDLMORNINGSTAR':'Morning Star',
        'CDLONNECK':'On Neck','CDLPIERCING':'Piercing Pattern',
        'CDLRICKSHAWMAN':'Rickshaw Man','CDLRISEFALL3METHODS':'Rise/Fall Three',
        'CDLSEPARATINGLINES':'Separating Lines','CDLSHOOTINGSTAR':'Shooting Star',
        'CDLSHORTLINE':'Short Line','CDLSPINNINGTOP':'Spinning Top',
        'CDLSTALLEDPATTERN':'Stalled Pattern','CDLSTICKSANDWICH':'Stick Sandwich',
        'CDLTAKURI':'Takuri','CDLTASUKIGAP':'Tasuki Gap',
        'CDLTHRUSTING':'Thrusting Pattern','CDLTRISTAR':'Tristar',
        'CDLUNIQUE3RIVER':'Unique Three River','CDLUPSIDEGAP2CROWS':'Upside Gap Two Crows',
        'CDLXSIDEGAP3METHODS':'Wide Gapping Three',
    }

    all_results = []
    recent_results = []

    for fname, func in pattern_funcs.items():
        try:
            if fname in PATTERN_PENETRATION:
                result = func(open_p, high_p, low_p, close_p, penetration=PATTERN_PENETRATION[fname])
            else:
                result = func(open_p, high_p, low_p, close_p)
        except Exception:
            continue
        idxs = np.where(result != 0)[0]
        for idx in idxs:
            signal = int(result[idx])
            date_str = str(df['date'].iloc[idx].date())
            price = close_p[idx]
            direction = '看涨' if signal > 0 else '看跌'
            strength = '高' if abs(signal) >= 100 else '中'
            days_ago = len(df) - 1 - idx
            is_recent = days_ago <= 30

            item = {
                'code': fname,
                'name_en': name_map_en.get(fname, fname),
                'name_cn': name_map_cn.get(fname, fname),
                'date': date_str,
                'days_ago': days_ago,
                'direction': direction,
                'direction_en': 'Bullish' if signal > 0 else 'Bearish',
                'strength': strength,
                'signal': signal,
                'close': round(price, price_decimal),
                'is_recent': is_recent,
            }
            all_results.append(item)
            if is_recent:
                recent_results.append(item)

    all_results.sort(key=lambda x: x['days_ago'])
    recent_results.sort(key=lambda x: x['days_ago'])

    print(f"  历史形态: {len(all_results)} 个 | 近30日: {len(recent_results)} 个")

    # --- 2b. 过去3年K线形态胜率统计 ---
    # 胜率定义: 形态出现后第N日收盘价方向与形态预测方向一致的比例
    # 看涨形态: N日后收盘价 > 形态当日收盘价 → 成功
    # 看跌形态: N日后收盘价 < 形态当日收盘价 → 成功
    print("\n正在计算K线形态历史胜率...")

    HORIZON_DAYS = [1, 3, 5, 10]  # 观察期(交易日)
    MAX_HORIZON = max(HORIZON_DAYS)
    # WR_LOOKBACK 已在数据切片处定义（756 = 3年回看窗口）

    wr_open_full  = np.array(df_full['open'],   dtype=np.float64)
    wr_high_full  = np.array(df_full['high'],   dtype=np.float64)
    wr_low_full   = np.array(df_full['low'],    dtype=np.float64)
    wr_close_full = np.array(df_full['close'],  dtype=np.float64)

    n_full = len(wr_close_full)
    # 扫描区间: [scan_start, scan_end) — 只统计过去3年内、且形态后还有 MAX_HORIZON 日观察空间的样本
    scan_end = n_full - MAX_HORIZON
    scan_start = max(0, scan_end - WR_LOOKBACK)
    actual_lookback = scan_end - scan_start

    pattern_occurrences = {}  # {(code, direction): [idx1, idx2, ...]}

    for fname, func in pattern_funcs.items():
        try:
            if fname in PATTERN_PENETRATION:
                wr_result = func(wr_open_full, wr_high_full, wr_low_full, wr_close_full,
                                 penetration=PATTERN_PENETRATION[fname])
            else:
                wr_result = func(wr_open_full, wr_high_full, wr_low_full, wr_close_full)
        except Exception:
            continue
        idxs = np.where(wr_result != 0)[0]
        for idx in idxs:
            if idx < scan_start or idx >= scan_end:
                continue
            sig_val = int(wr_result[idx])
            direction = '看涨' if sig_val > 0 else '看跌'
            key = (fname, direction)
            if key not in pattern_occurrences:
                pattern_occurrences[key] = []
            pattern_occurrences[key].append(idx)

    win_rate_results = []
    for (fname, direction), idx_list in pattern_occurrences.items():
        n_occ = len(idx_list)
        # 每个观察期记录: 胜次/总次/胜方收益(形态视角,正值)/败方收益(形态视角,负值)
        horizon_stats = {h: {
            'wins': 0,
            'total': 0,
            'win_returns': [],
            'loss_returns': [],
        } for h in HORIZON_DAYS}
        for idx in idx_list:
            entry_close = wr_close_full[idx]
            if entry_close <= 0 or np.isnan(entry_close):
                continue
            for h in HORIZON_DAYS:
                future_idx = idx + h
                if future_idx >= n_full:
                    continue
                future_close = wr_close_full[future_idx]
                if np.isnan(future_close):
                    continue
                # 原始收益率: (未来收盘 - 当日收盘)/当日收盘 × 100
                raw_ret = (future_close - entry_close) / entry_close * 100
                # 形态视角收益: 看涨直接用 raw_ret, 看跌取反 → 正值=方向预测正确
                directional_ret = raw_ret if direction == '看涨' else -raw_ret
                horizon_stats[h]['total'] += 1
                if directional_ret > 0:
                    horizon_stats[h]['wins'] += 1
                    horizon_stats[h]['win_returns'].append(directional_ret)
                else:
                    horizon_stats[h]['loss_returns'].append(directional_ret)
        win_rate_results.append({
            'code': fname,
            'name_cn': name_map_cn.get(fname, fname),
            'name_en': name_map_en.get(fname, fname),
            'direction': direction,
            'occurrences': n_occ,
            'horizon_stats': horizon_stats,
        })

    # 排序: 出现次数降序
    win_rate_results.sort(key=lambda x: (-x['occurrences'], x['code']))
    print(f"  统计完成: {len(win_rate_results)} 个(形态,方向)组合，回看 {actual_lookback} 个交易日")

    # --- 3. 技术指标 ---
    from indicators_lib import (
        calc_all_indicators, calc_percentile, pct_label, last_value,
    )

    ind_full = calc_all_indicators(
        df_full['high'].values, df_full['low'].values, df_full['close'].values,
        df_full['volume'].values, open_=df_full['open'].values,
    )
    ind_chart = calc_all_indicators(
        high_p, low_p, close_p, volume_p, open_=open_p,
    )

    ma5, ma10, ma20, ma60 = ind_chart.trend.sma5, ind_chart.trend.sma10, ind_chart.trend.sma20, ind_chart.trend.sma60
    # 【修复】MACD/RSI/KDJ/BOLL/ATR 使用 ind_full 的尾部数据绘图，避免短窗口 EMA 预热不足导致前期空白
    n = len(df)  # 图表窗口长度（chart_days）

    def _tail(arr, n):
        """取数组尾部 n 条，不足则全取，并对齐到 n（前补 NaN）"""
        if arr is None:
            return np.full(n, np.nan)
        a = np.asarray(arr, dtype=np.float64)
        if len(a) >= n:
            return a[-n:]
        pad = np.full(n - len(a), np.nan)
        return np.concatenate([pad, a])

    macd  = _tail(ind_full.momentum.macd,        n)
    sig   = _tail(ind_full.momentum.macd_signal,  n)
    hist  = _tail(ind_full.momentum.macd_hist,    n)
    rsi6  = _tail(ind_full.momentum.rsi6,         n)
    rsi12 = _tail(ind_full.momentum.rsi12,        n)
    upper  = _tail(ind_full.volatility.boll_upper, n)
    middle = _tail(ind_full.volatility.boll_mid,   n)
    lower  = _tail(ind_full.volatility.boll_lower, n)
    k_vals = _tail(ind_full.momentum.k9,           n)
    d_vals = _tail(ind_full.momentum.d9,           n)
    j_vals = _tail(ind_full.momentum.j9,           n)
    atr14  = _tail(ind_full.volatility.atr14,      n)
    # ma 系列保持用 ind_chart（已基于图表窗口数据，SMA 短期预热快）

    # 分位数
    rsi6_pct     = calc_percentile(last_value(rsi6),  ind_full.momentum.rsi6,  percentile_lookback)
    rsi12_pct    = calc_percentile(last_value(rsi12), ind_full.momentum.rsi12, percentile_lookback)
    k_pct        = calc_percentile(last_value(k_vals),  ind_full.momentum.k9,    percentile_lookback)
    d_pct        = calc_percentile(last_value(d_vals),  ind_full.momentum.d9,    percentile_lookback)
    j_pct        = calc_percentile(last_value(j_vals),  ind_full.momentum.j9,    percentile_lookback)
    atr_pct_hist = calc_percentile(last_value(atr14),  ind_full.volatility.atr14, percentile_lookback)

    vol_full = df_full['volume'].values
    vol_ratio_full = pd.Series(vol_full) / pd.Series(vol_full).rolling(5, min_periods=1).mean()
    vol_ratio_full = vol_ratio_full.values
    vol_ratio_today = vol_full[-1] / np.nanmean(vol_full[-6:-1]) if len(vol_full) >= 6 else 1.0
    vol_ratio_pct   = calc_percentile(vol_ratio_today, vol_ratio_full, percentile_lookback)

    # 最新价格
    last_close = close_p[-1]
    last_high  = high_p[-1]
    last_low   = low_p[-1]
    last_open  = open_p[-1]
    last_vol   = float(df['volume'].iloc[-1]) if len(df) > 0 else 0
    last_date  = df['date'].iloc[-1]
    prev_close = close_p[-2]
    change_pct = (last_close - prev_close) / prev_close * 100

    # 趋势判断
    above_ma = sum([1 for v in [ma5[-1], ma10[-1], ma20[-1]] if last_close > v])
    trend = '多头排列' if above_ma >= 2 and ma5[-1] > ma10[-1] > ma20[-1] else \
            '空头排列' if above_ma <= 1 and ma5[-1] < ma10[-1] < ma20[-1] else '震荡整理'

    # 成交量信息
    vol_ma5  = pd.Series(volume_p).rolling(5).mean().iloc[-1]
    vol_ma20 = pd.Series(volume_p).rolling(20).mean().iloc[-1]
    vol_ratio_today = vol_full[-1] / np.nanmean(vol_full[-6:-1]) if len(vol_full) >= 6 else 1.0
    vol_ratio_pct   = calc_percentile(vol_ratio_today, vol_ratio_full, percentile_lookback)
    vol_comment = f'{vol_ratio_today:.2f}x 5日均量'

    # --- 4. 信号扫描 ---
    print("\n正在进行异常信号扫描...")
    from signal_scanner import SignalScanner
    scanner = SignalScanner(
        ind_full=ind_full, ind_chart=ind_chart,
        recent_cdl_patterns=recent_results,
        lookback=percentile_lookback,
    )
    scan_report = scanner.scan_all()
    print(f"  {scanner.summary_text()}")

    # --- 6. 生成图表 ---
    chart_path = None
    if show_chart:
        print("\n正在生成图表...")

        fig, axes = plt.subplots(4, 1, figsize=(18, 16), gridspec_kw={'height_ratios':[3,1.2,1.2,1.2]})
        theme = cfg.get('color_theme', '#607D8B')
        bull_color = '#F44336'   # 涨 → 红色（A股惯例）
        bear_color = '#26A69A'   # 跌 → 绿色（A股惯例）
        fig.suptitle(f'{name} ({symbol_code}) 技术分析  {TODAY}', fontsize=16, fontweight='bold', y=0.98)

        # 面板1: K线 + 均线 + BOLL
        ax1 = axes[0]
        da = np.arange(len(df))
        ax1.plot(da, ma5,  color='#2196F3', lw=1.0, label=f'MA5={ma5[-1]:.{price_decimal}f}',  alpha=0.85)
        ax1.plot(da, ma10, color='#FF9800', lw=1.2, label=f'MA10={ma10[-1]:.{price_decimal}f}', alpha=0.85)
        ax1.plot(da, ma20, color='#9C27B0', lw=1.2, label=f'MA20={ma20[-1]:.{price_decimal}f}', alpha=0.85)
        if not np.isnan(ma60[-1]):
            ax1.plot(da, ma60, color='#795548', lw=0.9, label=f'MA60={ma60[-1]:.{price_decimal}f}', alpha=0.6)
        ax1.plot(da, upper,  color='gray', lw=0.4, ls='--', alpha=0.5)
        ax1.plot(da, middle, color='gray', lw=0.6, ls=':',  alpha=0.5, label='BOLL')
        ax1.plot(da, lower,  color='gray', lw=0.4, ls='--', alpha=0.5)
        ax1.fill_between(da, lower, upper, alpha=0.04, color='gray')

        for i in range(len(df)):
            color = bull_color if close_p[i] >= open_p[i] else bear_color
            ax1.plot([i,i],[low_p[i],high_p[i]], color=color, lw=0.8)
            ax1.plot([i,i],[open_p[i],close_p[i]], color=color, lw=3.5)

        # 【修复2】不再在主图上拥挤标注所有形态，形态详情见第三章独立详图
        ax1.set_xlim(-1, len(df))
        # 【修复1】K线图Y轴聚焦实际价格范围，而非布林带（国债期货波动小，布林带范围过宽导致K线被压扁）
        price_min = np.nanmin(low_p)
        price_max = np.nanmax(high_p)
        price_range = price_max - price_min
        # 给上下留适当边距
        margin_top = price_range * 0.15 if price_range > 0 else price_max * 0.03
        margin_bottom = price_range * 0.10 if price_range > 0 else price_min * 0.02
        ax1.set_ylim(price_min - margin_bottom, price_max + margin_top)
        ax1.legend(loc='upper left', fontsize=7.5, ncol=5)
        ax1.set_title('K线图 + 移动均线 + 布林带', fontsize=10)
        ax1.grid(True, alpha=0.2)
        ax1.set_ylabel('价格')

        # 面板2: MACD
        ax2 = axes[1]
        bar_colors = [bull_color if v>=0 else bear_color for v in hist]
        ax2.bar(da, hist, color=bar_colors, width=0.7, alpha=0.55)
        ax2.plot(da, macd, color='#2196F3', lw=1.0, label=f'MACD={macd[-1]:.4f}')
        ax2.plot(da, sig,   color='#FF9800', lw=1.0, label=f'Signal={sig[-1]:.4f}')
        ax2.axhline(0, color='gray', lw=0.5)
        ax2.legend(loc='upper left', fontsize=8)
        ax2.set_title(f'MACD  ({"金叉" if macd[-1]>sig[-1] else "死叉"})', fontsize=10)
        ax2.grid(True, alpha=0.2)
        ax2.set_xlim(-1, len(df))

        # 面板3: KDJ
        ax3 = axes[2]
        ax3.plot(da, k_vals, color='#2196F3', lw=1.0, label=f'K={k_vals[-1]:.1f}')
        ax3.plot(da, d_vals, color='#FF9800', lw=1.0, label=f'D={d_vals[-1]:.1f}')
        ax3.plot(da, j_vals, color='#9C27B0', lw=0.8, ls='--', label=f'J={j_vals[-1]:.1f}')
        ax3.axhline(50, color='gray',  lw=0.4, ls=':')
        ax3.axhline(80, color='red',   lw=0.3, ls='--', alpha=0.3)
        ax3.axhline(20, color='green', lw=0.3, ls='--', alpha=0.3)
        ax3.legend(loc='upper left', fontsize=8)
        ax3.set_title(f'KDJ  ({"金叉" if k_vals[-1]>d_vals[-1] else "死叉"})', fontsize=10)
        ax3.grid(True, alpha=0.2)
        ax3.set_xlim(-1, len(df))
        ax3.set_ylim(-10, 110)

        # 面板4: RSI
        ax4 = axes[3]
        ax4.plot(da, rsi6,  color='#E91E63', lw=1.0, label=f'RSI6={rsi6[-1]:.1f}')
        ax4.plot(da, rsi12, color='#3F51B5', lw=1.0, label=f'RSI12={rsi12[-1]:.1f}')
        ax4.axhline(70, color='red',   lw=0.4, ls='--', alpha=0.5)
        ax4.axhline(30, color='green', lw=0.4, ls='--', alpha=0.5)
        ax4.axhline(50, color='gray',  lw=0.4, ls=':')
        ax4.fill_between(da, 30, 70, alpha=0.04, color='gray')
        ax4.legend(loc='upper left', fontsize=8)
        ax4.set_title(f'RSI  (历史分位: {rsi6_pct:.0f}%)', fontsize=10)
        ax4.grid(True, alpha=0.2)
        ax4.set_xlim(-1, len(df))
        ax4.set_ylim(0, 100)
        ax4.set_xlabel('交易日')

        # X轴日期
        tick_step = max(1, len(df)//10)
        tick_pos = list(range(0, len(df), tick_step))
        tick_lbl = [str(df['date'].iloc[i].date()) for i in tick_pos]
        for ax in axes:
            ax.set_xticks(tick_pos)
            ax.set_xticklabels(tick_lbl, rotation=45, fontsize=6.5)

        plt.tight_layout(rect=[0, 0, 1, 0.97])




        safe_name = symbol_code.replace('/', '_')
        chart_path = os.path.join(output_dir, f'{safe_name}_TA_{TODAY}.png')
        plt.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"图表已保存: {chart_path}")

    # --- 6b. K线形态详图（仅今日形态，用户要求只展示今日出现的形态） ---
    pattern_chart_paths = []
    today_patterns = [r for r in all_results if r['days_ago'] == 0]
    if show_chart and today_patterns:
        print(f"\n正在生成今日({TODAY})K线形态详图...")
        for item in today_patterns:
            idx = len(df) - 1 - item['days_ago']
            if 0 <= idx < len(df):
                try:
                    p = _plot_pattern_detail(item, df, idx, price_decimal,
                                             output_dir, safe_name, TODAY)
                    if p:
                        pattern_chart_paths.append(p)
                except Exception:
                    pass
        print(f"  形态详图已生成 {len(pattern_chart_paths)} 张")

    # ============================================================
    # --- 7. 生成报告（买方研究报告版式） ---
    # ============================================================

    # ---------- 7.1 基础聚合 ----------
    bull_cnt = sum(1 for r in all_results if r['direction']=='看涨')
    bear_cnt = sum(1 for r in all_results if r['direction']=='看跌')
    recent_bull = [r for r in recent_results if r['direction']=='看涨']
    recent_bear = [r for r in recent_results if r['direction']=='看跌']

    macd_signal = 'MACD 金叉（看涨）' if macd[-1]>sig[-1] else 'MACD 死叉（看跌）'
    hist_signal = '柱体 > 0' if hist[-1]>0 else '柱体 < 0'
    boll_status = '突破上轨' if last_close>upper[-1] else ('跌破下轨' if last_close<lower[-1] else '布林带内')
    atr_pct = atr14[-1]/last_close*100

    vol_unit = cfg.get('volume_unit', '手')
    vol_display = f"{last_vol/10000:.2f}万{vol_unit}" if last_vol > 0 else "无数据"

    # ---------- 7.2 win-rate 渲染辅助函数（前置以便 5.2 节使用） ----------
    def _wr_text(stats):
        if stats['total'] == 0:
            return '-'
        rate = stats['wins'] / stats['total'] * 100
        return f"{rate:.0f}% ({stats['wins']}/{stats['total']})"

    def _avg_win(stats):
        if not stats['win_returns']:
            return None
        return sum(stats['win_returns']) / len(stats['win_returns'])

    def _avg_loss(stats):
        if not stats['loss_returns']:
            return None
        return sum(stats['loss_returns']) / len(stats['loss_returns'])

    def _fmt_pct(v):
        if v is None:
            return '-'
        return f"{v:+.2f}%"

    def _pl_ratio(stats):
        avg_w = _avg_win(stats)
        avg_l = _avg_loss(stats)
        if avg_w is None or avg_l is None or avg_l == 0:
            return '-'
        return f"{avg_w / abs(avg_l):.2f}"

    def _expected(stats):
        if stats['total'] == 0:
            return '-'
        win_rate = stats['wins'] / stats['total']
        avg_w = _avg_win(stats) or 0.0
        avg_l = _avg_loss(stats) or 0.0
        ev = win_rate * avg_w + (1 - win_rate) * avg_l
        return f"{ev:+.3f}%"

    # ---------- 7.3 报告章节辅助函数 ----------
    def build_key_levels(last_close_, ma_dict_, boll_dict_, price_decimal_):
        """从均线/BOLL候选点位中提取关键阻力支撑。
        返回 {'resistances': [...], 'supports': [...]} 每项含 type/price/label/hint。
        """
        candidates = []
        for nm, pv in {**ma_dict_, **boll_dict_}.items():
            if pv is None:
                continue
            try:
                f_pv = float(pv)
            except (TypeError, ValueError):
                continue
            if np.isnan(f_pv):
                continue
            candidates.append({'name': nm, 'price': f_pv})

        above = sorted([c for c in candidates if c['price'] > last_close_], key=lambda x: x['price'])
        below = sorted([c for c in candidates if c['price'] <= last_close_], key=lambda x: -x['price'])

        def _merge_close(items, threshold=0.001):
            merged = []
            for c in items:
                if merged and abs(c['price'] - merged[-1]['price']) / max(abs(merged[-1]['price']), 1e-9) < threshold:
                    merged[-1] = {'name': f"{merged[-1]['name']}/{c['name']}", 'price': merged[-1]['price']}
                else:
                    merged.append(dict(c))
            return merged

        above_m = _merge_close(above)
        below_m = _merge_close(below)

        res_types = ['第一阻力', '第二阻力']
        sup_types = ['第一支撑', '第二支撑', '下沿支撑']
        res_hints = ['短线反弹首先需要收复的位置', '若放量突破，趋势延续概率提高']
        sup_hints = ['短线震荡中枢', '中期趋势防守位', '若跌破，技术面转弱信号增强']

        resistances = [
            {'type': res_types[i], 'price': c['price'], 'label': c['name'] + '附近', 'hint': res_hints[i]}
            for i, c in enumerate(above_m[:2])
        ]
        supports = [
            {'type': sup_types[i], 'price': c['price'], 'label': c['name'] + '附近', 'hint': sup_hints[i]}
            for i, c in enumerate(below_m[:3])
        ]
        return {'resistances': resistances, 'supports': supports}

    def build_signal_matrix():
        """生成6维多空证据表，每行 dict: dim/signal/direction/comment。"""
        rows = []
        # 1. 趋势
        if trend == '多头排列':
            d, c = '看多', '短期均线呈多头排列，方向向上'
        elif trend == '空头排列':
            d, c = '看空', '短期均线呈空头排列，方向向下'
        else:
            d, c = '中性', '趋势未明显走强，价格在均线区间反复'
        rows.append({'dim': '趋势', 'signal': f'{above_ma}/3 短期均线多头，{trend}', 'direction': d, 'comment': c})

        # 2. 动量
        macd_cross = '金叉' if macd[-1] > sig[-1] else '死叉'
        kdj_cross = '金叉' if k_vals[-1] > d_vals[-1] else '死叉'
        if macd_cross == '金叉' and kdj_cross == '金叉':
            d, c = '偏多', 'MACD/KDJ 同向金叉，短线动能向上'
        elif macd_cross == '死叉' and kdj_cross == '死叉':
            d, c = '偏空', 'MACD/KDJ 同向死叉，短线动能转弱'
        else:
            d, c = '分歧', f'MACD {macd_cross} 与 KDJ {kdj_cross} 信号不一致'
        rows.append({'dim': '动量', 'signal': f'MACD {macd_cross}、KDJ {kdj_cross}', 'direction': d, 'comment': c})

        # 3. 超买超卖
        if rsi6[-1] > 70:
            d, c = '偏空', 'RSI(6) 超买，短线获利盘抛压上升'
        elif rsi6[-1] < 30:
            d, c = '偏多', 'RSI(6) 超卖，短线反弹动能积累'
        else:
            d, c = '中性', '尚未进入极端区间，无显著超买超卖情绪'
        rows.append({'dim': '超买超卖', 'signal': f'RSI(6)={rsi6[-1]:.1f}，RSI(12)={rsi12[-1]:.1f}', 'direction': d, 'comment': c})

        # 4. 波动率
        if atr_pct_hist < 30:
            d, c = '偏低', '市场波动收敛，等待方向选择'
        elif atr_pct_hist > 70:
            d, c = '偏高', '市场波动放大，需注意趋势加速或破位风险'
        else:
            d, c = '常态', '波动处于常规区间'
        rows.append({'dim': '波动率', 'signal': f'ATR(14) 处于 {atr_pct_hist:.0f}% 分位', 'direction': d, 'comment': c})

        # 5. 成交量
        if vol_ratio_today > 1.5 and vol_ratio_pct > 70:
            d, c = '偏强', '量比放大且分位偏高，资金参与度上升'
        elif vol_ratio_today < 0.8 or vol_ratio_pct < 30:
            d, c = '偏弱', '量能不足，方向确认乏力'
        else:
            d, c = '中性', '量能维持常态'
        rows.append({'dim': '成交量', 'signal': f'量比 {vol_ratio_today:.2f}x，{vol_ratio_pct:.0f}% 分位', 'direction': d, 'comment': c})

        # 6. 形态
        bull_n = len(recent_bull)
        bear_n = len(recent_bear)
        latest_dir = recent_results[0]['direction'] if recent_results else None
        if bull_n == 0 and bear_n == 0:
            d, c = '中性', '近期未出现明显形态'
        elif bull_n >= 2 * max(bear_n, 1) and latest_dir == '看涨':
            d, c = '偏多', '近30日看涨形态显著多于看跌，最新一日延续看涨'
        elif bear_n >= 2 * max(bull_n, 1) and latest_dir == '看跌':
            d, c = '偏空', '近30日看跌形态显著多于看涨，最新一日延续看跌'
        elif latest_dir == '看跌' and bull_n > bear_n:
            d, c = '分歧', '历史形态偏多，但最新一日转为看跌信号'
        elif latest_dir == '看涨' and bear_n > bull_n:
            d, c = '分歧', '历史形态偏空，但最新一日转为看涨信号'
        else:
            d, c = '中性', f'近30日 {bull_n} 看涨 / {bear_n} 看跌，无显著倾向'
        rows.append({'dim': '形态', 'signal': f'近30日 {bull_n} 看涨 / {bear_n} 看跌', 'direction': d, 'comment': c})
        return rows

    def build_core_view(matrix_, levels_):
        """基于多空证据表 + 关键点位生成 4 行核心结论字典。"""
        # 当前判断
        if atr_pct_hist < 30:
            vol_state = f'ATR {atr_pct_hist:.0f}% 分位，波动收敛'
        elif atr_pct_hist > 70:
            vol_state = f'ATR {atr_pct_hist:.0f}% 分位，波动放大'
        else:
            vol_state = f'ATR {atr_pct_hist:.0f}% 分位，波动常态'
        if trend == '震荡整理':
            judgement = f'{name_short} 短期处于震荡整理（{vol_state}），趋势方向尚未形成明确突破'
        elif trend == '多头排列':
            judgement = f'{name_short} 当前呈现多头排列态势（{vol_state}）'
        else:
            judgement = f'{name_short} 当前呈现空头排列态势（{vol_state}）'

        # 多空倾向
        bull_c = sum(1 for r in matrix_ if r['direction'] in ('看多', '偏多', '偏强'))
        bear_c = sum(1 for r in matrix_ if r['direction'] in ('看空', '偏空', '偏弱'))
        diverge_c = sum(1 for r in matrix_ if r['direction'] == '分歧')
        pattern_row = next((r for r in matrix_ if r['dim'] == '形态'), None)
        pattern_dir = pattern_row['direction'] if pattern_row else '中性'

        if bull_c > bear_c + 1:
            base = '指标层面偏多'
        elif bear_c > bull_c + 1:
            base = '指标层面略偏谨慎'
        else:
            base = '指标层面多空相对均衡'

        if diverge_c >= 2 or (bull_c > 0 and bear_c > 0 and abs(bull_c - bear_c) <= 1):
            bias = f'{base}，形态{pattern_dir}，整体信号分歧'
        elif bull_c > bear_c:
            bias = f'{base}，形态{pattern_dir}，整体偏多'
        elif bear_c > bull_c:
            bias = f'{base}，形态{pattern_dir}，整体偏谨慎'
        else:
            bias = f'{base}，形态{pattern_dir}'

        # 关键点位
        res_str = '/'.join([f"{r['price']:.{price_decimal}f}" for r in levels_['resistances']]) or '无明显阻力'
        sup_str = '/'.join([f"{s['price']:.{price_decimal}f}" for s in levels_['supports']]) or '无明显支撑'
        levels_text = f'上方关注 {res_str}，下方关注 {sup_str}'

        # 操作提示
        if bull_c > bear_c + 1:
            action = '可适度参与多头思路，但需关注关键阻力位放量配合；若跌破第一支撑则及时止盈'
        elif bear_c > bull_c + 1:
            action = '短线宜偏防守，等待关键支撑确认；若放量站稳第一阻力再确认反弹'
        else:
            action = '不宜追涨追跌，适合区间思路；若放量突破上方阻力再确认趋势延续，若跌破下方支撑则防范回撤'

        return {'judgement': judgement, 'bias': bias, 'levels': levels_text, 'action': action,
                'bull_c': bull_c, 'bear_c': bear_c, 'diverge_c': diverge_c}

    def summarize_recent_patterns_by_day(recent_results_, n_days=3):
        """按最近 n_days 个交易日聚合形态。"""
        if not recent_results_:
            return []
        from collections import defaultdict
        by_day = defaultdict(list)
        for r in recent_results_:
            if r['days_ago'] < n_days:
                by_day[r['days_ago']].append(r)
        rows = []
        for days_ago in sorted(by_day.keys()):
            items = by_day[days_ago]
            date_ = items[0]['date']
            bull_n = sum(1 for x in items if x['direction'] == '看涨')
            bear_n = sum(1 for x in items if x['direction'] == '看跌')
            seen, names = set(), []
            for x in items:
                if x['name_cn'] not in seen:
                    names.append(x['name_cn'])
                    seen.add(x['name_cn'])
            names_str = '/'.join(names[:4]) + ('等' if len(names) > 4 else '')
            if bull_n > 0 and bear_n == 0:
                direction = '偏多'
                explain = '看涨形态聚集，短线企稳信号，但持续性需后续 K 线验证'
            elif bear_n > 0 and bull_n == 0:
                direction = '偏空'
                explain = '看跌形态聚集，高位震荡后出现犹豫/转弱信号，需警惕方向选择'
            else:
                direction = '混合'
                explain = '看涨与看跌形态并存，市场分歧明显，建议等待方向确认'
            rows.append({'days_ago': days_ago, 'date': date_, 'names': names_str,
                         'direction': direction, 'bull_n': bull_n, 'bear_n': bear_n, 'explain': explain})
        return rows

    def filter_valid_patterns(win_rate_results_, min_occurrences=5):
        """筛选过去 3 年同时满足胜率>50%、盈亏比>1、5日期望>0 的形态。"""
        valid = []
        for w in win_rate_results_:
            if w['occurrences'] < min_occurrences:
                continue
            s5 = w['horizon_stats'][5]
            if s5['total'] == 0:
                continue
            win_rate_v = s5['wins'] / s5['total'] * 100
            avg_w = _avg_win(s5)
            avg_l = _avg_loss(s5)
            if avg_w is None or avg_l is None or avg_l == 0:
                continue
            pl_v = avg_w / abs(avg_l)
            ev_v = (s5['wins'] / s5['total']) * avg_w + (1 - s5['wins'] / s5['total']) * avg_l
            if win_rate_v > 50 and pl_v > 1 and ev_v > 0:
                valid.append({
                    'name_cn': w['name_cn'], 'name_en': w['name_en'], 'direction': w['direction'],
                    'occurrences': w['occurrences'], 'win_rate': win_rate_v,
                    'pl_ratio': pl_v, 'ev': ev_v, 'avg_win': avg_w, 'avg_loss': avg_l,
                })
        valid.sort(key=lambda x: -x['ev'])
        return valid

    def build_scenarios(levels_):
        """4 个情景：上行/震荡/转弱/破位（触发条件由关键点位填充）。"""
        res = levels_['resistances']
        sup = levels_['supports']
        def fmt(p):
            return f'{p:.{price_decimal}f}'
        if len(res) >= 2:
            up_t = f'收盘站上 {fmt(res[0]["price"])}，并接近/突破 {fmt(res[1]["price"])}'
        elif len(res) == 1:
            up_t = f'收盘站上 {fmt(res[0]["price"])}'
        else:
            up_t = '价格继续走高，但缺少明显阻力参考'
        if res and sup:
            range_t = f'价格维持在 {fmt(sup[0]["price"])} ~ {fmt(res[0]["price"])} 区间'
        else:
            range_t = '价格在 BOLL 中轨附近反复'
        if len(sup) >= 2:
            weak_t = f'跌破 {fmt(sup[0]["price"])}，并接近 {fmt(sup[1]["price"])}'
        elif len(sup) == 1:
            weak_t = f'跌破 {fmt(sup[0]["price"])}'
        else:
            weak_t = '短期回落，但仍在中枢附近'
        if len(sup) >= 3:
            break_t = f'跌破 {fmt(sup[2]["price"])}'
        elif len(sup) >= 1:
            break_t = f'跌破 {fmt(sup[-1]["price"])}'
        else:
            break_t = '下轨失守，波动可能放大'
        return [
            {'name': '上行情景', 'trigger': up_t,
             'meaning': '短期均线压力解除，布林带上沿打开',
             'action': '可适度提高多头暴露，但需成交量配合'},
            {'name': '震荡情景', 'trigger': range_t,
             'meaning': '均线与布林中轨附近反复拉锯',
             'action': '以区间交易和仓位控制为主'},
            {'name': '转弱情景', 'trigger': weak_t,
             'meaning': '短期动能转弱，中期均线面临考验',
             'action': '降低追多意愿，关注止盈和回撤风险'},
            {'name': '破位情景', 'trigger': break_t,
             'meaning': '布林下轨失守，波动可能放大',
             'action': '技术面转为空头防守'},
        ]

    def explain_signal_conflicts(vol_ratio_pct_, scan_report_):
        """检测量比与 OBV/AD/MFI 资金流指标是否处于不一致分位。"""
        flow_keywords = ['OBV', 'AD', 'MFI', '能量潮', '累积/派发', 'ADOSC', '资金']
        flow_signals = [s for s in scan_report_.get('indicator_signals', [])
                        if any(k in s['cn_name'] for k in flow_keywords)]
        if not flow_signals:
            return ''
        flow_high = [s for s in flow_signals if s['percentile'] > 70]
        flow_low = [s for s in flow_signals if s['percentile'] < 30]
        if vol_ratio_pct_ < 30 and flow_high:
            names_ = '、'.join(sorted(set(s['cn_name'] for s in flow_high)))
            top_pct = max(s['percentile'] for s in flow_high)
            return (
                f"\n> **指标冲突解读**：量比指标反映的是当日成交相对近期均值的活跃程度，"
                f"而 {names_} 等指标更多反映量价资金流向或资金强弱位置。"
                f"当前量比仅 {vol_ratio_pct_:.0f}% 分位（偏弱），短线成交放量确认不足；"
                f"但部分量价资金流指标已处于偏高分位（最高 {top_pct:.0f}%），"
                f"提示前期资金累积充分但当下追涨性价比有限。\n"
            )
        if vol_ratio_pct_ > 70 and flow_low:
            names_ = '、'.join(sorted(set(s['cn_name'] for s in flow_low)))
            low_pct = min(s['percentile'] for s in flow_low)
            return (
                f"\n> **指标冲突解读**：量比指标反映的是当日成交相对近期均值的活跃程度，"
                f"而 {names_} 等指标更多反映量价资金流向或资金强弱位置。"
                f"当前量比 {vol_ratio_pct_:.0f}% 分位偏高，短线成交活跃；"
                f"但量价资金流指标处于偏低分位（最低 {low_pct:.0f}%），"
                f"提示成交活跃但资金累积尚不充分，需观察后续持续性。\n"
            )
        return ''

    def build_usage_boundary(symbol_code_, name_):
        """根据标的类型生成使用边界文案。"""
        bond_codes = {'TL0', 'T0', 'TF0', 'TS0', 'TL', 'T', 'TF', 'TS'}
        is_bond = symbol_code_ in bond_codes or any(symbol_code_.startswith(c) for c in ('TL0', 'T0', 'TF0', 'TS0'))
        if is_bond:
            return (
                f"本报告主要用于辅助判断 **{name_}** 短期技术状态，适用观察周期以 1—10 个交易日为主。"
                f"由于国债期货价格与收益率方向相反，技术面信号应结合资金面、货币政策预期、"
                f"现券收益率曲线、基差和跨期价差等因素综合使用。"
                f"技术指标主要反映交易行为和市场情绪变化，不单独构成久期配置或方向交易依据。"
            )
        return (
            f"本报告主要用于辅助判断 **{name_}** 短期技术状态，适用观察周期以 1—10 个交易日为主。"
            f"技术指标主要反映交易行为和市场情绪变化，需结合基本面、估值、行业景气和资金面综合使用，"
            f"不单独构成持仓决策依据。"
        )

    def build_five_dimensional_summary(matrix_, levels_, scan_report_):
        """按新版 SKILL 的五维框架生成二次归纳章节。"""
        macd_cross = '金叉' if macd[-1] > sig[-1] else '死叉'
        macd_zone = '零轴上方' if macd[-1] > 0 else '零轴下方'
        hist_delta = hist[-1] - hist[-2] if len(hist) >= 2 and np.isfinite(hist[-2]) else np.nan
        if not np.isfinite(hist_delta):
            hist_text = '柱体变化数据不足'
        elif hist[-1] > 0:
            hist_text = '柱体为正且扩张' if hist_delta > 0 else '柱体为正但收缩'
        else:
            hist_text = '柱体为负且负向扩大' if hist_delta < 0 else '柱体为负但负向收敛'

        if trend == '多头排列' and macd_cross == '金叉':
            trend_state, trend_consistency = '偏多', '高'
        elif trend == '空头排列' and macd_cross == '死叉':
            trend_state, trend_consistency = '偏空', '高'
        elif trend == '震荡整理' and macd_cross == '死叉':
            trend_state, trend_consistency = '中性偏弱', '中'
        elif trend == '震荡整理' and macd_cross == '金叉':
            trend_state, trend_consistency = '中性偏强', '中'
        else:
            trend_state, trend_consistency = '分歧', '低'
        trend_basis = (
            f"价格处于 {above_ma}/3 条短期均线上方，趋势判断为{trend}；"
            f"MACD DIF/DEA 为{macd_cross}，且位于{macd_zone}。"
        )

        weak_mom = sum([
            rsi6[-1] < 45,
            k_vals[-1] < d_vals[-1],
            j_vals[-1] < 30,
            hist[-1] < 0,
        ])
        hot_mom = sum([rsi6[-1] > 70, j_vals[-1] > 90, k_pct > 80])
        repair_mom = sum([rsi6[-1] > 50, k_vals[-1] > d_vals[-1], hist[-1] > 0])
        if hot_mom >= 2:
            momentum_state, momentum_consistency = '过热', '中'
        elif weak_mom >= 3:
            momentum_state, momentum_consistency = '转弱', '中高'
        elif repair_mom >= 2:
            momentum_state, momentum_consistency = '修复', '中'
        elif weak_mom >= 2:
            momentum_state, momentum_consistency = '偏弱', '中'
        else:
            momentum_state, momentum_consistency = '分歧', '低'
        momentum_basis = (
            f"RSI(6)={rsi6[-1]:.2f}（{rsi6_pct:.0f}%分位），"
            f"KDJ K={k_vals[-1]:.2f}/D={d_vals[-1]:.2f}/J={j_vals[-1]:.2f}，"
            f"MACD {hist_text}。"
        )

        if atr_pct_hist <= 10:
            volatility_state, volatility_consistency = '低波压缩', '高'
        elif atr_pct_hist < 30:
            volatility_state, volatility_consistency = '收敛', '中高'
        elif atr_pct_hist > 80:
            volatility_state, volatility_consistency = '高波动', '高'
        elif atr_pct_hist > 70:
            volatility_state, volatility_consistency = '扩张', '中高'
        else:
            volatility_state, volatility_consistency = '常态', '中'
        volatility_basis = (
            f"ATR(14)={atr14[-1]:.4f}，处于 {atr_pct_hist:.0f}% 分位；"
            f"价格处于{boll_status}，BOLL 区间为 {lower[-1]:.{price_decimal}f}~{upper[-1]:.{price_decimal}f}。"
        )

        flow_keywords = ['OBV', 'AD', 'MFI', '能量潮', '累积/派发', 'ADOSC']
        flow_signals = [
            s for s in scan_report_.get('indicator_signals', [])
            if any(k in s['cn_name'] for k in flow_keywords)
        ]
        flow_high = [s for s in flow_signals if s['percentile'] > 70]
        flow_low = [s for s in flow_signals if s['percentile'] < 30]
        if vol_ratio_pct < 30 and flow_high:
            volume_state, volume_consistency = '不配合但资金痕迹偏强', '低'
        elif vol_ratio_pct > 70 and flow_low:
            volume_state, volume_consistency = '放量但资金流偏弱', '低'
        elif vol_ratio_pct > 70 and not flow_low:
            volume_state, volume_consistency = '配合', '中'
        elif vol_ratio_pct < 30:
            volume_state, volume_consistency = '不配合', '中'
        else:
            volume_state, volume_consistency = '中性', '中'
        if flow_signals:
            flow_desc = '；'.join([
                f"{s['cn_name']} {s['percentile']:.0f}%分位"
                for s in flow_signals[:3]
            ])
        else:
            flow_desc = '未触发 OBV/AD/ADOSC/MFI 极端异常'
        volume_basis = f"量比 {vol_ratio_today:.2f}x，处于 {vol_ratio_pct:.0f}% 分位；{flow_desc}。"

        high_extreme = [s for s in scan_report_.get('indicator_signals', []) if s['percentile'] >= 90]
        low_extreme = [s for s in scan_report_.get('indicator_signals', []) if s['percentile'] <= 10]
        resonance = scan_report_.get('resonance_signals', [])
        if volatility_state == '低波压缩':
            risk_state = '低波压缩'
        elif len(high_extreme) >= 2:
            risk_state = '过热/拥挤'
        elif len(low_extreme) >= 2:
            risk_state = '过冷'
        elif resonance:
            risk_state = '异常共振'
        else:
            risk_state = '无明显极端'
        risk_consistency = '高' if resonance or len(high_extreme) + len(low_extreme) >= 3 else '中'
        risk_bits = []
        if high_extreme:
            risk_bits.append('高分位：' + '、'.join([f"{s['cn_name']}({s['percentile']:.0f}%)" for s in high_extreme[:3]]))
        if low_extreme:
            risk_bits.append('低分位：' + '、'.join([f"{s['cn_name']}({s['percentile']:.0f}%)" for s in low_extreme[:3]]))
        if resonance:
            risk_bits.append('共振：' + '、'.join([r['group'] + r['direction'] for r in resonance[:2]]))
        risk_basis = '；'.join(risk_bits) if risk_bits else '非核心指标未出现明显极端共振。'

        rows = [
            ('趋势', trend_state, trend_consistency, trend_basis),
            ('动量', momentum_state, momentum_consistency, momentum_basis),
            ('波动', volatility_state, volatility_consistency, volatility_basis),
            ('量价', volume_state, volume_consistency, volume_basis),
            ('位置风险', risk_state, risk_consistency, risk_basis),
        ]
        rows_md = "\n".join([f"| {d} | {s} | {c} | {b} |" for d, s, c, b in rows])

        if trend_state in ('偏多', '中性偏强') and momentum_state in ('修复', '过热'):
            direction_confirm = '趋势和动量相互支持，方向确认度较高。'
        elif trend_state in ('偏空', '中性偏弱') and momentum_state in ('转弱', '偏弱'):
            direction_confirm = '趋势结构和动量边际均偏弱，短线方向确认偏谨慎。'
        else:
            direction_confirm = '趋势与动量未形成充分同向验证，方向确认度有限。'

        if volume_state == '配合':
            quality_confirm = '量价维度提供配合，价格信号质量较好。'
        elif '不配合' in volume_state or '偏弱' in volume_state:
            quality_confirm = '量价维度未充分配合，突破或反弹的质量仍需成交确认。'
        else:
            quality_confirm = '量价维度中性，暂未显著增强或削弱方向信号。'

        if risk_state in ('低波压缩', '异常共振', '过热/拥挤'):
            risk_confirm = f'位置风险显示{risk_state}，后续若关键位被突破或跌破，波动放大概率上升。'
        elif risk_state == '过冷':
            risk_confirm = '位置风险偏过冷，若动量修复可关注超跌修复，但仍需趋势确认。'
        else:
            risk_confirm = '位置风险未见明显极端，风险主要来自趋势和量价是否继续分化。'

        latest_shape = recent_by_day[0] if recent_by_day else None
        if latest_shape:
            shape_confirm = (
                f"最新交易日形态为{latest_shape['names']}，方向{latest_shape['direction']}；"
                f"{latest_shape['explain']}"
            )
        else:
            shape_confirm = '最近 3 个交易日未识别到可用于验证的主要 K 线形态。'

        confirm_score = 0
        if '相互支持' in direction_confirm or '均偏弱' in direction_confirm:
            confirm_score += 1
        if volume_state == '配合':
            confirm_score += 1
        elif '不配合' in volume_state:
            confirm_score -= 1
        if risk_state in ('异常共振', '过热/拥挤', '低波压缩'):
            confirm_score -= 1
        if latest_shape and latest_shape['direction'] not in ('混合',):
            if (trend_state in ('偏多', '中性偏强') and latest_shape['direction'] == '偏多') or \
               (trend_state in ('偏空', '中性偏弱') and latest_shape['direction'] == '偏空'):
                confirm_score += 1
            else:
                confirm_score -= 1
        if confirm_score >= 2:
            confirm_level = '高'
        elif confirm_score <= -1:
            confirm_level = '中低'
        else:
            confirm_level = '中'

        res_str = '/'.join([f"{r['price']:.{price_decimal}f}" for r in levels_['resistances']]) or '无明显阻力'
        sup_str = '/'.join([f"{s['price']:.{price_decimal}f}" for s in levels_['supports']]) or '无明显支撑'

        return (
            "## 二、五维交叉验证摘要\n\n"
            f"**技术状态判断：** {core_view['judgement']}。"
            f"趋势和动量决定方向，量价决定可信度，波动和位置风险决定风险，K 线形态用于辅助确认或削弱信号。\n\n"
            "### 2.1 五维状态与内部一致性\n\n"
            "| 维度 | 状态 | 一致性 | 关键证据 |\n"
            "|------|------|--------|----------|\n"
            f"{rows_md}\n\n"
            "### 2.2 跨维度交叉验证\n\n"
            f"- **方向确认（趋势 x 动量）**：{direction_confirm}\n"
            f"- **质量确认（趋势 x 量价）**：{quality_confirm}\n"
            f"- **风险确认（动量 x 波动 x 位置风险）**：{risk_confirm}\n"
            f"- **形态验证**：{shape_confirm}\n\n"
            "### 2.3 信号确认度与关键位\n\n"
            f"**信号确认度：{confirm_level}。** "
            f"上方关注 {res_str}，下方关注 {sup_str}。"
            f"历史分位基于过去 {percentile_lookback} 个交易日；形态胜率基于过去约 3 年样本，"
            "仅代表历史统计规律，不代表本次必然兑现。"
        )

    # ---------- 7.4 调用 helpers 计算中间数据 ----------
    ma_dict = {'MA5': ma5[-1], 'MA10': ma10[-1], 'MA20': ma20[-1], 'MA60': ma60[-1]}
    boll_dict = {'BOLL上轨': upper[-1], 'BOLL中轨': middle[-1], 'BOLL下轨': lower[-1]}
    key_levels = build_key_levels(last_close, ma_dict, boll_dict, price_decimal)
    signal_matrix = build_signal_matrix()
    core_view = build_core_view(signal_matrix, key_levels)
    recent_by_day = summarize_recent_patterns_by_day(recent_results, n_days=3)
    valid_patterns = filter_valid_patterns(win_rate_results, min_occurrences=5)
    scenarios = build_scenarios(key_levels)
    conflict_text = explain_signal_conflicts(vol_ratio_pct, scan_report)
    usage_text = build_usage_boundary(symbol_code, name)
    section_five_dimensional_md = build_five_dimensional_summary(signal_matrix, key_levels, scan_report)

    # ---------- 7.5 报告章节组装（结论前置式买方研究报告版式） ----------

    # ===== Header =====
    latest_data_date = df['date'].iloc[-1].date()
    header_md = (
        f"# {name} ({symbol_code}) 技术形态分析报告\n\n"
        f"**标的:** {name}（{symbol_code}） | **分析日期:** {latest_data_date}  \n"
        f"**数据范围:** {df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()}（{len(df)} 交易日）"
    )

    # ===== 一、核心观点与交易提示 =====
    section_one_md = (
        "## 一、核心观点与交易提示\n\n"
        "| 维度 | 结论 |\n"
        "|------|------|\n"
        f"| 当前判断 | {core_view['judgement']} |\n"
        f"| 多空倾向 | {core_view['bias']} |\n"
        f"| 关键点位 | {core_view['levels']} |\n"
        f"| 操作提示 | {core_view['action']} |\n\n"
        "> 本表为研究结论，下方各章节给出推导依据。"
    )

    # ===== 三、基础信号证据表 =====
    evidence_type_map = {
        '趋势': '方向结构',
        '动量': '边际强弱',
        '超买超卖': '位置状态',
        '波动率': '环境状态',
        '成交量': '质量验证',
        '形态': '辅助验证',
    }
    matrix_rows_md = "\n".join([
        f"| {r['dim']} | {evidence_type_map.get(r['dim'], '基础证据')} | {r['signal']} | {r['comment']} |"
        for r in signal_matrix
    ])
    section_two_md = (
        "## 三、基础信号证据表\n\n"
        "> 本表是第二章“五维交叉验证摘要”的底层证据来源，不单独作为方向结论使用。\n\n"
        "| 证据维度 | 信号属性 | 当前信号 | 证据含义 |\n"
        "|----------|----------|----------|----------|\n"
        f"{matrix_rows_md}\n\n"
        f"> **证据分布**：偏多 {core_view['bull_c']} / 偏空 {core_view['bear_c']} / 分歧 {core_view['diverge_c']}（共 6 项基础信号）。"
    )

    # ===== 四、价格快照与关键点位 =====
    key_levels_rows = []
    for kl in key_levels['resistances']:
        key_levels_rows.append(
            f"| {kl['type']} | {kl['price']:.{price_decimal}f} | {kl['label']} | {kl['hint']} |"
        )
    for kl in key_levels['supports']:
        key_levels_rows.append(
            f"| {kl['type']} | {kl['price']:.{price_decimal}f} | {kl['label']} | {kl['hint']} |"
        )
    if key_levels_rows:
        key_levels_md = "\n".join(key_levels_rows)
    else:
        key_levels_md = "| - | - | - | 当前价格附近无明显均线/布林带参考 |"

    ma60_display = f"{ma60[-1]:.{price_decimal}f}" if not np.isnan(ma60[-1]) else "数据不足"

    section_three_md = (
        "## 四、价格快照与关键点位\n\n"
        "### 4.1 行情数据\n\n"
        "| 项目 | 数值 |\n"
        "|------|------|\n"
        f"| 最新收盘价 | **{last_close:.{price_decimal}f}** |\n"
        f"| 日涨跌幅 | {change_pct:+.2f}% |\n"
        f"| 最高价 | {last_high:.{price_decimal}f} |\n"
        f"| 最低价 | {last_low:.{price_decimal}f} |\n"
        f"| 开盘价 | {last_open:.{price_decimal}f} |\n"
        f"| 成交量 | {vol_display} |\n"
        f"| MA5 | {ma5[-1]:.{price_decimal}f} |\n"
        f"| MA10 | {ma10[-1]:.{price_decimal}f} |\n"
        f"| MA20 | {ma20[-1]:.{price_decimal}f} |\n"
        f"| MA60 | {ma60_display} |\n"
        f"| **趋势判断** | **{trend}**（{above_ma}/3 均线多头） |\n\n"
        "### 4.2 关键点位决策表\n\n"
        "| 点位类型 | 点位 | 来源 | 使用含义 |\n"
        "|---------|------|------|---------|\n"
        f"{key_levels_md}\n\n"
        "> 阻力位为价格上方最近的 2 个均线/BOLL 参考；支撑位为下方最近的 3 个参考（含下沿支撑）。两点位价格相差小于 0.1% 时合并显示。"
    )

    # ===== 五、核心技术指标 =====
    section_four_md = (
        "## 五、核心技术指标\n\n"
        f"| 指标 | 数值 | 历史分位（{percentile_lookback}日）| 状态 |\n"
        "|------|------|------|--------|\n"
        f"| MACD | {macd[-1]:.4f} | - | {macd_signal} |\n"
        f"| MACD Signal | {sig[-1]:.4f} | - | {hist_signal} |\n"
        f"| RSI(6) | {rsi6[-1]:.2f} | {rsi6_pct:.0f}% | {pct_label(rsi6_pct)} |\n"
        f"| RSI(12) | {rsi12[-1]:.2f} | {rsi12_pct:.0f}% | {pct_label(rsi12_pct)} |\n"
        f"| K | {k_vals[-1]:.2f} | {k_pct:.0f}% | {pct_label(k_pct)} |\n"
        f"| D | {d_vals[-1]:.2f} | {d_pct:.0f}% | {pct_label(d_pct)} |\n"
        f"| J | {j_vals[-1]:.2f} | {j_pct:.0f}% | {pct_label(j_pct)} |\n"
        f"| BOLL 上轨 | {upper[-1]:.{price_decimal}f} | - | {boll_status} |\n"
        f"| BOLL 中轨 | {middle[-1]:.{price_decimal}f} | - | - |\n"
        f"| BOLL 下轨 | {lower[-1]:.{price_decimal}f} | - | - |\n"
        f"| ATR(14) | {atr14[-1]:.4f} ({atr_pct:.2f}%) | {atr_pct_hist:.0f}% | {pct_label(atr_pct_hist)} |\n"
        f"| 量比 | {vol_ratio_today:.2f}x | {vol_ratio_pct:.0f}% | {pct_label(vol_ratio_pct)} |"
        f"\n> 注：表中「历史分位」基于过去 {percentile_lookback} 个交易日的数据计算。\n"
    )

    # ===== 五、K 线形态识别（降噪三层） =====
    # 5.1 最近 3 个交易日聚合
    if recent_by_day:
        recent_rows = "\n".join([
            f"| {r['date']} | {r['names']} | {r['direction']} | {r['explain']} |"
            for r in recent_by_day
        ])
        section_five_one = (
            "### 6.1 最新形态信号（最近 3 个交易日）\n\n"
            "| 日期 | 主要形态 | 方向 | 解释 |\n"
            "|------|----------|------|------|\n"
            f"{recent_rows}"
        )
    else:
        section_five_one = (
            "### 6.1 最新形态信号（最近 3 个交易日）\n\n"
            "*最近 3 个交易日内未检测到明显的 K 线形态。*"
        )

    # 5.1 形态详图（紧跟 5.1 表后，作为视觉化）
    if pattern_chart_paths:
        chart_imgs_md = "\n\n".join([
            f'<img src="{os.path.basename(p)}" width="750"/>' for p in pattern_chart_paths
        ])
        section_five_charts = (
            "**最新形态视觉化**（每张展示前后 12 根 K 线）：\n\n"
            f"{chart_imgs_md}"
        )
    else:
        section_five_charts = "*（未生成形态详图）*"

    # 5.2 近3日形态历史统计
    # 取近3日出现的不重复 (code, direction) 组合，记录出现日期，从 win_rate_results 中查找历史统计数据
    recent3_info = {}  # {(code, direction): {'name_cn': ..., 'dates': [date_str, ...]}}
    for r in recent_results:
        if r['days_ago'] < 3:
            key = (r['code'], r['direction'])
            if key not in recent3_info:
                recent3_info[key] = {'name_cn': r['name_cn'], 'dates': []}
            date_str = r['date'].strftime('%Y-%m-%d') if hasattr(r['date'], 'strftime') else str(r['date'])[:10]
            if date_str not in recent3_info[key]['dates']:
                recent3_info[key]['dates'].append(date_str)

    # 建立 win_rate_results 查找索引
    wr_index = {(w['code'], w['direction']): w for w in win_rate_results}

    if recent3_info:
        recent3_wr_rows = []
        for (code, direction), info in recent3_info.items():
            emoji = '🔴' if direction == '看涨' else '🟢'
            name_cn = info['name_cn']
            dates_str = ' / '.join(info['dates'])
            w = wr_index.get((code, direction))
            if w:
                s5 = w['horizon_stats'][5]
                recent3_wr_rows.append(
                    f"| {emoji} {name_cn} | {direction} | {dates_str} | {w['occurrences']} | "
                    f"{_wr_text(w['horizon_stats'][1])} | {_wr_text(w['horizon_stats'][3])} | "
                    f"{_wr_text(s5)} | "
                    f"{_fmt_pct(_avg_win(s5))} | {_fmt_pct(_avg_loss(s5))} | "
                    f"{_pl_ratio(s5)} | {_expected(s5)} |"
                )
            else:
                recent3_wr_rows.append(
                    f"| {emoji} {name_cn} | {direction} | {dates_str} | - | - | - | - | - | - | - | - |"
                )
        recent3_wr_md = "\n".join(recent3_wr_rows)

        # 生成分析提醒
        hints = []
        for (code, direction), info in recent3_info.items():
            name_cn = info['name_cn']
            w = wr_index.get((code, direction))
            if not w:
                continue
            s5 = w['horizon_stats'][5]
            if s5['total'] == 0:
                continue
            wr5 = s5['wins'] / s5['total'] * 100
            avg_w = _avg_win(s5)
            avg_l = _avg_loss(s5)
            ev = None
            if avg_w is not None and avg_l is not None:
                ev = (s5['wins'] / s5['total']) * avg_w + (1 - s5['wins'] / s5['total']) * avg_l
            occ = w['occurrences']
            emoji = '🔴' if direction == '看涨' else '🟢'

            if occ < 5:
                hints.append(f"- {emoji} **{name_cn}（{direction}）**：历史样本仅 {occ} 次，统计稳定性不足，信号仅供参考。")
            elif wr5 > 55 and ev is not None and ev > 0:
                hints.append(
                    f"- {emoji} **{name_cn}（{direction}）**：历史胜率 {wr5:.0f}%，5日期望 {ev:+.3f}%，"
                    f"过去3年方向预测价值相对稳定，与当前其他指标方向一致时参考意义较强。"
                )
            elif wr5 < 45 or (ev is not None and ev < 0):
                hints.append(
                    f"- {emoji} **{name_cn}（{direction}）**：历史胜率仅 {wr5:.0f}%，5日期望 "
                    f"{'不可计算' if ev is None else f'{ev:+.3f}%'}，过去3年方向预测价值有限，需结合其他指标验证。"
                )
            else:
                hints.append(
                    f"- {emoji} **{name_cn}（{direction}）**：历史胜率 {wr5:.0f}%，5日期望 "
                    f"{'不可计算' if ev is None else f'{ev:+.3f}%'}，方向预测价值中等，建议观察后续成交量配合。"
                )

        hints_md = "\n".join(hints) if hints else "- 以上形态历史统计数据不足，建议结合其他维度综合研判。"

        section_five_two = (
            "### 6.2 近3日形态历史统计\n\n"
            "> 以下为最近 3 个交易日识别到的形态在过去 3 年（756 日）的历史胜率、盈亏比与期望统计。"
            "出现次数为过去 3 年的样本量（不含最近 10 日），样本越少统计稳定性越低。\n\n"
            "| 形态 | 方向 | 日期 | 出现次数 | 1日胜率 | 3日胜率 | 5日胜率 | 5日均盈 | 5日均亏 | 5日盈亏比 | 5日期望 |\n"
            "|------|------|------|---------|--------|--------|--------|--------|--------|----------|--------|\n"
            f"{recent3_wr_md}\n\n"
            "**形态统计分析提醒**\n\n"
            f"{hints_md}\n\n"
            "> ⚠️ 历史胜率描述过去统计规律，不代表本次必然兑现；样本量 < 10 次时统计意义有限，需结合趋势、动量等多维度综合判断。"
        )
    else:
        section_five_two = (
            "### 6.2 近3日形态历史统计\n\n"
            "*最近 3 个交易日内未检测到明显形态，无统计数据可展示。*"
        )

    # 5.3 跳转
    section_five_three = (
        "### 6.3 完整数据\n\n"
        f"*完整 {len(recent_results)} 项形态明细、形态详图与全部胜率统计见 **附录 A**。*"
    )

    section_five_md = (
        "## 六、K 线形态识别\n\n"
        f"{section_five_one}\n\n"
        f"{section_five_charts}\n\n"
        f"{section_five_two}\n\n"
        f"{section_five_three}"
    )

    # ===== 六、后市情景推演 =====
    scenarios_rows = "\n".join([
        f"| {sc['name']} | {sc['trigger']} | {sc['meaning']} | {sc['action']} |"
        for sc in scenarios
    ])
    section_six_md = (
        "## 七、后市情景推演\n\n"
        "| 情景 | 触发条件 | 含义 | 应对思路 |\n"
        "|------|----------|------|----------|\n"
        f"{scenarios_rows}\n\n"
        "> 情景推演基于章节四的关键点位生成，仅作为研究讨论框架，不构成交易建议。"
    )

    # ===== 七、辅助信号与异常提示 =====
    section_seven_md = (
        "## 八、辅助信号与异常提示\n\n"
        f"{scan_report['report_md']}"
        f"{conflict_text}"
    )

    # ===== 八、使用边界 =====
    section_eight_md = (
        "## 九、使用边界\n\n"
        f"{usage_text}"
    )

    # ===== 九、风险声明 =====
    section_nine_md = (
        "## 十、风险声明\n\n"
        "本报告仅供信息参考，不构成投资建议。请在做出交易决策前结合基本面分析、个人风险承受能力综合判断。"
    )

    # ===== 附录 A =====
    # 完整 30 日形态明细
    if recent_results:
        recent_full_rows = []
        for r in recent_results:
            emoji = '🔴' if r['direction'] == '看涨' else '🟢'  # A股惯例:红涨绿跌
            recent_full_rows.append(
                f"| {emoji} {r['name_cn']} | {r['name_en']} | {r['date']} | "
                f"{r['days_ago']}d | {r['direction']} | {r['strength']} | {r['close']:.{price_decimal}f} |"
            )
        recent_full_md = "\n".join(recent_full_rows)
    else:
        recent_full_md = "*近30个交易日内未检测到明显的K线形态。*"

    # 完整胜率统计（≥3 次）
    wr_displayed = [w for w in win_rate_results if w['occurrences'] >= 3]
    if wr_displayed:
        wr_full_rows = []
        for w in wr_displayed:
            emoji = '🔴' if w['direction'] == '看涨' else '🟢'  # A股惯例:红涨绿跌
            hs = w['horizon_stats']
            s5 = hs[5]
            wr_full_rows.append(
                f"| {emoji} {w['name_cn']} | {w['name_en']} | {w['direction']} | {w['occurrences']} | "
                f"{_wr_text(hs[1])} | {_wr_text(hs[3])} | {_wr_text(hs[5])} | {_wr_text(hs[10])} | "
                f"{_fmt_pct(_avg_win(s5))} | {_fmt_pct(_avg_loss(s5))} | {_pl_ratio(s5)} | {_expected(s5)} |"
            )
        wr_full_md = "\n".join(wr_full_rows)
        wr_footer_md = (
            f"\n\n*共统计 {len(wr_displayed)} 个形态-方向组合（出现 ≥ 3 次）。"
            "胜率 > 50% + 盈亏比 > 1 + 5日期望 > 0 三者同时满足，方可视为该形态在过去 3 年具备方向预测价值。"
            "单一指标不构成交易决策依据，需结合样本量和市场环境综合判断。*"
        )
    else:
        wr_full_md = "*过去 3 年内未出现 ≥ 3 次的形态-方向组合，样本不足。*"
        wr_footer_md = ""

    appendix_md = (
        "## 附录 A：形态明细与详图\n\n"
        f"### A.1 近 30 日完整形态明细（共 {len(recent_results)} 个）\n\n"
        "| 形态（中文） | 形态（英文） | 日期 | 天前 | 方向 | 强度 | 收盘价 |\n"
        "|-------------|-------------|------|------|------|------|--------|\n"
        f"{recent_full_md}\n\n"
        "### A.2 历史形态汇总\n\n"
        "| 方向 | 数量 |\n"
        "|------|------|\n"
        f"| 🔴 看涨形态 | {bull_cnt} |\n"
        f"| 🟢 看跌形态 | {bear_cnt} |\n\n"
        f"**30 日汇总：** {len(recent_bull)} 个看涨形态 vs {len(recent_bear)} 个看跌形态\n\n"
        "### A.3 形态过去 3 年胜率统计（完整版）\n\n"
        "> **胜率定义**：形态出现后第 N 个交易日收盘价方向与形态预测方向一致的比例。\n"
        "> - 看涨形态成功 = N 日后收盘价 > 形态当日收盘价\n"
        "> - 看跌形态成功 = N 日后收盘价 < 形态当日收盘价\n"
        ">\n"
        "> **盈亏比与期望**（基于 5 日观察期，按\"形态视角收益\"统计：看涨形态收益用原始涨跌幅，看跌形态取反，正值即方向预测兑现）：\n"
        "> - **5日均盈**：胜的样本的形态视角收益均值（≥0）\n"
        "> - **5日均亏**：败的样本的形态视角收益均值（≤0）\n"
        "> - **5日盈亏比** = 5日均盈 / |5日均亏|，> 1 表示赢得比输得多\n"
        "> - **5日期望** = 胜率 × 均盈 + (1-胜率) × 均亏，正值表示该形态过去 3 年综合期望为正\n"
        ">\n"
        f"> **样本窗口**：过去 {actual_lookback} 个交易日（已扣除最后 {MAX_HORIZON} 日，以保证每个样本都有 10 日观察期）。\n"
        "> **样本要求**：仅展示过去 3 年内出现 ≥ 3 次的形态-方向组合。\n\n"
        "| 形态（中文） | 形态（英文） | 方向 | 出现次数 | 1日胜率 | 3日胜率 | 5日胜率 | 10日胜率 | 5日均盈 | 5日均亏 | 5日盈亏比 | 5日期望 |\n"
        "|-------------|-------------|------|---------|--------|--------|--------|---------|--------|--------|----------|--------|\n"
        f"{wr_full_md}{wr_footer_md}"
    )

    # ===== Footer =====
    footer_md = (
        f"*报告生成时间: {TODAY} {datetime.now().strftime('%H:%M:%S')}*  \n"
        "*数据来源: AKShare / Tushare / BaoStock（多源自动切换）*"
    )

    # ===== 拼接（章节之间用 horizontal rule 分隔） =====
    report_md = "\n\n---\n\n".join([
        header_md,
        section_one_md,
        section_five_dimensional_md,
        section_two_md,
        section_three_md,
        section_four_md,
        section_five_md,
        section_six_md,
        section_seven_md,
        section_eight_md,
        section_nine_md,
        appendix_md,
        footer_md,
    ])

    safe_name = symbol_code.replace('/', '_')
    report_path = os.path.join(output_dir, f'{safe_name}_技术分析报告_{TODAY}.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_md)
    print(f"报告已保存: {report_path}")

    print("\n" + "=" * 60)
    print("分析完成！")
    if chart_path:
        print(f"图表: {chart_path}")
    print(f"报告: {report_path}")
    print("=" * 60)

    return {
        'name': name,
        'symbol': symbol_code,
        'last_close': last_close,
        'change_pct': change_pct,
        'trend': trend,
        'macd_signal': macd_signal,
        'rsi6': rsi6[-1],
        'rsi6_pct': rsi6_pct,
        'recent_patterns': len(recent_results),
        'bull_patterns': len(recent_bull),
        'bear_patterns': len(recent_bear),
        'chart_path': chart_path,
        'pattern_chart_paths': pattern_chart_paths,
        'report_path': report_path,
        'scan_summary': scanner.summary_text(),
    }


# ==================== 命令行入口 ====================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='通用技术形态分析')
    parser.add_argument('--symbol', '-s', default='T0', help='标的代码（如 T0, sh000001, 600519）')
    parser.add_argument('--name', default='', help='标的名称（可选）')
    parser.add_argument('--asset-type', default='', help='资产类型（如 a_share, index, etf, hk_stock, us_stock, convertible_bond）')
    parser.add_argument('--market', default='', help='市场代码（如 SH, SZ, HK, US, CSI）')
    parser.add_argument('--ts-code', default='', help='Tushare 标准代码（可选）')
    parser.add_argument('--config', '-c', default=None, help='预设配置名（可选）')
    parser.add_argument('--days', '-d', type=int, default=120, help='图表显示天数（默认120）')
    parser.add_argument('--lookback', '-l', type=int, default=756, help='分位数回看窗口（默认756，即3年）')
    parser.add_argument('--output', '-o', default=None, help='输出目录（可选）')
    parser.add_argument('--no-chart', action='store_true', help='不生成图表')

    args = parser.parse_args()

    result = run_analysis(
        symbol_code=args.symbol,
        config_name=args.config,
        chart_days=args.days,
        percentile_lookback=args.lookback,
        output_dir=args.output,
        show_chart=not args.no_chart,
        name=args.name,
        asset_type=args.asset_type,
        market=args.market,
        ts_code=args.ts_code,
    )
