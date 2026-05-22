# -*- coding: utf-8 -*-
"""
TA-Lib 全量技术指标预计算库
============================
一次性计算所有 TA-Lib 技术指标，按类别分组存储，供上层按需调用。

分类体系：
  1. 趋势类 (Trend)        — MA/EMA/DEMA/TEMA/KAMA/T3/SAR/HT_TRENDLINE...
  2. 动量类 (Momentum)     — MACD/RSI/CCI/MOM/ROC/TRIX/ULTOSC/STOCH...
  3. 波动率类 (Volatility)  — ATR/NATR/BOLL/STDDEV/TRANGE...
  4. 成交量类 (Volume)      — OBV/AD/ADOSC/MFI...
  5. 趋势强度 (Trend Strength) — ADX/ADXR/DX/MINUS_DI/PLUS_DI...
  6. 统计类 (Statistics)    — BETA/CORREL/LINEARREG...
  7. 数学变换 (Math)        — LN/SQRT/EXP/等（低优先级，按需加）

用法：
  from indicators_lib import calc_all_indicators
  ind = calc_all_indicators(high, low, close, volume, open_=open_p)
  # ind.trend.ema20        → EMA(20) 数组
  # ind.momentum.cci14     → CCI(14) 数组
  # ind.momentum.rsi6      → RSI(6) 数组
  # ind.volatility.atr14   → ATR(14) 数组
  # ind.volume.obv         → OBV 数组
  # ind.strength.adx14     → ADX(14) 数组
  # ind.trend.sar          → SAR 数组
"""

import numpy as np
import talib
from collections import namedtuple


# ==================== 数据容器 ====================

def _make_group(name, **kwargs):
    """创建一个带 __repr__ 的指标分组"""
    nt = namedtuple(name, sorted(kwargs.keys()))
    return nt(**kwargs)


class AllIndicators:
    """
    所有技术指标的统一容器。

    属性分组：
      .trend       — 趋势方向类指标
      .momentum    — 动量/振荡器类指标
      .volatility  — 波动率类指标
      .volume      — 成交量类指标
      .strength    — 趋势强度类指标
      .statistics  — 统计类指标（需双序列，可选计算）
    """
    def __init__(self, trend, momentum, volatility, volume, strength, statistics=None):
        self.trend = trend
        self.momentum = momentum
        self.volatility = volatility
        self.volume = volume
        self.strength = strength
        self.statistics = statistics

    def summary(self):
        """返回各分组的指标名称列表"""
        groups = [
            ('趋势类 Trend', self.trend),
            ('动量类 Momentum', self.momentum),
            ('波动率类 Volatility', self.volatility),
            ('成交量类 Volume', self.volume),
            ('趋势强度 Trend Strength', self.strength),
        ]
        if self.statistics:
            groups.append(('统计类 Statistics', self.statistics))
        lines = []
        for label, grp in groups:
            names = [f for f in dir(grp) if not f.startswith('_')]
            lines.append(f'{label} ({len(names)}):')
            lines.append(f'  {", ".join(names)}')
        return '\n'.join(lines)

    def __repr__(self):
        return f'<AllIndicators: trend={len([f for f in dir(self.trend) if not f.startswith("_")])}, ' \
               f'momentum={len([f for f in dir(self.momentum) if not f.startswith("_")])}, ' \
               f'volatility={len([f for f in dir(self.volatility) if not f.startswith("_")])}, ' \
               f'volume={len([f for f in dir(self.volume) if not f.startswith("_")])}, ' \
               f'strength={len([f for f in dir(self.strength) if not f.startswith("_")])}>'


# ==================== 分位数工具（复用） ====================

def calc_percentile(value, series, lookback=252):
    """计算当前值在过去 lookback 个周期中的分位数"""
    from scipy.stats import percentileofscore
    window = series[-lookback:]
    valid = window[~np.isnan(window)]
    if len(valid) < 30:
        return np.nan
    return round(percentileofscore(valid, value), 1)


