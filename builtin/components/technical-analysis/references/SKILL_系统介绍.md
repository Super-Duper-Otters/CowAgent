# TA-Pattern Skill 系统介绍

> **版本：** 1.0  
> **路径：** `D:\浙商\AI赋能固收投研\技术分析skill\ta_pattern_skill\skill_ta_pattern\`  
> **更新时间：** 2026-04-14

> **说明：** 本文档是旧版系统设计背景说明，部分路径、数据源、输出格式和图表标记规则已经落后于 `v0.0.8-basic` 当前代码。当前可执行规范以仓库根目录的 `SKILL.md`、`README.md` 和 `scripts/analyze_universal.py` 为准。

---

## 一、Skill 概述

### 1.1 定位与目标

TA-Pattern Skill 是一款专注于**技术形态识别**的投研辅助工具，基于 TA-Lib 技术分析库实现对 K 线形态的自动识别，支持国债期货、股票指数及用户指定标的的技术分析，并输出结构化文字报告与可视化图表。

**核心价值：**
- 自动化识别 61 种经典 TA-Lib K 线形态
- 结合均线、MACD、KDJ、RSI、BOLL 等常用技术指标
- 生成专业的技术分析报告，辅助投研决策

### 1.2 文件结构

```
skill_ta_pattern/
├── SKILL.md                 # Skill 元数据与使用说明
└── analyze_ai_index.py      # AI 指数技术分析脚本（示例实现）
```

---

## 二、技术架构

### 2.1 技术栈

| 组件 | 说明 |
|------|------|
| **TA-Lib** | 核心形态识别引擎，支持 61 种 K 线形态函数 |
| **AKShare** | 首选数据源（国债期货、股票指数、个股） |
| **Matplotlib** | 可视化图表生成 |
| **NumPy/Pandas** | 数据处理 |

### 2.2 数据源优先级

```
1. akshare（首选）
2. tushare
3. 腾讯财经 API
4. 新浪财经 API
5. baostock
```

### 2.3 数据接口

```python
# 国债期货数据（10年期主力连续）
df = ak.futures_zh_daily_sina(symbol="T0")

# 上证综指
df = ak.stock_zh_index_daily(symbol="sh000001")

# 个股日K线
df = ak.stock_zh_a_hist(symbol="000001", period="daily", adjust="qfq")
```

---

## 三、核心功能

### 3.1 TA-Lib 61 种 K 线形态

| 类别 | 形态列表 |
|------|----------|
| **单 K 线** | 十字星(CDLDOJI)、锤子线(CDLHAMMER)、倒锤线(CDLINVERTEDHAMMER)、射击之星(CDLSHOOTINGSTAR)、上吊线(CDLHANGINGMAN)、纺锤线(CDLSPINNINGTOP)、墓碑十字(CDLGRAVESTONEDOJI)、蜻蜓十字(CDLDRAGONFLYDOJI)、光头光脚(CDLMARUBOZU)、长脚十字(CDLLONGLEGGEDDOJI) 等 |
| **双 K 线** | 吞没形态(CDLENGULFING)、乌云盖顶(CDLDARKCLOUDCOVER)、刺透形态(CDLPIERCING)、孕线(CDLHARAMI)、十字孕线(CDLHARAMICROSS)、捉腰带线(CDLBELTHOLD) 等 |
| **三 K 线** | 早晨之星(CDLMORNINGSTAR)、黄昏之星(CDLEVENINGSTAR)、三只乌鸦(CDL3BLACKCROWS)、三白兵(CDL3WHITESOLDIERS)、早晨十字星(CDLMORNINGDOJISTAR)、黄昏十字星(CDLEVENINGDOJISTAR)、三内部形态(CDL3INSIDE)、三外部形态(CDL3OUTSIDE) 等 |
| **多 K 线** | 弃婴形态(CDLABANDONEDBABY)、上升/下降三法(CDLRISEFALL3METHODS)、脱离形态(CDLBREAKAWAY)、藏婴形态(CDLCONCEALBABYSWALL) 等 |

### 3.2 技术指标集成

| 指标 | 说明 |
|------|------|
| **均线系统** | MA5、MA10、MA20、MA60，多头/空头排列判断 |
| **MACD** | 快线(12)、慢线(26)、Signal(9)，金叉/死叉判断 |
| **KDJ** | 随机指标，超买/超卖判断 |
| **RSI** | 相对强弱指标，RSI6/RSI12 |
| **BOLL** | 布林带，中轨/上下轨突破判断 |
| **ATR** | 平均真实波幅，风险/止损参考 |

### 3.3 信号返回值约定

```python
# TA-Lib 形态函数返回值
100   → 看涨形态 (Bullish)
-100  → 看跌形态 (Bearish)
0     → 未识别到形态

