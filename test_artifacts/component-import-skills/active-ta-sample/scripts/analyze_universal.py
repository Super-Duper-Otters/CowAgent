# encoding:utf-8
import argparse
import base64
from pathlib import Path


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_symbol = args.symbol.replace("/", "_").replace("\\", "_").replace(" ", "_")

    report = output_dir / f"{safe_symbol}_技术分析报告.md"
    chart = output_dir / f"{safe_symbol}_TA_main.png"

    report.write_text(
        f"# 技术分析报告\n\n标的：{args.symbol}\n\n结论：这是导入组件测试报告。\n",
        encoding="utf-8",
    )
    chart.write_bytes(PNG_1X1)


if __name__ == "__main__":
    main()