def pct_label(pct):
    """分位数 → 中文标签（五档，纯客观描述）"""
    if np.isnan(pct) if isinstance(pct, float) else False:
        return '数据不足'
    if pct >= 90:
        return f'极端高位（{pct:.0f}%分位）'
    elif pct >= 70:
        return f'偏高（{pct:.0f}%分位）'
    elif pct >= 30:
        return f'中性（{pct:.0f}%分位）'
    elif pct >= 10:
        return f'偏低（{pct:.0f}%分位）'
    else:
        return f'极端低位（{pct:.0f}%分位）'


# ==================== 自研指标（TA-Lib 未涵盖） ====================

def _kdj(high, low, close, n=9):
    """KDJ 指标（TA-Lib 未提供原生实现）"""
    low_n  = pd_series_rolling_min(low, n)
    high_n = pd_series_rolling_max(high, n)
    rsv = (close - low_n) / (high_n - low_n) * 100
    k = np.zeros(len(close)); d = np.zeros(len(close))
    k[0] = 50; d[0] = 50
    for i in range(1, len(close)):
        k[i] = (2/3) * k[i-1] + (1/3) * _get(rsv, i)
        d[i] = (2/3) * d[i-1] + (1/3) * k[i]
    j = 3 * k - 2 * d
    return k, d, j


def _bollinger_pct(close, upper, middle, lower):
    """布林带 %B 指标：收盘价在布林带中的相对位置 (0~1)"""
    width = upper - lower
    width = np.where(width == 0, np.nan, width)
    return (close - lower) / width


def _bollinger_width(upper, lower):
    """布林带带宽：衡量波动率"""
    return (upper - lower) / _safe_mean(upper + lower) * 100


# ---- 内部工具 ----

def _safe_mean(arr):
    """安全均值，避免全 NaN"""
    m = np.nanmean(arr)
    return m if np.isfinite(m) else 1.0


def _get(arr, i):
    """安全取值"""
    if hasattr(arr, 'iloc'):
        return float(arr.iloc[i]) if i < len(arr) else np.nan
    return float(arr[i]) if i < len(arr) else np.nan


def pd_series_rolling_min(arr, window):
    import pandas as pd
    return pd.Series(arr).rolling(window=window, min_periods=1).min()


def pd_series_rolling_max(arr, window):
    import pandas as pd
    return pd.Series(arr).rolling(window=window, min_periods=1).max()


# ==================== 主计算函数 ====================