# 信号强度评估
abs(signal) >= 100 → High
abs(signal) < 100  → Medium
```

---

## 四、使用方式

### 4.1 三种调用模式

| 模式 | 用户表达 | 默认行为 |
|------|----------|----------|
| **默认分析** | "帮我做技术形态分析" | 分析国债期货(T主力) + 上证指数 |
| **指定标的** | "分析下贵州茅台的形态" | 分析指定个股 |
| **批量扫描** | "帮我扫描这50只票的形态" | 批量分析股票池 |

### 4.2 分析流程

```
1. 数据获取
   ├─ 标的识别 → 数据接口选择
   ├─ 获取最近 60-120 个交易日数据
   └─ 数据清洗和格式化

2. 形态识别
   ├─ 调用 TA-Lib 61 种形态函数
   ├─ 记录形态类型、出现位置、信号方向
   └─ 标注近 30 个交易日内的信号

3. 指标计算
   ├─ 均线系统 (MA5/10/20/60)
   ├─ MACD / KDJ / RSI / BOLL / ATR
   └─ 趋势评分计算

4. 报告生成
   ├─ 文字报告 (Markdown 格式)
   ├─ 可视化图表 (PNG)
   └─ 操作建议输出
```

---

## 五、输出格式

### 5.1 文字报告结构

```markdown
# [标的名称] 技术形态分析报告

## 1. 价格快照
   - 最新收盘价、涨跌幅、成交量
   - 均线位置、多空排列判断

## 2. 核心技术指标
   - MACD / KDJ / RSI / BOLL / ATR 状态

## 3. TA-Lib 形态识别结果
   - 近 30 日形态列表（带方向/强度）
   - 历史形态统计

## 4. 综合技术评估
   - 趋势评分 (Trend Score: ±5)
   - 各项指标多空判断

## 5. 操作建议
   - 根据趋势评分生成买卖建议
   - 止损位参考 (2x ATR)

## 6. 风险提示
   - 技术分析局限性说明
```

### 5.2 可视化图表

```
┌────────────────────────────────────────────────────┐
│  K线图 + 均线系统 + BOLL + 形态标注                │
├────────────────────────────────────────────────────┤
│  MACD 指标面板                                    │
├────────────────────────────────────────────────────┤
│  KDJ 指标面板                                      │
├────────────────────────────────────────────────────┤
│  RSI 指标面板                                      │
└────────────────────────────────────────────────────┘
```

**图表特征：**
- 🟢 上箭头 = 看涨形态信号
- 🔴 下箭头 = 看跌形态信号
- 自动标注形态名称

---

## 六、趋势评分系统

### 6.1 评分因子

| # | 因子 | 看多(+1) | 看空(-1) |
|---|------|----------|----------|
| 1 | 价格 vs MA5 | Price > MA5 | Price < MA5 |
| 2 | 价格 vs MA10 | Price > MA10 | Price < MA10 |
| 3 | 价格 vs MA60 | Price > MA60 | Price < MA60 |
| 4 | MACD | MACD > Signal | MACD < Signal |
| 5 | RSI | RSI6 > 50 | RSI6 < 50 |

### 6.2 评分解读

| 评分区间 | 趋势判断 | 操作建议 |
|----------|----------|----------|
| ≥ +3 | 强势看多 | 积极做多，回调买入 |
| +1 ~ +2 | 震荡偏多 | 谨慎做多，等待确认 |
| -1 ~ 0 | 中性震荡 | 观望为主 |
| -2 ~ -1 | 震荡偏空 | 减仓防守 |
| ≤ -3 | 弱势看空 | 离场或做空 |

---

## 七、示例代码：analyze_ai_index.py

这是针对**深证 AI 产业指数(sz399639)**的示例实现：

```python
# 1. 数据获取
INDEX_CODE = 'sz399639'  # 深证AI产业指数
df = ak.stock_zh_index_daily(symbol=INDEX_CODE)
df = df.tail(120).reset_index(drop=True)  # 最近120个交易日

