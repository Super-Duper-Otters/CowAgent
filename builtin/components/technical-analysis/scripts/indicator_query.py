# -*- coding: utf-8 -*-
"""
指标对话扩展接口 (Indicator Query)
==================================
为对话场景提供指标查询、对比分析、按问题自动选指标组的功能。

用法：
  from indicator_query import IndicatorQuery
  iq = IndicatorQuery(ind_full, ind_chart)
  
  # 场景1：用户问某个具体指标
  iq.query_indicator('cci14')  
  # → {'cn_name': 'CCI(14)', 'value': 128.5, 'percentile': 95.2, 'label': '极端高位（95%分位）', 'description': '...'}
  
  # 场景2：用户问方向性问题
  iq.answer_question('最近波动是不是变大了？')
  # → 自动选取波动率指标组，返回综合分析
  
  # 场景3：对比两个品种
  iq.compare('T', ind_full_T, ind_chart_T, 'TF', ind_full_TF, ind_chart_TF)
  # → 返回两个品种的多维度对比
"""

import numpy as np
from indicators_lib import (
    calc_all_indicators, calc_percentile, pct_label, last_value,
    INDICATOR_NAMES_CN, INDICATOR_CATEGORIES,
    AllIndicators,
)


# ==================== 问题 → 指标组映射 ====================

QUESTION_INDICATOR_MAP = {
    '波动': {
        'keywords': ['波动', '波幅', '波动率', '剧烈', '震荡', 'vola', 'volatility'],
        'indicators': ['atr14', 'atr7', 'natr14', 'boll_width', 'stddev20', 'boll_pctb'],
        'category': '波动率',
        'interpretation': {
            'high': '波动率处于历史高位，市场不确定性较大，注意控制仓位',
            'low': '波动率处于历史低位，市场处于平静期，但需警惕波动率突然放大',
            'normal': '波动率处于正常区间',
        },
    },
    '趋势': {
        'keywords': ['趋势', '方向', '多空', '上涨', '下跌', '涨跌', 'trend'],
        'indicators': ['adx14', 'adxr14', 'dx14', 'plus_di14', 'minus_di14', 'aroonosc14'],
        'category': '趋势强度',
        'interpretation': {
            'high': '趋势强度处于高位，当前趋势明确，顺势操作为宜',
            'low': '趋势强度处于低位，市场缺乏方向，适合区间操作',
            'normal': '趋势强度处于正常区间',
        },
    },
    '动量': {
        'keywords': ['动量', '强弱', '超买', '超卖', '过热', '冷', 'momentum'],
        'indicators': ['rsi6', 'rsi12', 'rsi14', 'cci14', 'cci20', 'willr', 'mfi14', 'ultosc', 'cmo14'],
        'category': '动量',
        'interpretation': {
            'high': '动量指标普遍偏高，存在短期过热风险，注意回调',
            'low': '动量指标普遍偏低，超卖迹象明显，关注反弹机会',
            'mixed': '动量指标方向不一致，市场分歧较大',
            'normal': '动量处于正常区间',
        },
    },
    '成交量': {
        'keywords': ['成交量', '量能', '放量', '缩量', 'volume', '交易量'],
        'indicators': ['obv', 'ad', 'adosc', 'mfi14'],
        'category': '成交量',
        'interpretation': {
            'high': '成交量指标活跃，市场参与度较高',
            'low': '成交量指标低迷，市场参与度较低',
            'normal': '成交量处于正常水平',
        },
    },
    '还能涨吗': {
        'keywords': ['还能涨', '还能跌', '能持续', '能不能', '会继续', '空间'],
        'indicators': ['adx14', 'adxr14', 'aroonosc14', 'rsi14', 'cci14', 'ultosc'],
        'category': '趋势+动量综合',
        'interpretation': None,  # 需要多维综合判断
    },
    '对比': {
        'keywords': ['对比', '比较', '谁强', '哪个好', 'compare', '区别'],
        'indicators': ['rsi6', 'adx14', 'natr14', 'cci14', 'mfi14', 'boll_width'],
        'category': '综合对比',
    },
}


# ==================== 指标查询接口 ====================

