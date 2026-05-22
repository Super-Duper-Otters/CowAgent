# MEMORY.md - 长期记忆

## 项目信息
- 项目：`ta-pattern` 技术分析 skill（v0.0.8-basic）
- 位置：`D:\浙商\AI赋能固收投研\技术分析skill\v0.0.8-basic`
- 主脚本：`scripts/analyze_universal.py`
- 五维框架：趋势方向 / 动量状态 / 波动环境 / 量价关系 / 极端值预警

## 用户偏好
- 胜率回看窗口：3年（756交易日），2026-05-04 从 1年（252）改为 3年
- 5.2 节：不做筛选，展示近3日形态的历史胜率统计 + 自动文字提醒

## 技术要点
- `df_full` 切片需同时覆盖 `chart_days`、`percentile_lookback`、`WR_LOOKBACK + MAX_HORIZON`，否则胜率回看窗口会被截断
- 数据源优先级：AKShare → Tushare → 腾讯/新浪财经 → Baostock
- T0 数据量约 2252 条（2017-01 至今），足以支撑 3 年回看
