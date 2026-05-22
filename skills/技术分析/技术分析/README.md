# 技术形态分析 Skill v0.0.8-basic

> 基础技术分析版（非高级形态）· 浙商证券固收团队

## 版本说明

**定位**：面向中国金融市场的多资产基础技术分析工具，支持国债期货、A 股指数、个股、ETF 等标的，输出 Markdown 技术分析报告和 PNG 图表。

**更新日期**：2026-05-06

v0.0.8-basic 是 v0.0.8 的精简版，移除了高级价格形态识别模块，保留并强化了 K 线形态、技术指标、信号扫描和报告生成能力。

## 核心功能

| 模块 | 说明 |
|---|---|
| K 线形态识别 | 基于 TA-Lib 识别 61 种经典 K 线形态 |
| 核心技术指标 | MA、MACD、RSI、KDJ、BOLL、ATR、量比等 |
| 扩展指标库 | ADX、CCI、MFI、OBV、AD、ADOSC、APO、PPO、ULTOSC 等 |
| 信号扫描 | 非核心指标极端分位、同类指标共振、形态与指标交叉验证 |
| 形态历史统计 | 近 3 日形态的历史胜率、盈亏比和 5 日期望统计 |
| 关键点位 | 基于均线和 BOLL 生成支撑/阻力参考 |
| 情景推演 | 根据关键点位生成条件式情景讨论 |
| 报告生成 | Markdown 报告、主图、近 3 日形态详图 |

## 基础版边界

| 功能 | v0.0.8-basic |
|---|---|
| TA-Lib K 线形态 | 有 |
| 核心和扩展技术指标 | 有 |
| 量价辅助判断 | 有 |
| 非核心指标异常扫描 | 有 |
| 形态历史胜率统计 | 有 |
| 波段结构分析 | 无 |
| W底/M顶/头肩 | 无 |
| 三角形/楔形/旗形 | 无 |
| 缺口分析 | 无 |
| 严格 RSI 背离识别 | 无 |

## 文件结构

```text
v0.0.8-basic/
├── SKILL.md
├── README.md
├── 指标综合解读框架.md
├── scripts/
│   ├── analyze_universal.py    # 主入口
│   ├── indicators_lib.py       # 指标计算库
│   ├── signal_scanner.py       # 异常与共振扫描器
│   ├── indicator_query.py      # 指标问答和对比扩展
│   └── chart_helpers.py        # 共享绘图工具
├── references/
│   └── SKILL_系统介绍.md       # 历史设计说明，部分内容可能滞后
└── assets/
    └── 图表配色规范.md
```

`output_*`、`__pycache__`、`run.log` 等为运行产物，不属于核心逻辑。

## 使用方式

```bash
# 国债期货（默认）
python scripts/analyze_universal.py -s T0

# 五年/二年国债期货
python scripts/analyze_universal.py -s TF0
python scripts/analyze_universal.py -s TS0

# 指数
python scripts/analyze_universal.py -s sh000001
python scripts/analyze_universal.py -s sh000300
python scripts/analyze_universal.py -s sz399001

# 个股
python scripts/analyze_universal.py -s 600519
```

常用参数：

| 参数 | 含义 | 默认值 |
|---|---|---|
| `-s`, `--symbol` | 标的代码 | `T0` |
| `-c`, `--config` | 预设配置名 | 无 |
| `-d`, `--days` | 图表天数 | `120` |
| `-l`, `--lookback` | 分位数回看窗口 | `756` |
| `-o`, `--output` | 输出目录 | `../技术形态分析` |
| `--no-chart` | 不生成图表 | 默认生成 |

## 输出文件

| 类型 | 命名格式 |
|---|---|
| Markdown 报告 | `{代码}_技术分析报告_{日期}.md` |
| 主图 | `{代码}_TA_{日期}.png` |
| 形态详图 | `{代码}_PATTERN_{形态代码}_{形态日期}.png` |

形态详图仅在近 3 日检测到可展示形态时生成。

## 数据源

当前代码实际实现的数据源顺序：

1. AKShare
2. Tushare，需要 `TUSHARE_TOKEN` 或 `~/.tushare_token`
3. BaoStock

腾讯财经和新浪财经 fallback 当前未在代码中实现。

## 技术栈

- Python 3.12+
- TA-Lib
- AKShare / Tushare / BaoStock
- NumPy / Pandas / SciPy
- Matplotlib

## 风险提示

技术分析仅用于辅助判断，不构成投资建议。单一形态、单一指标或历史胜率统计都不能独立作为交易依据。
