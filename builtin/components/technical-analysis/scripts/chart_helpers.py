"""
chart_helpers.py — 共享图表生成工具
analyze_t_future.py 和 analyze_universal.py 共用
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

BULL_COLOR = '#E53935'   # 阳线（债市 convention：红涨绿跌）
BEAR_COLOR = '#43A047'   # 阴线
REF_COLOR  = '#1565C0'   # 参考线
BK_COLOR   = '#FAFAFA'


def _plot_pattern_detail(pattern_item, df, idx, price_decimal, output_dir, safe_name, today_str):
    """
    为单个 K 线形态绘制放大详图。

    参数：
        pattern_item : dict  形态信息（code, date, direction, signal, strength 等）
        df           : pd.DataFrame  含 date/open/high/low/close 列
        idx          : int  形态在 df 中的行索引
        price_decimal: int  价格小数位数
        output_dir   : str  输出目录
        safe_name    : str  标的名称（用于文件名）
        today_str    : str  今日日期字符串
    """
    WINDOW = 12  # 前后展示窗口

    # 取窗口数据（防止越界）
    start = max(0, idx - WINDOW)
    end   = min(len(df), idx + WINDOW + 1)
    win_df = df.iloc[start:end].reset_index(drop=True)
    rel_idx = idx - start  # 形态在窗口内的相对位置

    open_p  = win_df['open'].values
    high_p  = win_df['high'].values
    low_p   = win_df['low'].values
    close_p = win_df['close'].values
    dates   = win_df['date'].values

    fig, ax = plt.subplots(figsize=(10, 5.5))
    fig.patch.set_facecolor(BK_COLOR)
    ax.set_facecolor(BK_COLOR)

    n = len(win_df)
    xs = np.arange(n)

    # 均线
    ma5  = pd.Series(close_p).rolling(5,  min_periods=1).mean().values
    ma10 = pd.Series(close_p).rolling(10, min_periods=1).mean().values
    if n >= 5:
        ax.plot(xs, ma5,  color='#2196F3', lw=0.9, alpha=0.7, label='MA5')
    if n >= 10:
        ax.plot(xs, ma10, color='#FF9800', lw=0.9, alpha=0.7, label='MA10')

    # 绘制 K 线
    for i in range(n):
        o, h, l, c = open_p[i], high_p[i], low_p[i], close_p[i]
        color = BULL_COLOR if c >= o else BEAR_COLOR
        ax.plot([i, i], [l, h], color=color, lw=0.9)
        body_bottom = min(o, c)
        body_height = abs(c - o)
        body_height = max(body_height, 1e-6)
        ax.plot([i, i], [body_bottom, body_bottom + body_height],
                color=color, lw=3.5)

    # 形态 K 线加粗 + 颜色标注（橙色高亮）
    ax.plot([rel_idx, rel_idx],
            [low_p[rel_idx], high_p[rel_idx]],
            color='#FF6F00', lw=3.0, zorder=5)
    body_b = min(open_p[rel_idx], close_p[rel_idx])
    body_h = max(abs(close_p[rel_idx] - open_p[rel_idx]), 1e-6)
    ax.plot([rel_idx, rel_idx],
            [body_b, body_b + body_h],
            color='#FF6F00', lw=6.0, zorder=6)

    # 关键价位水平线
    ref_prices = {
        f'形态开盘 {open_p[rel_idx]:.{price_decimal}f}': open_p[rel_idx],
        f'形态收盘 {close_p[rel_idx]:.{price_decimal}f}': close_p[rel_idx],
    }
    if rel_idx > 0:
        ref_prices[f'前收 {close_p[rel_idx-1]:.{price_decimal}f}'] = close_p[rel_idx - 1]
        ref_prices[f'前高 {high_p[rel_idx-1]:.{price_decimal}f}']  = high_p[rel_idx - 1]
        ref_prices[f'前低 {low_p[rel_idx-1]:.{price_decimal}f}']  = low_p[rel_idx - 1]
    line_colors = [REF_COLOR, '#FF9800', '#7B1FA2', '#00695C', '#AD1457']
    for (lbl, price), lc in zip(ref_prices.items(), line_colors):
        ax.axhline(price, color=lc, lw=0.6, ls='--', alpha=0.7)
        ax.text(n + 0.3, price, lbl, fontsize=7, va='center', color=lc, alpha=0.9)

    # X轴标签
    tick_step = max(1, n // 8)
    ax.set_xticks(range(0, n, tick_step))
    ax.set_xticklabels([str(pd.Timestamp(dates[i]).date()) for i in range(0, n, tick_step)],
                       rotation=45, fontsize=7.5)

    ax.set_xlim(-1, n + 5)
    y_min = np.nanmin(low_p) * 0.998
    y_max = np.nanmax(high_p) * 1.002
    ax.set_ylim(y_min, y_max)
    ax.yaxis.set_tick_params(labelsize=8)

    # 标题
    name_cn  = pattern_item.get('name_cn', pattern_item.get('code', ''))
    name_en  = pattern_item.get('name_en', '')
    direction = pattern_item.get('direction', '')
    signal   = pattern_item.get('signal', 100)
    strength = pattern_item.get('strength', '中')
    ptype    = '看涨' if signal > 0 else '看跌'
    arrow    = '▲'   if signal > 0 else '▼'
    color    = BULL_COLOR if signal > 0 else BEAR_COLOR

    title = (f'{arrow} {name_cn}（{name_en}）{direction}  |  '
             f'日期: {pattern_item["date"]}  |  强度: {strength}')
    ax.set_title(title, fontsize=11, fontweight='bold', color=color, pad=8)

    # 标注上下影线长度
    pt_high  = high_p[rel_idx]
    pt_low   = low_p[rel_idx]
    pt_open  = open_p[rel_idx]
    pt_close = close_p[rel_idx]
    upper_shadow = pt_high - max(pt_open, pt_close)
    lower_shadow = min(pt_open, pt_close) - pt_low
    ax.text(rel_idx, pt_high  + (y_max - y_min) * 0.012,
            f'上影{upper_shadow:.{price_decimal}f}', ha='center', fontsize=7,
            color='#555', style='italic')
    ax.text(rel_idx, pt_low - (y_max - y_min) * 0.012,
            f'下影{lower_shadow:.{price_decimal}f}', ha='center', fontsize=7,
            color='#555', style='italic')

    ax.grid(True, alpha=0.18, ls=':')
    ax.legend(loc='upper left', fontsize=8, framealpha=0.7)
    plt.tight_layout()

    # 保存
    os.makedirs(output_dir, exist_ok=True)
    fname = (f'{safe_name}_PATTERN_{pattern_item["code"]}_{pattern_item["date"]}'
             .replace('/', '_'))
    path = os.path.join(output_dir, f'{fname}.png')
    plt.savefig(path, dpi=150, bbox_inches='tight', facecolor=BK_COLOR)
    plt.close()
    return path