def calc_all_indicators(high, low, close, volume, open_=None):
    """
    计算所有 TA-Lib 技术指标。

    Parameters
    ----------
    high, low, close, volume : np.ndarray
        价格和成交量序列（np.float64）
    open_ : np.ndarray, optional
        开盘价序列，部分指标需要

    Returns
    -------
    AllIndicators
        分组指标容器
    """
    # 确保 numpy 数组
    high   = np.asarray(high, dtype=np.float64)
    low    = np.asarray(low, dtype=np.float64)
    close  = np.asarray(close, dtype=np.float64)
    volume = np.asarray(volume, dtype=np.float64)

    n = len(close)
    assert len(high) == len(low) == n, "所有输入序列长度必须一致"

    # ==================== 1. 趋势类 (Trend) ====================
    trend = {
        # --- 移动均线系列 ---
        'sma5':   talib.SMA(close, timeperiod=5),
        'sma10':  talib.SMA(close, timeperiod=10),
        'sma20':  talib.SMA(close, timeperiod=20),
        'sma60':  talib.SMA(close, timeperiod=60),
        'sma120': talib.SMA(close, timeperiod=120),

        'ema5':   talib.EMA(close, timeperiod=5),
        'ema10':  talib.EMA(close, timeperiod=10),
        'ema12':  talib.EMA(close, timeperiod=12),
        'ema20':  talib.EMA(close, timeperiod=20),
        'ema26':  talib.EMA(close, timeperiod=26),
        'ema60':  talib.EMA(close, timeperiod=60),

        'dema20':  talib.DEMA(close, timeperiod=20),
        'tema20':  talib.TEMA(close, timeperiod=20),
        'kama20':  talib.KAMA(close, timeperiod=20),
        'kama30':  talib.KAMA(close, timeperiod=30),
        't3_20':   talib.T3(close, timeperiod=20),
        'trima20': talib.TRIMA(close, timeperiod=20),
        'wma20':   talib.WMA(close, timeperiod=20),

        # --- 价格变换 ---
        'midpoint10': talib.MIDPOINT(close, timeperiod=10),
        'midprice20': talib.MIDPRICE(high, low, timeperiod=20),

        # --- SAR 抛物线止损 ---
        'sar':  talib.SAR(high, low, acceleration=0.02, maximum=0.2),
        # 'sarext': talib.SAREXT(high, low),  # 参数过多，按需手动调用

        # --- 希尔伯特变换 ---
        'ht_trendline': talib.HT_TRENDLINE(close),
        # ht_dcperiod, ht_dcphase, ht_phasor, ht_sine, ht_trendmode
        # 按需调用，不预计算（返回特殊格式）

        # --- MESA 自适应均线 ---
        # 'mama': talib.MAMA(close),  # 返回两个数组，按需调用
    }

    # ==================== 2. 动量类 (Momentum) ====================
    macd, macd_sig, macd_hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    macd_ext, macd_ext_sig, macd_ext_hist = talib.MACDEXT(close, fastperiod=12, slowperiod=26, signalperiod=9)
    macd_fix, macd_fix_sig, macd_fix_hist = talib.MACDFIX(close, signalperiod=9)

    k9, d9, j9 = _kdj(high, low, close, n=9)

    stoch_k, stoch_d = talib.STOCH(high, low, close,
                                    fastk_period=9, slowk_period=3, slowk_matype=0,
                                    slowd_period=3, slowd_matype=0)
    stochf_k, stochf_d = talib.STOCHF(high, low, close,
                                        fastk_period=14, fastd_period=3, fastd_matype=0)
    stochrsi_k, stochrsi_d = talib.STOCHRSI(close, timeperiod=14, fastk_period=5,
                                              fastd_period=3, fastd_matype=0)

    momentum = {
        # --- MACD 系列 ---
        'macd':        macd,
        'macd_signal': macd_sig,
        'macd_hist':   macd_hist,
        'macd_ext':        macd_ext,
        'macd_ext_signal': macd_ext_sig,
        'macd_ext_hist':   macd_ext_hist,
        'macd_fix':        macd_fix,
        'macd_fix_signal': macd_fix_sig,
        'macd_fix_hist':   macd_fix_hist,

        # --- RSI 系列 ---
        'rsi6':  talib.RSI(close, timeperiod=6),
        'rsi12': talib.RSI(close, timeperiod=12),
        'rsi14': talib.RSI(close, timeperiod=14),
        'rsi24': talib.RSI(close, timeperiod=24),

        # --- KDJ (自研) ---
        'k9':  k9,
        'd9':  d9,
        'j9':  j9,

        # --- 随机振荡器系列 ---
        'stoch_k':  stoch_k,
        'stoch_d':  stoch_d,
        'stochf_k': stochf_k,
        'stochf_d': stochf_d,
        'stochrsi_k': stochrsi_k,
        'stochrsi_d': stochrsi_d,
        'willr':    talib.WILLR(high, low, close, timeperiod=14),

        # --- CCI ---
        'cci14': talib.CCI(high, low, close, timeperiod=14),
        'cci20': talib.CCI(high, low, close, timeperiod=20),

        # --- 其他动量 ---
        'mom10': talib.MOM(close, timeperiod=10),
        'roc10': talib.ROC(close, timeperiod=10),
        'rocp10': talib.ROCP(close, timeperiod=10),
        'rocr10': talib.ROCR(close, timeperiod=10),
        'trix15': talib.TRIX(close, timeperiod=15),
        'ultosc': talib.ULTOSC(high, low, close, timeperiod1=7, timeperiod2=14, timeperiod3=28),
        'cmo14':  talib.CMO(close, timeperiod=14),
        'apo12':  talib.APO(close, fastperiod=12, slowperiod=26, matype=0),
        'ppo12':  talib.PPO(close, fastperiod=12, slowperiod=26, matype=0),

        # --- BOP ---
        'bop': talib.BOP(open_ if open_ is not None else close, high, low, close),

        # --- IMI (Intraday Momentum Index, 需要开盘价) ---
        'imi14': None,  # TA-Lib 无此函数，自研备用
    }

    # ==================== 3. 波动率类 (Volatility) ====================
    boll_upper, boll_mid, boll_lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)

    volatility = {
        # --- ATR 系列 ---
        'atr14':  talib.ATR(high, low, close, timeperiod=14),
        'atr7':   talib.ATR(high, low, close, timeperiod=7),
        'natr14': talib.NATR(high, low, close, timeperiod=14),  # 归一化 ATR

        # --- 真实波幅 ---
        'trange': talib.TRANGE(high, low, close),

        # --- 标准差 ---
        'stddev20': talib.STDDEV(close, timeperiod=20, nbdev=1),
        'var20':    talib.VAR(close, timeperiod=20, nbdev=1),

        # --- 布林带 ---
        'boll_upper': boll_upper,
        'boll_mid':   boll_mid,
        'boll_lower': boll_lower,
        'boll_pctb':  _bollinger_pct(close, boll_upper, boll_mid, boll_lower),  # %B
        'boll_width': _bollinger_width(boll_upper, boll_lower),  # 带宽

        # --- 平均偏差 ---
        'avgdev20': talib.AVGDEV(close, timeperiod=20),
    }

    # ==================== 4. 成交量类 (Volume) ====================
    volume_grp = {
        'obv':    talib.OBV(close, volume),
        'ad':     talib.AD(high, low, close, volume),
        'adosc':  talib.ADOSC(high, low, close, volume, fastperiod=3, slowperiod=10),
        'mfi14':  talib.MFI(high, low, close, volume, timeperiod=14),
    }

    # ==================== 5. 趋势强度类 (Trend Strength) ====================
    strength = {
        'adx14':     talib.ADX(high, low, close, timeperiod=14),
        'adxr14':    talib.ADXR(high, low, close, timeperiod=14),
        'dx14':      talib.DX(high, low, close, timeperiod=14),
        'plus_di14': talib.PLUS_DI(high, low, close, timeperiod=14),
        'minus_di14': talib.MINUS_DI(high, low, close, timeperiod=14),
        'plus_dm':   talib.PLUS_DM(high, low, timeperiod=14),
        'minus_dm':  talib.MINUS_DM(high, low, timeperiod=14),
        'aroon14':   talib.AROON(high, low, timeperiod=14),
        'aroonosc14': talib.AROONOSC(high, low, timeperiod=14),
    }

    # ==================== 6. 统计类 (Statistics) ====================
    # BETA 和 CORREL 需要两个标的，不预计算，提供函数接口
    statistics = None

    # ==================== 组装 ====================
    return AllIndicators(
        trend=_make_group('Trend', **trend),
        momentum=_make_group('Momentum', **momentum),
        volatility=_make_group('Volatility', **volatility),
        volume=_make_group('Volume', **volume_grp),
        strength=_make_group('Strength', **strength),
        statistics=statistics,
    )


