#!/usr/bin/env python3
"""
Deterministic renderer for signal-card-renderer.

Usage:
  python scripts/render_card.py --input input.txt
  python scripts/render_card.py --text "..." --output card.png
"""
from __future__ import annotations

import argparse
import hashlib
import html
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
WORK_DIR = ROOT / ".rendered"


def normalize_text(raw: str) -> str:
    text = raw.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in text.split("\n"):
        cleaned = line.strip()
        if not cleaned:
            lines.append("")
            continue
        if set(cleaned) <= {"-", "—", "─", "_", " "}:
            lines.append("")
            continue
        lines.append(cleaned)
    return "\n".join(lines).strip()


def detect_card_type(text: str) -> str:
    if all(keyword in text for keyword in ("市场与风格表现", "行业结构", "错定价跟踪")):
        return "cb"
    if all(keyword in text for keyword in ("当日核心信号", "周度全景复盘", "复合策略信号")):
        return "bond"
    if all(keyword in text for keyword in ("趋势研判", "核心关键位", "实操指引")):
        return "ta"
    raise ValueError("无法识别卡片类型：请提供技术分析、利率择时或可转债多因子格式文本。")


def line_value(text: str, label: str, default: str = "") -> str:
    pattern = re.compile(rf"(?:^|\n).*?{re.escape(label)}\s*[:：]\s*([^\n]+)")
    match = pattern.search(text)
    return match.group(1).strip() if match else default


def extract_section(text: str, heading: str, stop_headings: tuple[str, ...]) -> list[str]:
    lines = text.split("\n")
    start = None
    for index, line in enumerate(lines):
        if heading in line:
            start = index + 1
            break
    if start is None:
        return []
    collected = []
    for line in lines[start:]:
        stripped = line.strip()
        if any(stop in stripped for stop in stop_headings):
            break
        if stripped:
            collected.append(stripped)
    return collected


def split_level(value: str) -> tuple[str, str]:
    value = value.strip()
    match = re.match(r"(.+?)\s*[（(]\s*(.+?)\s*[）)]\s*$", value)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return value, ""


def signal_style(signal: str) -> tuple[str, str, str]:
    bull_words = ("买入", "入场", "看涨", "支撑", "低估修复", "持续入场", "做多")
    bear_words = ("卖出", "看跌", "压力", "高估偏离", "规避", "出场", "做空")
    if any(word in signal for word in bull_words):
        return "#E24B4A", "#FCEBEB", "2,9 5,2 8,9"
    if any(word in signal for word in bear_words):
        return "#3B6D11", "#EAF3DE", "2,2 5,9 8,2"
    return "#888888", "#F5F5F0", "5,5 5,5 5,5"


def ops_style(ops: str) -> tuple[str, str]:
    if any(word in ops for word in ("买入", "入场", "做多")):
        return "#FCEBEB", "#E24B4A"
    if any(word in ops for word in ("卖出", "减仓", "规避", "离场")):
        return "#EAF3DE", "#3B6D11"
    return "#F5F5F0", "#555555"


def escape_text(value: str) -> str:
    return html.escape(value, quote=True)


def escape_block(value: str) -> str:
    return "<br>".join(escape_text(part) for part in value.split("\n"))


def render_trend_items(lines: list[str]) -> str:
    dot_colors = ("#E24B4A", "#EF9F27", "#3B6D11", "#E24B4A", "#1F6FB8", "#7F77DD")
    chunks = []
    for index, line in enumerate(lines):
        item = re.sub(r"^[▪▫•·\-\s️]+", "", line).strip()
        if not item:
            continue
        if "：" in item:
            label, body = item.split("：", 1)
        elif ":" in item:
            label, body = item.split(":", 1)
        else:
            label, body = "", item
        tag = ""
        label_text = label
        label_match = re.match(r"(.+?)\s*[（(](.+?)[）)]\s*$", label)
        if label_match:
            label_text = label_match.group(1).strip()
            tag = label_match.group(2).strip()
        label_html = f'<span class="trend-label">{escape_text(label_text)}</span>' if label_text else ""
        tag_html = f'<span class="trend-tag">{escape_text(tag)}</span>' if tag else ""
        dot_color = dot_colors[index % len(dot_colors)]
        chunks.append(
            f'<div class="trend-item" style="--dot-color:{dot_color}">'
            '<div class="trend-dot"></div>'
            f'<div class="trend-head">{label_html}{tag_html}</div>'
            f'<div class="trend-text">{escape_text(body.strip())}</div>'
            "</div>"
        )
    return "\n  ".join(chunks)


