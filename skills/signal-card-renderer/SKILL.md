---
name: signal-card-renderer
description: >
  技术分析、利率择时、可转债多因子信号卡片渲染工具。
  当用户提供原始信号文本，并希望生成稳定样式的 PNG 图片时使用此 skill。
  支持三类卡片：技术分析、利率交易性择时、可转债多因子择券跟踪。
  自动完成文本类型识别、字段解析、HTML 模板填充和 Playwright 高清截图。
---

# Signal Card Renderer

将固定格式的投研信号文本渲染为稳定样式的 PNG 卡片。

## 重要提醒：稳定生成的环境要素

如果将来不在当前机器运行，必须在新环境中尽量固定以下要素。否则同一 HTML 在不同系统、浏览器或字体环境下，可能出现轻微的换行、字重、抗锯齿、图片高度差异。

### 必须固定

1. **Python 版本与依赖**
   - 推荐 Python 3.10+。
   - 必须安装 `playwright`。
   - 建议固定版本，例如写入 `requirements.txt`：

```txt
playwright==<已验证版本>
```

检查命令：

```bash
python --version
python -m pip show playwright
```

2. **Playwright Chromium 版本**
   - Playwright 截图依赖 Chromium。
   - 不同 Chromium 版本可能导致字体渲染和 PNG 字节不同。
   - 部署后执行：

```bash
python -m playwright install chromium
```

3. **中文字体**
   - 模板字体栈：

```css
"Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", Arial, sans-serif
```

   - Windows 推荐安装并使用 `Microsoft YaHei`。
   - Linux 推荐安装 `Noto Sans CJK SC` 或等价 CJK 字体。
   - 字体不同会直接影响换行、高度和字重。

4. **模板与脚本版本**
   - 以下文件必须随发布版本一起锁定：

```text
assets/template_ta.html
assets/template_bond.html
assets/template_cb.html
scripts/render_card.py
scripts/screenshot_card.py
```

5. **输入文本结构**
   - 文本内容可以变化，但字段名、段落标题和 bullet 符号应保持稳定。
   - 推荐使用 UTF-8 文本文件输入，避免命令行管道编码损坏中文。

### 推荐部署方式

为了跨环境稳定，优先使用容器或固定运行目录：

- 固定 Python 镜像/解释器版本
- 固定 `playwright` 版本
- 固定 Chromium 安装版本
- 安装固定中文字体
- 随代码发布模板文件
- 每次上线后用 `examples/` 里的样例文本做一次重复渲染哈希检查

重复渲染检查方式：

```bash
python scripts/render_card.py --input examples/ta_sample.txt --output /tmp/a.png
python scripts/render_card.py --input examples/ta_sample.txt --output /tmp/b.png
sha256sum /tmp/a.png /tmp/b.png
```

两个哈希一致，说明当前环境下同输入可字节级稳定输出。

## 用法

推荐从 UTF-8 文本文件生成 PNG：

```bash
python scripts/render_card.py --input examples/ta_sample.txt --output card_ta.png
python scripts/render_card.py --input examples/bond_sample.txt --output card_bond.png
python scripts/render_card.py --input examples/cb_sample.txt --output card_cb.png
```

也可以只对已经生成好的 HTML 截图：

```bash
python scripts/screenshot_card.py <html_path> <output_png_path>
```

## 工作流程

```text
原始文本
→ 识别卡片类型
→ 规则解析字段
→ 填充固定 HTML 模板
→ Playwright Chromium 截图
→ 输出 PNG
```

## 卡片类型识别

| 类型 | 识别关键词 | 模板 |
|---|---|---|
| 技术分析 | `趋势研判` + `核心关键位` + `实操指引` | `assets/template_ta.html` |
| 利率择时 | `当日核心信号` + `周度全景复盘` + `复合策略信号` | `assets/template_bond.html` |
| 可转债多因子 | `市场与风格表现` + `行业结构` + `错定价跟踪` | `assets/template_cb.html` |

## 输出规范

- 输出格式：PNG
- 截图比例：`device_scale_factor=3`
- 卡片 CSS 宽度：`520px`
- Playwright viewport：`600px × 1000px`
- 默认输出文件名：`card_<标的或类型>_<YYYYMMDD>.png`
- 临时 HTML：默认写入 `signal-card-renderer/.rendered/`，如未指定 `--keep-html` 会自动清理

## 输入格式要求

### 技术分析

必须包含：

```text
标的：
信号方向：
最新收盘：
行情日期：
趋势研判
核心关键位
实操指引
授权剩余时间：
数据来源：
业务对接：
```

### 利率择时

必须包含：

```text
标的：
最新收盘：
行情日期：
分析模型：
当日核心信号
复合策略信号：
多头：...；空头：...
日度主线：
周度全景复盘
近一周整体信号：
周度主线：
授权剩余时间：
业务对接：
```

`数据来源` 可缺省，缺省时显示 `——`。

### 可转债多因子

必须包含：

```text
跟踪日期：
分析模型：
跟踪维度：
市场与风格表现
行业结构
错定价跟踪
实操指引
授权剩余时间：
数据来源：
业务对接：
```

## 配色规则

- A 股/多头语义：红色 `#E24B4A`
- 下跌/空头/压力/高偏离风险：绿色 `#3B6D11`
- 中性说明：灰色
- 可转债分析块：蓝色摘要、橙色判断块、灰色标签

## 交付前检查

生成图片后建议至少检查：

1. PNG 是否存在且大小非 0。
2. 生成 HTML 中是否仍有 `{{...}}` 占位符。
3. 是否出现明显乱码，例如 `锛`、`鈥`、`馃`。
4. 同一输入重复渲染两次，哈希是否一致。

PowerShell 示例：

```powershell
Get-FileHash .\card.png -Algorithm SHA256
Select-String -Path .\.rendered\card_export_xxx.html -Pattern "{{|锛|鈥|馃"
```
