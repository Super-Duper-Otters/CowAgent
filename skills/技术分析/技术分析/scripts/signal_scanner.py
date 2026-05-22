# -*- coding: utf-8 -*-
"""
信号扫描引擎 (Signal Scanner)
==============================
全量指标异常检测 + 同类指标共振检测 + 形态↔指标交叉验证。

核心功能：
  1. 全量分位数扫描：对 83 个指标逐一计算历史分位数，识别异常值
  2. 同类指标共振：同一类别多个指标同时异常 → 高置信度信号
  3. 形态↔指标交叉验证：K线形态与指标信号互相确认
  4. 优先级分级：高/中/低三级，控制信息量

用法：
  from signal_scanner import SignalScanner
  scanner = SignalScanner(ind_full, ind_chart, recent_cdl_patterns)
  report = scanner.generate_report()
"""

import numpy as np
from collections import defaultdict
from indicators_lib import (
    calc_percentile, pct_label, last_value,
    INDICATOR_NAMES_CN, INDICATOR_CATEGORIES,
    AllIndicators,
)


# ==================== 配置 ====================

# 分位数异常阈值
EXTREME_HIGH = 90      # >90% 分位视为偏高
EXTREME_LOW = 10       # <10% 分位视为偏低
VERY_EXTREME_HIGH = 95 # >95% 视为极端偏高
VERY_EXTREME_LOW = 5   # <5% 视为极端偏低

# 核心指标（已展示在报告中的，不在异常扫描中重复报告）
CORE_INDICATORS = {
    'rsi6', 'rsi12', 'k9', 'd9', 'j9',
    'macd', 'macd_signal', 'macd_hist',
    'boll_upper', 'boll_mid', 'boll_lower',
    'atr14', 'sma5', 'sma10', 'sma20', 'sma60',
}

# 需要跳过的指标（通道/均线类不适合做分位数扫描，或信息冗余）
SKIP_INDICATORS = {
    # 布林带上下轨本身，保留 %B 和带宽
    'boll_upper', 'boll_mid', 'boll_lower',
    # 均线系列（趋势方向信息已由趋势评分覆盖）
    'sma5', 'sma10', 'sma20', 'sma60', 'sma120',
    'ema5', 'ema10', 'ema12', 'ema20', 'ema26', 'ema60',
    'dema20', 'tema20', 'kama20', 'kama30', 't3_20', 'trima20', 'wma20',
    'midpoint10', 'midprice20', 'ht_trendline',
    # MACD 变体（MACD 本身已展示）
    'macd_ext', 'macd_ext_signal', 'macd_ext_hist',
    'macd_fix', 'macd_fix_signal', 'macd_fix_hist',
    # SAR（趋势跟踪，需要收盘价上下文解释）
    'sar',
    # RSI 变体（RSI6/12 已展示）
    'rsi14', 'rsi24',
    # 随机振荡器变体（KDJ 已展示）
    'stoch_k', 'stoch_d', 'stochf_k', 'stochf_d', 'stochrsi_k', 'stochrsi_d',
    # KDJ 已展示
    'k9', 'd9', 'j9',
    # MACD 已展示
    'macd', 'macd_signal', 'macd_hist',
    # RSI 已展示
    'rsi6', 'rsi12',
    # BOP 需要特殊解释
    'bop',
    # 未实现的占位
    'imi14',
    # 纯波动通道（ATR 已展示）
    'trange', 'var20', 'avgdev20',
}

# 同类指标分组（用于共振检测）
RESONANCE_GROUPS = {
    '动量超买超卖': ['rsi6', 'rsi12', 'rsi14', 'rsi24', 'willr', 'cci14', 'cci20',
                     'stoch_k', 'stochf_k', 'stochrsi_k', 'cmo14'],
    '趋势强度': ['adx14', 'adxr14', 'dx14', 'aroonosc14'],
    '波动率': ['atr14', 'atr7', 'natr14', 'boll_width', 'stddev20'],
    '成交量': ['obv', 'ad', 'adosc', 'mfi14'],
    '趋势方向(DI)': ['plus_di14', 'minus_di14'],
}