def render_plain_bullets(lines: list[str]) -> str:
    dot_colors = ("#E24B4A", "#1F6FB8", "#3B6D11", "#EF9F27", "#7F77DD")
    chunks = []
    for index, line in enumerate(lines):
        item = re.sub(r"^[▪▫•·\-\s️]+", "", line).strip()
        if not item:
            continue
        chunks.append(
            f'<div class="bullet" style="--dot-color:{dot_colors[index % len(dot_colors)]}">'
            '<div class="bullet-dot"></div>'
            f'<div class="bullet-text">{escape_text(item)}</div>'
            "</div>"
        )
    return "\n  ".join(chunks)


def render_cb_items(lines: list[str], verdict_labels: tuple[str, ...]) -> str:
    dot_colors = ("#378ADD", "#EF9F27", "#7F77DD")
    chunks = []
    bullet_index = 0
    for line in lines:
        item = re.sub(r"^[▪▫•·\-\s️]+", "", line).strip()
        if not item:
            continue
        label = ""
        body = item
        if "：" in item:
            label, body = item.split("：", 1)
        elif ":" in item:
            label, body = item.split(":", 1)
        label = label.strip()
        body = body.strip()
        if label in verdict_labels:
            chunks.append(f'<div class="block-verdict">{escape_text(label)}：{escape_text(body)}</div>')
            continue
        color = dot_colors[bullet_index % len(dot_colors)]
        bullet_index += 1
        if label:
            text = f"<strong>{escape_text(label)}：</strong>{escape_text(body)}"
        else:
            text = escape_text(body)
        chunks.append(
            f'<div class="block-bullet" style="--dot-color:{color}">'
            '<div class="block-dot"></div>'
            f'<div class="block-text">{text}</div>'
            "</div>"
        )
    return "\n    ".join(chunks)


def render_tags(raw: str) -> str:
    parts = [part.strip() for part in re.split(r"[/／,，、]", raw) if part.strip()]
    return "".join(f'<span class="tag">{escape_text(part)}</span>' for part in parts)