# ==================== 统计类按需计算 ====================

def calc_beta(high0, low0, close0, high1, low1, close1, timeperiod=5):
    """计算两个标的的 Beta 系数"""
    return talib.BETA(
        np.asarray(high0, dtype=np.float64),
        np.asarray(high1, dtype=np.float64),
        timeperiod=timeperiod,
    )


def calc_correl(real0, real1, timeperiod=30):
    """计算两个序列的相关系数"""
    return talib.CORREL(
        np.asarray(real0, dtype=np.float64),
        np.asarray(real1, dtype=np.float64),
        timeperiod=timeperiod,
    )


def calc_linearreg(close, timeperiod=14):
    """线性回归"""
    return talib.LINEARREG(np.asarray(close, dtype=np.float64), timeperiod=timeperiod)


def calc_linearreg_slope(close, timeperiod=14):
    """线性回归斜率"""
    return talib.LINEARREG_SLOPE(np.asarray(close, dtype=np.float64), timeperiod=timeperiod)


def calc_linearreg_angle(close, timeperiod=14):
    """线性回归角度"""
    return talib.LINEARREG_ANGLE(np.asarray(close, dtype=np.float64), timeperiod=timeperiod)


# ==================== 索引字典（快速查找） ====================

# 中文名映射
INDICATOR_NAMES_CN = {
    # 趋势类
    'sma5': '5日简单均线', 'sma10': '10日简单均线', 'sma20': '20日简单均线',
    'sma60': '60日简单均线', 'sma120': '120日简单均线',
    'ema5': '5日指数均线', 'ema10': '10日指数均线', 'ema12': '12日指数均线',
    'ema20': '20日指数均线', 'ema26': '26日指数均线', 'ema60': '60日指数均线',
    'dema20': '20日双指数均线', 'tema20': '20日三指数均线',
    'kama20': '20日自适应均线', 'kama30': '30日自适应均线',
    't3_20': '20日T3均线', 'trima20': '20日三角均线', 'wma20': '20日加权均线',
    'midpoint10': '10日中点', 'midprice20': '20日中间价',
    'sar': '抛物线止损(SAR)', 'ht_trendline': '希尔伯特趋势线',

    # 动量类
    'macd': 'MACD', 'macd_signal': 'MACD信号线', 'macd_hist': 'MACD柱体',
    'rsi6': 'RSI(6)', 'rsi12': 'RSI(12)', 'rsi14': 'RSI(14)', 'rsi24': 'RSI(24)',
    'k9': 'KDJ-K', 'd9': 'KDJ-D', 'j9': 'KDJ-J',
    'stoch_k': '慢速K', 'stoch_d': '慢速D', 'stochf_k': '快速K', 'stochf_d': '快速D',
    'stochrsi_k': 'RSI随机K', 'stochrsi_d': 'RSI随机D',
    'willr': '威廉指标(W%R)', 'cci14': 'CCI(14)', 'cci20': 'CCI(20)',
    'mom10': '动量(10)', 'roc10': '变化率(10)', 'rocp10': '百分比变化率(10)',
    'rocr10': '比率变化率(10)', 'trix15': 'TRIX(15)', 'ultosc': '终极振荡器',
    'cmo14': 'CMO(14)', 'apo12': 'APO(12)', 'ppo12': 'PPO(12)', 'bop': '均衡力(BOP)',

    # 波动率类
    'atr14': 'ATR(14)', 'atr7': 'ATR(7)', 'natr14': '归一化ATR(14)',
    'trange': '真实波幅', 'stddev20': '标准差(20)', 'var20': '方差(20)',
    'boll_upper': '布林上轨', 'boll_mid': '布林中轨', 'boll_lower': '布林下轨',
    'boll_pctb': '布林%B', 'boll_width': '布林带宽', 'avgdev20': '平均偏差(20)',

    # 成交量类
    'obv': '能量潮(OBV)', 'ad': '累积/派发线(AD)',
    'adosc': 'AD振荡器', 'mfi14': 'MFI(14)',

    # 趋势强度类
    'adx14': 'ADX(14)', 'adxr14': 'ADXR(14)', 'dx14': 'DX(14)',
    'plus_di14': '+DI(14)', 'minus_di14': '-DI(14)',
    'plus_dm': '+DM(14)', 'minus_dm': '-DM(14)',
    'aroon14': 'AROON(14)', 'aroonosc14': 'AROON振荡器(14)',
}