# 2. TA-Lib 形态识别
for name, func in pattern_funcs.items():
    result = func(open_p, high_p, low_p, close_p)
    idxs = np.where(result != 0)[0]
    for idx in idxs:
        signal = int(result[idx])  # 100/-100/0
        # 记录形态名称、日期、方向

# 3. 技术指标计算
ma5  = talib.SMA(close_p, timeperiod=5)
macd, sig, hist = talib.MACD(close_p)
rsi6  = talib.RSI(close_p, timeperiod=6)
upper, middle, lower = talib.BBANDS(close_p, timeperiod=20)

# 4. 生成图表
# Panel 1: K线 + 均线 + BOLL
# Panel 2: MACD
# Panel 3: KDJ
# Panel 4: RSI

# 5. 输出报告
report_path = f'AI_Index_sz399639_TA_Report_{TODAY}.md'
chart_path = f'AI_Index_sz399639_TA_{TODAY}.png'
```

---

## 八、文件输出规范

| 类型 | 路径 | 命名格式 |
|------|------|----------|
| 报告 | `./输出/技术形态分析/` | `[标的名称]_形态分析_[日期].md` |
| 图表 | `./输出/技术形态分析/` | `[标的名称]_形态分析图_[日期].png` |

---

## 九、注意事项

1. **数据时效性**：使用最近交易日收盘数据，T+0 收盘后更新
2. **形态有效性**：单一形态信号仅供参考，需结合其他指标综合判断
3. **信号强度**：基于形态出现位置、成交量配合等因素评估
4. **风险提示**：技术分析不能保证投资收益，仅供参考

---

## 十、扩展方向（待开发）

- [ ] **图表形态识别**：头肩顶/底、双顶/双底、三重顶/底、圆弧顶/底
- [ ] **中继形态识别**：三角形、旗形、楔形、矩形整理
- [ ] **批量扫描功能**：支持股票池批量形态扫描
- [ ] **飞书推送集成**：自动化推送日报到飞书群

---

## 附录：常用形态速查表

| 中文名称 | 英文名称 | 函数名 | 信号类型 |
|----------|----------|--------|----------|
| 锤子线 | Hammer | CDLHAMMER | 看涨反转 |
| 吞没形态 | Engulfing | CDLENGULFING | 看涨/看跌 |
| 早晨之星 | Morning Star | CDLMORNINGSTAR | 看涨反转 |
| 黄昏之星 | Evening Star | CDLEVENINGSTAR | 看跌反转 |
| 十字星 | Doji | CDLDOJI | 中性/反转 |
| 三只乌鸦 | Three Black Crows | CDL3BLACKCROWS | 看跌延续 |
| 三白兵 | Three White Soldiers | CDL3WHITESOLDIERS | 看涨延续 |
| 乌云盖顶 | Dark Cloud Cover | CDLDARKCLOUDCOVER | 看跌反转 |
| 刺透形态 | Piercing Pattern | CDLPIERCING | 看涨反转 |
| 孕线 | Harami | CDLHARAMI | 看涨/看跌 |

---

*文档生成时间：2026-04-14*