# ==================== 指标方向性 ====================
# 某些指标天然有方向偏好，用于判断异常的"语义"
# 'high' = 值越大越异常, 'low' = 值越小越异常, 'both' = 两端都异常
INDICATOR_DIRECTION = {
    # 动量类：大部分 both
    'cci14': 'both', 'cci20': 'both',
    'willr': 'both',  # %R: >-20 超买, <-80 超卖
    'mom10': 'both',
    'roc10': 'both',
    'rocp10': 'both',
    'rocr10': 'both',
    'trix15': 'both',
    'ultosc': 'both',
    'cmo14': 'both',
    'apo12': 'both',
    'ppo12': 'both',
    # 波动率类
    'atr14': 'high', 'atr7': 'high', 'natr14': 'high',
    'boll_pctb': 'both',  # %B: >1 超买, <0 超卖
    'boll_width': 'high',  # 带宽越大波动越大
    'stddev20': 'high',
    # 成交量类
    'obv': 'both',  # OBV 趋势与价格背离时异常
    'ad': 'both',
    'adosc': 'both',
    'mfi14': 'both',  # >80 超买, <20 超卖
    # 趋势强度
    'adx14': 'high', 'adxr14': 'high', 'dx14': 'high',
    'aroonosc14': 'both',
    'plus_di14': 'both', 'minus_di14': 'both',
    'plus_dm': 'high', 'minus_dm': 'high',
}


# ==================== 信号扫描器 ====================