# 类别映射
INDICATOR_CATEGORIES = {
    # 趋势类
    'sma5': '趋势', 'sma10': '趋势', 'sma20': '趋势', 'sma60': '趋势', 'sma120': '趋势',
    'ema5': '趋势', 'ema10': '趋势', 'ema12': '趋势', 'ema20': '趋势', 'ema26': '趋势', 'ema60': '趋势',
    'dema20': '趋势', 'tema20': '趋势', 'kama20': '趋势', 'kama30': '趋势',
    't3_20': '趋势', 'trima20': '趋势', 'wma20': '趋势',
    'midpoint10': '趋势', 'midprice20': '趋势',
    'sar': '趋势', 'ht_trendline': '趋势',
    # 动量类
    'macd': '动量', 'macd_signal': '动量', 'macd_hist': '动量',
    'macd_ext': '动量', 'macd_ext_signal': '动量', 'macd_ext_hist': '动量',
    'macd_fix': '动量', 'macd_fix_signal': '动量', 'macd_fix_hist': '动量',
    'rsi6': '动量', 'rsi12': '动量', 'rsi14': '动量', 'rsi24': '动量',
    'k9': '动量', 'd9': '动量', 'j9': '动量',
    'stoch_k': '动量', 'stoch_d': '动量', 'stochf_k': '动量', 'stochf_d': '动量',
    'stochrsi_k': '动量', 'stochrsi_d': '动量', 'willr': '动量',
    'cci14': '动量', 'cci20': '动量',
    'mom10': '动量', 'roc10': '动量', 'rocp10': '动量', 'rocr10': '动量',
    'trix15': '动量', 'ultosc': '动量', 'cmo14': '动量', 'apo12': '动量', 'ppo12': '动量', 'bop': '动量',
    # 波动率类
    'atr14': '波动率', 'atr7': '波动率', 'natr14': '波动率',
    'trange': '波动率', 'stddev20': '波动率', 'var20': '波动率',
    'boll_upper': '波动率', 'boll_mid': '波动率', 'boll_lower': '波动率',
    'boll_pctb': '波动率', 'boll_width': '波动率', 'avgdev20': '波动率',
    # 成交量类
    'obv': '成交量', 'ad': '成交量', 'adosc': '成交量', 'mfi14': '成交量',
    # 趋势强度类
    'adx14': '趋势强度', 'adxr14': '趋势强度', 'dx14': '趋势强度',
    'plus_di14': '趋势强度', 'minus_di14': '趋势强度',
    'plus_dm': '趋势强度', 'minus_dm': '趋势强度',
    'aroon14': '趋势强度', 'aroonosc14': '趋势强度',
}