class IndicatorQuery:
    """
    指标对话查询接口。
    
    Parameters
    ----------
    ind_full : AllIndicators
        全量窗口指标数据
    ind_chart : AllIndicators
        图表窗口指标数据
    lookback : int
        分位数回看窗口
    """
    
    def __init__(self, ind_full, ind_chart, lookback=252):
        self.ind_full = ind_full
        self.ind_chart = ind_chart
        self.lookback = lookback
    
    def query_indicator(self, key, use_full=True):
        """
        查询单个指标的详细信息。
        
        Parameters
        ----------
        key : str
            指标 key，如 'cci14', 'adx14'
        use_full : bool
            是否使用全量窗口计算分位数
            
        Returns
        -------
        dict or None
            指标详情，包含 cn_name, value, percentile, label, description
        """
        # 查找指标所在的分组
        ind_data = self.ind_full if use_full else self.ind_chart
        group_names = ['trend', 'momentum', 'volatility', 'volume', 'strength']
        
        arr = None
        found_group = None
        for grp_name in group_names:
            grp = getattr(ind_data, grp_name)
            if hasattr(grp, key):
                arr = getattr(grp, key)
                found_group = grp_name
                break
        
        if arr is None:
            return {'error': f'指标 {key} 不存在', 'suggestions': self._suggest_similar(key)}
        
        arr = np.asarray(arr).ravel()
        val = last_value(arr)
        
        if np.isnan(val):
            return {'cn_name': INDICATOR_NAMES_CN.get(key, key), 'value': None, 'status': '无数据'}
        
        pct = calc_percentile(val, arr, lookback=self.lookback)
        cn_name = INDICATOR_NAMES_CN.get(key, key)
        category = INDICATOR_CATEGORIES.get(key, found_group)
        
        return {
            'key': key,
            'cn_name': cn_name,
            'category': category,
            'value': round(val, 4),
            'percentile': pct,
            'label': pct_label(pct) if not np.isnan(pct) else '数据不足',
            'interpretation': self._interpret_single(key, val, pct),
        }
    
    def query_category(self, category_name):
        """
        查询某类别的所有指标概况。
        
        Parameters
        ----------
        category_name : str
            类别名，如 '波动率', '动量', '趋势强度', '成交量'
            
        Returns
        -------
        dict
            {category, indicators: [...], summary}
        """
        ind_data = self.ind_full
        results = []
        
        group_map = {
            '趋势': 'trend', '动量': 'momentum', '波动率': 'volatility',
            '成交量': 'volume', '趋势强度': 'strength',
        }
        grp_name = group_map.get(category_name)
        if not grp_name:
            return {'error': f'未知类别: {category_name}', 'available': list(group_map.keys())}
        
        grp = getattr(ind_data, grp_name)
        fields = [f for f in dir(grp) if not f.startswith('_') and f not in ('count', 'index')]
        
        for field in fields:
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
            cn_name = INDICATOR_NAMES_CN.get(field, field)
            
            results.append({
                'key': field,
                'cn_name': cn_name,
                'value': round(val, 4),
                'percentile': pct,
                'label': pct_label(pct) if not np.isnan(pct) else '数据不足',
            })
        
        # 按分位数极端程度排序
        results.sort(key=lambda x: -abs((x['percentile'] or 50) - 50))
        
        # 汇总
        high_count = sum(1 for r in results if r['percentile'] and r['percentile'] >= 90)
        low_count = sum(1 for r in results if r['percentile'] and r['percentile'] <= 10)
        
        return {
            'category': category_name,
            'indicator_count': len(results),
            'high_count': high_count,
            'low_count': low_count,
            'indicators': results,
            'summary': f'{category_name}类共 {len(results)} 个指标，其中 {high_count} 个偏高、{low_count} 个偏低',
        }
    
    def answer_question(self, question):
        """
        根据自然语言问题自动选取指标组并回答。
        
        Parameters
        ----------
        question : str
            用户问题，如"最近波动是不是变大了？"、"这个趋势还能持续吗？"
            
        Returns
        -------
        dict
            {matched_topic, indicators, analysis, conclusion}
        """
        q_lower = question.lower()
        
        # 匹配话题
        best_match = None
        best_score = 0
        for topic, config in QUESTION_INDICATOR_MAP.items():
            score = sum(1 for kw in config['keywords'] if kw in q_lower)
            if score > best_score:
                best_score = score
                best_match = topic
        
        if not best_match or best_score == 0:
            # 没有明确匹配，返回全量概况
            return self._overview_answer()
        
        config = QUESTION_INDICATOR_MAP[best_match]
        indicator_results = []
        
        for key in config['indicators']:
            result = self.query_indicator(key)
            if result and 'error' not in result:
                indicator_results.append(result)
        
        # 生成分析
        analysis = self._analyze_group(indicator_results, config)
        
        return {
            'matched_topic': best_match,
            'topic_cn': config.get('category', best_match),
            'indicators': indicator_results,
            'analysis': analysis['details'],
            'conclusion': analysis['conclusion'],
        }
    
    def compare(self, name_a, ind_full_a, ind_chart_a, name_b, ind_full_b, ind_chart_b,
                indicator_keys=None):
        """
        对比两个品种/标的的指标。
        
        Parameters
        ----------
        name_a, name_b : str
            两个标的名称
        ind_full_a/b, ind_chart_a/b : AllIndicators
            两个标的的指标数据
        indicator_keys : list of str, optional
            要对比的指标列表，默认为综合对比指标组
            
        Returns
        -------
        dict
            对比结果
        """
        if indicator_keys is None:
            indicator_keys = ['rsi6', 'adx14', 'natr14', 'cci14', 'mfi14', 'boll_width', 'aroonosc14']
        
        comparisons = []
        for key in indicator_keys:
            result_a = self._query_from(ind_full_a, key)
            result_b = self._query_from(ind_full_b, key)
            
            if result_a and result_b and 'error' not in result_a and 'error' not in result_b:
                cn_name = INDICATOR_NAMES_CN.get(key, key)
                # 判断谁更强
                stronger = name_a if result_a['percentile'] > result_b['percentile'] else name_b
                diff = (result_a['percentile'] or 50) - (result_b['percentile'] or 50)
                
                comparisons.append({
                    'key': key,
                    'cn_name': cn_name,
                    f'{name_a}_value': result_a['value'],
                    f'{name_a}_pct': result_a['percentile'],
                    f'{name_b}_value': result_b['value'],
                    f'{name_b}_pct': result_b['percentile'],
                    'stronger': stronger,
                    'diff': diff,
                })
        
        # 统计谁整体更强
        a_wins = sum(1 for c in comparisons if c['stronger'] == name_a)
        b_wins = sum(1 for c in comparisons if c['stronger'] == name_b)
        
        return {
            'name_a': name_a,
            'name_b': name_b,
            'comparisons': comparisons,
            'a_wins': a_wins,
            'b_wins': b_wins,
            'conclusion': (f'{name_a} 在 {a_wins}/{len(comparisons)} 个指标上更强，'
                         f'{name_b} 在 {b_wins}/{len(comparisons)} 个指标上更强'),
        }
    
    # ---- 内部方法 ----
    
    def _query_from(self, ind_data, key):
        """从指定 AllIndicators 对象查询指标。"""
        group_names = ['trend', 'momentum', 'volatility', 'volume', 'strength']
        for grp_name in group_names:
            grp = getattr(ind_data, grp_name)
            if hasattr(grp, key):
                arr = np.asarray(getattr(grp, key)).ravel()
                val = last_value(arr)
                if np.isnan(val):
                    return None
                pct = calc_percentile(val, arr, lookback=self.lookback)
                return {
                    'key': key,
                    'cn_name': INDICATOR_NAMES_CN.get(key, key),
                    'value': round(val, 4),
                    'percentile': pct,
                    'label': pct_label(pct) if not np.isnan(pct) else '数据不足',
                }
        return None
    
    def _interpret_single(self, key, value, percentile):
        """单个指标的解读。"""
        if np.isnan(percentile):
            return '数据不足以判断'
        
        cn = INDICATOR_NAMES_CN.get(key, key)
        
        # CCI
        if key in ('cci14', 'cci20'):
            if value > 200:
                return f'{cn} 达到 {value:.1f}，远超 +200 极端超买区域，短期回调压力极大'
            elif value > 100:
                return f'{cn} 达到 {value:.1f}，突破 +100 超买线，价格偏离统计均值明显'
            elif value < -200:
                return f'{cn} 达到 {value:.1f}，远低于 -200 极端超卖区域，存在超跌反弹可能'
            elif value < -100:
                return f'{cn} 达到 {value:.1f}，跌破 -100 超卖线'
            return f'{cn} 处于正常范围（{value:.1f}）'
        
        # ADX
        if key in ('adx14', 'adxr14', 'dx14'):
            if value > 50:
                return f'{cn} 达到 {value:.1f}，趋势极强（>50），但需警惕趋势衰竭'
            elif value > 25:
                return f'{cn} 为 {value:.1f}，趋势正在形成'
            return f'{cn} 为 {value:.1f}，趋势较弱或无趋势'
        
        # NATR
        if key == 'natr14':
            return f'{cn} 为 {value:.2f}%，处于历史 {percentile:.0f}% 分位'
        
        # 默认
        return f'{cn} 当前值 {value:.4f}，处于历史 {percentile:.0f}% 分位'
    
    def _analyze_group(self, results, config):
        """分析一组指标并生成结论。"""
        if not results:
            return {'details': ['无数据'], 'conclusion': '数据不足，无法分析'}
        
        details = []
        high_count = 0
        low_count = 0
        
        for r in results:
            pct = r.get('percentile')
            if pct is None or np.isnan(pct):
                continue
            
            details.append(
                f"- {r['cn_name']}：{r['value']}（{pct:.0f}%分位，{r['label']}）"
            )
            
            if pct >= 90:
                high_count += 1
            elif pct <= 10:
                low_count += 1
        
        # 生成结论
        interpretation = config.get('interpretation', {})
        
        if interpretation is None:
            # 需要多维综合判断
            conclusion = self._multi_dim_conclusion(results)
        elif high_count >= 2 and low_count == 0:
            conclusion = interpretation.get('high', '多指标偏高')
        elif low_count >= 2 and high_count == 0:
            conclusion = interpretation.get('low', '多指标偏低')
        elif high_count > 0 and low_count > 0:
            conclusion = interpretation.get('mixed', '指标方向不一致')
        else:
            conclusion = interpretation.get('normal', '指标处于正常区间')
        
        return {'details': details, 'conclusion': conclusion}
    
    def _multi_dim_conclusion(self, results):
        """多维度综合判断结论。"""
        adx = next((r for r in results if r['key'] in ('adx14', 'adxr14')), None)
        rsi = next((r for r in results if 'rsi' in r['key']), None)
        cci = next((r for r in results if 'cci' in r['key']), None)
        
        parts = []
        
        if adx and adx.get('percentile', 50) > 70:
            parts.append(f'趋势强度明确（ADX {adx["percentile"]:.0f}%分位）')
        elif adx and adx.get('percentile', 50) < 30:
            parts.append('趋势强度较弱')
        
        if rsi and rsi.get('percentile', 50) > 80:
            parts.append('但动量已偏高，注意回调风险')
        elif rsi and rsi.get('percentile', 50) < 20:
            parts.append('动量偏低，超卖反弹可能')
        
        if cci and cci.get('percentile', 50) > 90:
            parts.append('CCI 进入极端区域')
        
        if not parts:
            return '各维度指标暂无明确信号'
        
        return '；'.join(parts) + '。'
    
    def _overview_answer(self):
        """全量概况回答。"""
        categories = {
            '趋势强度': 'strength',
            '波动率': 'volatility',
            '动量': 'momentum',
            '成交量': 'volume',
        }
        
        summary_parts = []
        for cn_name, grp_name in categories.items():
            result = self.query_category(cn_name)
            if 'error' in result:
                continue
            if result['high_count'] > 0 or result['low_count'] > 0:
                summary_parts.append(
                    f"{cn_name}类：{result['high_count']} 个偏高、{result['low_count']} 个偏低"
                )
        
        if not summary_parts:
            return {
                'matched_topic': '全量概况',
                'analysis': ['所有指标均处于正常区间，无异常信号'],
                'conclusion': '市场处于正常状态，无明显异常',
            }
        
        return {
            'matched_topic': '全量概况',
            'analysis': summary_parts,
            'conclusion': f'共发现异常：{"；".join(summary_parts)}',
        }
    
    def _suggest_similar(self, key):
        """当指标不存在时，推荐相似的指标。"""
        from indicators_lib import find_indicators
        # 模糊匹配
        results = find_indicators(keyword=key.replace('_', ''))
        if results:
            return [r['cn'] for r in results[:5]]
        return []