class SignalScanner:
    """
    全量信号扫描器。
    
    Parameters
    ----------
    ind_full : AllIndicators
        全量窗口（~312天）的指标数据，用于分位数计算
    ind_chart : AllIndicators
        图表窗口（~120天）的指标数据，用于取最新值
    recent_cdl_patterns : list of dict, optional
        近 30 天的 CDL K 线形态识别结果
    lookback : int
        分位数回看窗口（默认 252）
    """

    def __init__(self, ind_full, ind_chart, recent_cdl_patterns=None,
                 lookback=252):
        self.ind_full = ind_full
        self.ind_chart = ind_chart
        self.cdl_patterns = recent_cdl_patterns or []
        self.lookback = lookback
        
        # 扫描结果
        self.indicator_signals = []   # 单指标异常信号
        self.resonance_signals = []   # 共振信号
        self.cross_validations = []   # 形态↔指标交叉验证

    def scan_all(self):
        """执行全量扫描，返回汇总报告数据。"""
        self._scan_indicator_percentiles()
        self._detect_resonance()
        self._cross_validate_patterns()
        return self.generate_report()

    # ---- 1. 全量分位数扫描 ----

    def _scan_indicator_percentiles(self):
        """对每个非核心、非跳过指标计算分位数，识别异常。"""
        signals = []
        group_names = ['trend', 'momentum', 'volatility', 'volume', 'strength']
        
        for grp_name in group_names:
            grp = getattr(self.ind_full, grp_name)
            fields = [f for f in dir(grp) if not f.startswith('_') and f not in ('count', 'index')]
            
            for field in fields:
                if field in SKIP_INDICATORS:
                    continue
                    
                arr = getattr(grp, field)
                if arr is None:
                    continue
                arr = np.asarray(arr).ravel()
                if len(arr) == 0:
                    continue
                
                val = last_value(arr)
                if np.isnan(val):
                    continue
                
                pct = calc_percentile(val, arr, lookback=self.lookback)
                if np.isnan(pct):
                    continue
                
                # 判断异常
                if pct >= VERY_EXTREME_HIGH:
                    severity = 'high'
                    direction = 'extreme_high'
                elif pct <= VERY_EXTREME_LOW:
                    severity = 'high'
                    direction = 'extreme_low'
                elif pct >= EXTREME_HIGH:
                    severity = 'medium'
                    direction = 'high'
                elif pct <= EXTREME_LOW:
                    severity = 'medium'
                    direction = 'low'
                else:
                    continue  # 正常范围，不记录
                
                cn_name = INDICATOR_NAMES_CN.get(field, field)
                category = INDICATOR_CATEGORIES.get(field, grp_name)
                
                signals.append({
                    'key': field,
                    'cn_name': cn_name,
                    'category': category,
                    'value': round(val, 4),
                    'percentile': pct,
                    'severity': severity,
                    'direction': direction,
                    'label': pct_label(pct),
                    'description': self._describe_indicator(field, val, pct),
                })
        
        # 按严重度 + 分位数极端程度排序
        severity_order = {'high': 0, 'medium': 1, 'low': 2}
        signals.sort(key=lambda x: (
            severity_order.get(x['severity'], 9),
            -abs(x['percentile'] - 50)  # 越偏离 50 越靠前
        ))
        
        self.indicator_signals = signals

    def _describe_indicator(self, key, value, percentile):
        """生成指标的简短中文描述。"""
        cn = INDICATOR_NAMES_CN.get(key, key)
        
        # 动量类超买超卖
        if key in ('cci14', 'cci20'):
            if value > 100:
                return f'{cn} = {value:.1f}，远超 +100 超买线，价格偏离统计均值过多'
            elif value < -100:
                return f'{cn} = {value:.1f}，远低于 -100 超卖线，价格偏离统计均值过多'
            else:
                return f'{cn} = {value:.1f}'
        
        if key == 'willr':
            if value > -20:
                return f'{cn} = {value:.1f}，接近 -20 超买区域'
            elif value < -80:
                return f'{cn} = {value:.1f}，接近 -80 超卖区域'
            return f'{cn} = {value:.1f}'
        
        if key == 'mfi14':
            if value > 80:
                return f'{cn} = {value:.1f}，进入 >80 超买区域'
            elif value < 20:
                return f'{cn} = {value:.1f}，进入 <20 超卖区域'
            return f'{cn} = {value:.1f}'
        
        # 趋势强度
        if key in ('adx14', 'adxr14', 'dx14'):
            if value > 40:
                return f'{cn} = {value:.1f}，趋势强度极强（>40 通常为强趋势）'
            elif value > 25:
                return f'{cn} = {value:.1f}，趋势正在形成'
            return f'{cn} = {value:.1f}'
        
        # 波动率
        if key == 'boll_width':
            return f'{cn} = {value:.2f}%，布林带带宽处于历史{percentile:.0f}%分位'
        
        if key == 'boll_pctb':
            if value > 1:
                return f'{cn} = {value:.2f}，收盘价突破布林上轨'
            elif value < 0:
                return f'{cn} = {value:.2f}，收盘价跌破布林下轨'
            return f'{cn} = {value:.2f}'
        
        if key == 'natr14':
            return f'{cn} = {value:.2f}%，归一化波动率处于历史{percentile:.0f}%分位'
        
        # 默认
        return f'{cn} = {value:.4f}，处于历史{percentile:.0f}%分位'

    # ---- 2. 同类指标共振检测 ----

    def _detect_resonance(self):
        """检测同类指标的共振信号。"""
        resonances = []
        
        # 收集所有异常指标的 key 和 direction
        abnormal_indicators = {}
        for sig in self.indicator_signals:
            key = sig['key']
            # 判断是偏高还是偏低异常
            if sig['percentile'] >= EXTREME_HIGH:
                abnormal_indicators[key] = 'high'
            elif sig['percentile'] <= EXTREME_LOW:
                abnormal_indicators[key] = 'low'
        
        for group_name, group_keys in RESONANCE_GROUPS.items():
            # 筛选该组中实际有异常的指标
            high_abnormal = [k for k in group_keys if abnormal_indicators.get(k) == 'high']
            low_abnormal = [k for k in group_keys if abnormal_indicators.get(k) == 'low']
            
            # 同向共振：2+ 指标同时偏高/偏低
            if len(high_abnormal) >= 2:
                cn_names = [INDICATOR_NAMES_CN.get(k, k) for k in high_abnormal]
                resonances.append({
                    'group': group_name,
                    'direction': '偏高共振',
                    'indicators': high_abnormal,
                    'cn_names': cn_names,
                    'count': len(high_abnormal),
                    'severity': 'high',
                    'description': f'{group_name}：{len(high_abnormal)} 个指标同时处于历史高位（{"、".join(cn_names)}），动量过热信号明确',
                })
            
            if len(low_abnormal) >= 2:
                cn_names = [INDICATOR_NAMES_CN.get(k, k) for k in low_abnormal]
                resonances.append({
                    'group': group_name,
                    'direction': '偏低共振',
                    'indicators': low_abnormal,
                    'cn_names': cn_names,
                    'count': len(low_abnormal),
                    'severity': 'high',
                    'description': f'{group_name}：{len(low_abnormal)} 个指标同时处于历史低位（{"、".join(cn_names)}），动量超卖信号明确',
                })
            
            # 反向共振：如 +DI 高但 -DI 低 = 方向性极强
            if group_name == '趋势方向(DI)':
                if 'plus_di14' in abnormal_indicators and 'minus_di14' in abnormal_indicators:
                    if (abnormal_indicators['plus_di14'] == 'high' and 
                        abnormal_indicators['minus_di14'] == 'low'):
                        resonances.append({
                            'group': group_name,
                            'direction': '多空方向极化',
                            'indicators': ['plus_di14', 'minus_di14'],
                            'cn_names': ['+DI(14)', '-DI(14)'],
                            'count': 2,
                            'severity': 'high',
                            'description': '+DI 处于高位、-DI 处于低位，多头方向极其明确',
                        })
                    elif (abnormal_indicators['plus_di14'] == 'low' and 
                          abnormal_indicators['minus_di14'] == 'high'):
                        resonances.append({
                            'group': group_name,
                            'direction': '多空方向极化',
                            'indicators': ['plus_di14', 'minus_di14'],
                            'cn_names': ['+DI(14)', '-DI(14)'],
                            'count': 2,
                            'severity': 'high',
                            'description': '-DI 处于高位、+DI 处于低位，空头方向极其明确',
                        })
        
        self.resonance_signals = resonances

    # ---- 3. 形态 ↔ 指标交叉验证 ----

    def _cross_validate_patterns(self):
        """将 CDL 形态与指标信号交叉验证。"""
        validations = []
        
        # 3a. CDL 形态与动量指标验证
        recent_bull = [p for p in self.cdl_patterns if p.get('direction') == 'Bullish']
        recent_bear = [p for p in self.cdl_patterns if p.get('direction') == 'Bearish']
        
        if recent_bull:
            # 检查动量指标是否支持看多
            mom_high = [s for s in self.indicator_signals 
                       if s['category'] == '动量' and s['direction'] in ('high', 'extreme_high')]
            if mom_high:
                validations.append({
                    'type': '形态+指标共振',
                    'direction': '看多',
                    'pattern_count': len(recent_bull),
                    'indicator_count': len(mom_high),
                    'patterns': [p.get('name_cn', p.get('name_en', '')) for p in recent_bull[-3:]],
                    'indicators': [s['cn_name'] for s in mom_high[:3]],
                    'description': (f'近 30 日识别 {len(recent_bull)} 个看多形态'
                                   f'（{"、".join([p.get("name_cn","") for p in recent_bull[-3:]])}）'
                                   f'，同时 {len(mom_high)} 个动量指标处于高位'
                                   f'（{"、".join([s["cn_name"] for s in mom_high[:3]])}），形态与指标共振看多'),
                })
        
        if recent_bear:
            mom_low = [s for s in self.indicator_signals 
                      if s['category'] == '动量' and s['direction'] in ('low', 'extreme_low')]
            if mom_low:
                validations.append({
                    'type': '形态+指标共振',
                    'direction': '看空',
                    'pattern_count': len(recent_bear),
                    'indicator_count': len(mom_low),
                    'patterns': [p.get('name_cn', p.get('name_en', '')) for p in recent_bear[-3:]],
                    'indicators': [s['cn_name'] for s in mom_low[:3]],
                    'description': (f'近 30 日识别 {len(recent_bear)} 个看空形态'
                                   f'（{"、".join([p.get("name_cn","") for p in recent_bear[-3:]])}）'
                                   f'，同时 {len(mom_low)} 个动量指标处于低位'
                                   f'（{"、".join([s["cn_name"] for s in mom_low[:3]])}），形态与指标共振看空'),
                })
        
        # 3b. 形态与指标矛盾检测（分歧信号）
        if recent_bull and not mom_high:
            mom_low = [s for s in self.indicator_signals 
                      if s['category'] == '动量' and s['direction'] in ('low', 'extreme_low')]
            if mom_low:
                validations.append({
                    'type': '形态+指标分歧',
                    'direction': '警告',
                    'description': (f'⚠️ 分歧信号：近 30 日有 {len(recent_bull)} 个看多形态，'
                                   f'但动量指标（{"、".join([s["cn_name"] for s in mom_low[:3]])}）'
                                   f'处于低位，形态信号可能不可靠'),
                })
        
        if recent_bear and not mom_low:
            mom_high = [s for s in self.indicator_signals 
                       if s['category'] == '动量' and s['direction'] in ('high', 'extreme_high')]
            if mom_high:
                validations.append({
                    'type': '形态+指标分歧',
                    'direction': '警告',
                    'description': (f'⚠️ 分歧信号：近 30 日有 {len(recent_bear)} 个看空形态，'
                                   f'但动量指标（{"、".join([s["cn_name"] for s in mom_high[:3]])}）'
                                   f'处于高位，形态信号可能不可靠'),
                })
        
        self.cross_validations = validations

    # ---- 4. 报告生成 ----

    def generate_report(self):
        """生成 Markdown 格式的信号扫描报告段落。"""
        sections = []
        
        # 4a. 异常指标信号
        if self.indicator_signals:
            high_signals = [s for s in self.indicator_signals if s['severity'] == 'high']
            medium_signals = [s for s in self.indicator_signals if s['severity'] == 'medium']
            
            section = "### 非核心指标异常信号\n\n"
            section += "> 以下指标不在常规展示中，但因处于历史极端分位，自动纳入关注。\n\n"
            
            if high_signals:
                section += f"#### 高优先级信号（{len(high_signals)} 个）\n\n"
                section += "| 指标 | 当前值 | 历史分位 | 状态 | 说明 |\n"
                section += "|------|--------|---------|------|------|\n"
                for s in high_signals:
                    section += f"| {s['cn_name']} | {s['value']} | {s['percentile']:.0f}% | {s['label']} | {s['description']} |\n"
                section += "\n"
            
            if medium_signals:
                section += f"#### 中优先级信号（{len(medium_signals)} 个）\n\n"
                section += "| 指标 | 当前值 | 历史分位 | 状态 | 说明 |\n"
                section += "|------|--------|---------|------|------|\n"
                for s in medium_signals[:5]:  # 最多展示 5 个中优先级
                    section += f"| {s['cn_name']} | {s['value']} | {s['percentile']:.0f}% | {s['label']} | {s['description']} |\n"
                if len(medium_signals) > 5:
                    section += f"\n*...另有 {len(medium_signals) - 5} 个中优先级信号未展示*\n"
                section += "\n"
            
            sections.append(section)
        
        # 4b. 同类指标共振
        if self.resonance_signals:
            section = "### 同类指标共振检测\n\n"
            section += "> 同类多个指标同时异常，信号置信度高于单一指标。\n\n"
            
            for r in self.resonance_signals:
                section += f"- **{r['group']}（{r['direction']}）**：{r['description']}\n"
            section += "\n"
            sections.append(section)
        
        # 4c. 形态 ↔ 指标交叉验证
        if self.cross_validations:
            section = "### 形态 ↔ 指标交叉验证\n\n"
            
            for v in self.cross_validations:
                section += f"- {v['description']}\n"
            section += "\n"
            sections.append(section)
        
        # 如果没有任何信号
        if not sections:
            sections.append("*非核心指标未见异常信号，所有指标处于正常区间。*\n\n")
        
        return {
            'has_signals': bool(self.indicator_signals or self.resonance_signals or self.cross_validations),
            'indicator_count': len(self.indicator_signals),
            'resonance_count': len(self.resonance_signals),
            'cross_validation_count': len(self.cross_validations),
            'report_md': '\n'.join(sections),
            'indicator_signals': self.indicator_signals,
            'resonance_signals': self.resonance_signals,
            'cross_validations': self.cross_validations,
        }

    def summary_text(self):
        """生成一句话摘要。"""
        parts = []
        if self.indicator_signals:
            high = sum(1 for s in self.indicator_signals if s['severity'] == 'high')
            medium = sum(1 for s in self.indicator_signals if s['severity'] == 'medium')
            if high:
                parts.append(f'{high} 个高优先级异常')
            if medium:
                parts.append(f'{medium} 个中优先级异常')
        if self.resonance_signals:
            parts.append(f'{len(self.resonance_signals)} 组共振信号')
        if self.cross_validations:
            parts.append(f'{len(self.cross_validations)} 条交叉验证')
        
        if parts:
            return f'扫描发现：{"，".join(parts)}。'
        return '非核心指标未见异常，所有指标处于正常区间。'