def find_indicators(category=None, keyword=None):
    """
    按类别或关键词查找指标。

    Parameters
    ----------
    category : str, optional
        类别名称，如 '趋势', '动量', '波动率', '成交量', '趋势强度'
    keyword : str, optional
        关键词，支持中英文模糊匹配

    Returns
    -------
    list of dict
        [{'key': 'rsi6', 'cn': 'RSI(6)', 'category': '动量'}, ...]
    """
    results = []
    for key, cn in INDICATOR_NAMES_CN.items():
        cat = INDICATOR_CATEGORIES.get(key, '')
        if category and cat != category:
            continue
        if keyword:
            kw = keyword.lower()
            if kw not in key.lower() and kw not in cn.lower():
                continue
        results.append({'key': key, 'cn': cn, 'category': cat})
    return results


def last_value(arr):
    """安全获取数组最后一个有效值"""
    arr = np.asarray(arr).ravel()
    if len(arr) == 0:
        return np.nan
    for v in reversed(arr):
        if np.ndim(v) == 0 and np.isfinite(v):
            return float(v)
    return np.nan


if __name__ == '__main__':
    # 测试：用随机数据跑一遍
    import pandas as pd
    np.random.seed(42)
    n = 300
    close = 100 + np.cumsum(np.random.randn(n) * 0.3)
    high = close + np.abs(np.random.randn(n) * 0.2)
    low = close - np.abs(np.random.randn(n) * 0.2)
    volume = np.random.rand(n) * 1000000 + 500000
    open_ = close + np.random.randn(n) * 0.1

    print("计算所有指标...")
    ind = calc_all_indicators(high, low, close, volume, open_=open_)
    print(ind.summary())

    # 测试分位数
    print(f"\nRSI(6) 最新值: {last_value(ind.momentum.rsi6):.2f}")
    print(f"RSI(6) 分位数: {calc_percentile(last_value(ind.momentum.rsi6), ind.momentum.rsi6):.1f}%")
    print(f"ATR(14) 最新值: {last_value(ind.volatility.atr14):.4f}")

    # 测试查找
    print("\n--- 查找 'rsi' ---")
    for item in find_indicators(keyword='rsi'):
        print(f"  {item['key']}: {item['cn']} ({item['category']})")

    print("\n--- 查找类别 '波动率' ---")
    for item in find_indicators(category='波动率'):
        print(f"  {item['key']}: {item['cn']}")