def extract_bonds(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    if not match:
        return ""
    return "、".join(part.strip() for part in re.split(r"[、,，]", match.group(1)) if part.strip())


def parse_ta(text: str) -> dict[str, str]:
    brand_match = re.search(r"【(.+?)】", text)
    brand = brand_match.group(1).strip() if brand_match else "浙商固收 | 智能投研辅助系统"

    ticker_raw = line_value(text, "标的")
    ticker_match = re.match(r"(.+?)\s*[（(]\s*(.+?)\s*[）)]", ticker_raw)
    ticker_name = ticker_match.group(1).strip() if ticker_match else ticker_raw.strip()
    ticker_code = ticker_match.group(2).strip() if ticker_match else ""

    model = line_value(text, "分析模型")
    signal = line_value(text, "信号方向")
    price = re.sub(r"\s*元\s*$", "", line_value(text, "最新收盘")).strip()

    market_line = line_value(text, "行情日期")
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", market_line)
    change_match = re.search(r"日内(涨幅|跌幅)\s*[:：]\s*([+-]?\d+(?:\.\d+)?%)", market_line)
    date = date_match.group(1) if date_match else ""
    change = f"日内{change_match.group(1)}：{change_match.group(2)}" if change_match else ""
    change_class = "negative" if "涨幅" in market_line else "positive" if "跌幅" in market_line else ""

    trend_lines = extract_section(text, "趋势研判", ("核心关键位", "实操指引", "本内容仅供研究参考"))
    trend_summary = ""
    trend_items = []
    for line in trend_lines:
        if re.match(r"^[▪▫•·\-]", line):
            trend_items.append(line)
        elif not trend_summary:
            trend_summary = line
        else:
            trend_summary = f"{trend_summary}\n{line}"

    level_lines = extract_section(text, "核心关键位", ("实操指引", "本内容仅供研究参考"))
    resist_level, resist_desc = "", ""
    support_level, support_desc = "", ""
    for line in level_lines:
        item = re.sub(r"^[▪▫•·\-\s️]+", "", line).strip()
        if item.startswith("强压力"):
            resist_level, resist_desc = split_level(re.sub(r"^强压力\s*[:：]\s*", "", item))
        if item.startswith("强支撑"):
            support_level, support_desc = split_level(re.sub(r"^强支撑\s*[:：]\s*", "", item))

    ops_lines = extract_section(text, "实操指引", ("本内容仅供研究参考", "授权剩余时间", "数据来源", "业务对接"))
    ops = "\n".join(ops_lines).strip()

    data_source = line_value(text, "数据来源")
    contact = line_value(text, "业务对接")

    signal_color, signal_bg, arrow_points = signal_style(signal)
    ops_bg, ops_color = ops_style(ops)

    return {
        "BRAND": escape_text(brand),
        "SIGNAL": escape_text(signal),
        "SIGNAL_COLOR": signal_color,
        "SIGNAL_BG": signal_bg,
        "ARROW_POINTS": arrow_points,
        "TICKER_NAME": escape_text(ticker_name),
        "TICKER_CODE": escape_text(ticker_code),
        "PRICE": escape_text(price),
        "DATE": escape_text(date),
        "CHANGE": escape_text(change),
        "CHANGE_CLASS": change_class,
        "TREND_SUMMARY": escape_block(trend_summary),
        "TREND_ITEMS": render_trend_items(trend_items),
        "RESIST_LEVEL": escape_text(resist_level),
        "RESIST_DESC": escape_text(resist_desc),
        "SUPPORT_LEVEL": escape_text(support_level),
        "SUPPORT_DESC": escape_text(support_desc),
        "OPS_GUIDE": escape_block(ops),
        "OPS_BG": ops_bg,
        "OPS_COLOR": ops_color,
        "DATA_SOURCE": escape_text(data_source),
        "AUTH": "",
        "CONTACT": escape_text(contact),
    }


def parse_bond(text: str) -> dict[str, str]:
    brand_match = re.search(r"【(.+?)】", text)
    brand = brand_match.group(1).strip() if brand_match else "浙商固收 | 智能投研辅助系统"

    ticker_name = line_value(text, "标的")
    model = line_value(text, "分析模型")
    price = re.sub(r"\s*元\s*$", "", line_value(text, "最新收盘")).strip()
    market_line = line_value(text, "行情日期")
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", market_line)
    date = date_match.group(1) if date_match else ""

    daily_lines = extract_section(text, "当日核心信号", ("周度全景复盘", "本内容仅供研究参考"))
    compound_signal = ""
    bull_signals = ""
    bear_signals = ""
    daily_items = []
    daily_theme = ""
    for line in daily_lines:
        if line.startswith("复合策略信号"):
            compound_signal = re.sub(r"^复合策略信号\s*[:：]\s*", "", line).strip()
        elif line.startswith("多头"):
            match = re.search(r"多头\s*[:：]\s*(.*?)(?:；|;)\s*空头\s*[:：]\s*(.*)$", line)
            if match:
                bull_signals = match.group(1).strip()
                bear_signals = match.group(2).strip()
            else:
                bull_signals = re.sub(r"^多头\s*[:：]\s*", "", line).strip()
        elif line.startswith("💡") or "日度主线" in line:
            daily_theme = re.sub(r"^💡\s*", "", line)
            daily_theme = re.sub(r"^日度主线\s*[:：]\s*", "日度主线：", daily_theme).strip()
        elif re.match(r"^[▪▫•·\-]", line):
            daily_items.append(line)

    weekly_lines = extract_section(text, "周度全景复盘", ("本内容仅供研究参考", "授权剩余时间", "数据来源", "业务对接"))
    weekly_signal = ""
    weekly_items = []
    weekly_theme = ""
    for line in weekly_lines:
        if line.startswith("近一周整体信号"):
            weekly_signal = re.sub(r"^近一周整体信号\s*[:：]\s*", "近一周整体信号：", line).strip()
        elif line.startswith("💡") or "周度主线" in line:
            weekly_theme = re.sub(r"^💡\s*", "", line)
            weekly_theme = re.sub(r"^周度主线\s*[:：]\s*", "周度主线：", weekly_theme).strip()
        elif re.match(r"^[▪▫•·\-]", line):
            weekly_items.append(line)

    signal_keyword = compound_signal.split("（", 1)[0].split("(", 1)[0].strip()
    signal_color, signal_bg, arrow_points = signal_style(signal_keyword)

    return {
        "BRAND": escape_text(brand),
        "SIGNAL": escape_text(compound_signal or signal_keyword),
        "SIGNAL_COLOR": signal_color,
        "SIGNAL_BG": signal_bg,
        "ARROW_POINTS": arrow_points,
        "TICKER_NAME": escape_text(ticker_name),
        "MODEL_NAME": escape_text(model),
        "PRICE": escape_text(price),
        "DATE": escape_text(date),
        "COMPOUND_SIGNAL": escape_text(f"复合策略信号：{compound_signal}" if compound_signal else ""),
        "BULL_SIGNALS": escape_text(bull_signals),
        "BEAR_SIGNALS": escape_text(bear_signals),
        "DAILY_ITEMS": render_plain_bullets(daily_items),
        "DAILY_THEME": escape_text(daily_theme),
        "WEEKLY_SIGNAL": escape_text(weekly_signal),
        "WEEKLY_ITEMS": render_plain_bullets(weekly_items),
        "WEEKLY_THEME": escape_text(weekly_theme),
        "AUTH": "",
        "DATA_SOURCE": escape_text(line_value(text, "数据来源") or "——"),
        "CONTACT": escape_text(line_value(text, "业务对接")),
    }


def parse_cb(text: str) -> dict[str, str]:
    brand_match = re.search(r"【(.+?)】", text)
    brand = brand_match.group(1).strip() if brand_match else "浙商固收 | 智能投研辅助系统"
    date = line_value(text, "跟踪日期")
    factors = line_value(text, "跟踪维度")

    market_lines = extract_section(text, "市场与风格表现", ("行业结构", "错定价跟踪", "实操指引"))
    industry_lines = extract_section(text, "行业结构", ("错定价跟踪", "实操指引"))
    misprice_lines = extract_section(text, "错定价跟踪", ("实操指引", "本内容仅供研究参考"))
    ops_lines = extract_section(text, "实操指引", ("本内容仅供研究参考", "授权剩余时间", "数据来源", "业务对接"))

    def split_summary_items(lines: list[str]) -> tuple[str, list[str]]:
        summary = ""
        items = []
        for line in lines:
            if re.match(r"^[▪▫•·\-]", line):
                items.append(line)
            elif not summary:
                summary = line
            else:
                summary = f"{summary}\n{line}"
        return summary, items

    market_summary, market_items = split_summary_items(market_lines)
    industry_summary, industry_items = split_summary_items(industry_lines)
    misprice_summary, misprice_items_all = split_summary_items(misprice_lines)

    focus_lines = []
    misprice_items = []
    for line in misprice_items_all:
        normalized = re.sub(r"^[▪▫•·\-\s️]+", "", line).strip()
        if normalized.startswith("跟踪重点"):
            focus_lines.append(line)
        else:
            misprice_items.append(line)

    misprice_text = "\n".join(misprice_lines)
    high_risk = extract_bonds(r"([一-龥A-Za-z0-9、，,]+等)处于相对高偏离区间", misprice_text)
    low_risk = extract_bonds(r"([一-龥A-Za-z0-9、，,]+等)(?:仍)?处于显著负偏离区间", misprice_text)
    if high_risk.endswith("等"):
        high_risk = high_risk[:-1]
    if low_risk.endswith("等"):
        low_risk = low_risk[:-1]

    ops = "\n".join(ops_lines).strip()

    return {
        "BRAND": escape_text(brand),
        "DATE": escape_text(date),
        "FACTOR_TAGS": render_tags(factors),
        "MARKET_SUMMARY": escape_block(market_summary),
        "MARKET_ITEMS": render_cb_items(market_items, ("整体判断",)),
        "INDUSTRY_SUMMARY": escape_block(industry_summary),
        "INDUSTRY_ITEMS": render_cb_items(industry_items, ("结构判断",)),
        "MISPRICE_SUMMARY": escape_block(misprice_summary),
        "MISPRICE_ITEMS": render_cb_items(misprice_items, ()),
        "MISPRICE_FOCUS": render_cb_items(focus_lines, ("跟踪重点",)),
        "HIGH_RISK_BONDS": escape_text(high_risk),
        "LOW_RISK_BONDS": escape_text(low_risk),
        "OPS_GUIDE": escape_block(ops),
        "DATA_SOURCE": escape_text(line_value(text, "数据来源")),
        "AUTH": "",
        "CONTACT": escape_text(line_value(text, "业务对接")),
    }


def fill_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    leftovers = sorted(set(re.findall(r"{{[A-Z0-9_]+}}", rendered)))
    if leftovers:
        raise ValueError(f"模板仍有未填充字段：{', '.join(leftovers)}")
    return rendered


def safe_filename_part(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "_", value).strip("_")
    return cleaned or "signal"


def default_output_path(values: dict[str, str], output_dir: Path) -> Path:
    name = html.unescape(values.get("TICKER_NAME", "signal"))
    date = values.get("DATE", "").replace("-", "")
    suffix = f"_{date}" if date else ""
    return output_dir / f"card_{safe_filename_part(name)}{suffix}.png"


def read_stdin_text() -> str:
    data = sys.stdin.buffer.read()
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def render(text: str, output: Path | None, html_output: Path | None, keep_html: bool) -> tuple[Path, Path]:
    normalized = normalize_text(text)
    card_type = detect_card_type(normalized)
    if card_type == "ta":
        values = parse_ta(normalized)
        template_name = "template_ta.html"
    elif card_type == "bond":
        values = parse_bond(normalized)
        template_name = "template_bond.html"
    elif card_type == "cb":
        values = parse_cb(normalized)
        template_name = "template_cb.html"
    else:
        raise ValueError(f"暂不支持的卡片类型：{card_type}")
    template = (ASSETS / template_name).read_text(encoding="utf-8")
    rendered_html = fill_template(template, values)

    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    html_path = html_output or (WORK_DIR / f"card_export_{digest}.html")
    html_path = html_path.resolve()
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(rendered_html, encoding="utf-8", newline="\n")

    output_path = (output or default_output_path(values, Path.cwd())).resolve()
    screenshot_script = ROOT / "scripts" / "screenshot_card.py"
    subprocess.run([sys.executable, str(screenshot_script), str(html_path), str(output_path)], check=True)

    if not keep_html and html_output is None:
        html_path.unlink(missing_ok=True)
    return output_path, html_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a signal card PNG from raw text.")
    parser.add_argument("--input", "-i", type=Path, help="UTF-8 text file containing the raw signal text.")
    parser.add_argument("--text", help="Raw signal text. If omitted, stdin is used.")
    parser.add_argument("--output", "-o", type=Path, help="Output PNG path. Defaults to card_<标的>_<YYYYMMDD>.png.")
    parser.add_argument("--html-output", type=Path, help="Optional HTML output path.")
    parser.add_argument("--keep-html", action="store_true", help="Keep the generated temporary HTML.")
    args = parser.parse_args()

    if args.input:
        raw = args.input.read_text(encoding="utf-8")
    elif args.text is not None:
        raw = args.text
    else:
        raw = read_stdin_text()

    output_path, html_path = render(raw, args.output, args.html_output, args.keep_html)
    print(f"[signal-card] PNG: {output_path}")
    if args.keep_html or args.html_output:
        print(f"[signal-card] HTML: {html_path}")


if __name__ == "__main__":
    main()
