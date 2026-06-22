# encoding:utf-8
import argparse
import struct
import zlib
from pathlib import Path


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


def build_ta_chart_png(width: int = 640, height: int = 360) -> bytes:
    points = [284, 270, 292, 252, 238, 218, 230, 198, 178, 188, 154, 132]
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            rgb = (248, 250, 252)
            if x < 56 or y > height - 48:
                rgb = (226, 232, 240)
            if x in (56, width - 32) or y in (32, height - 48):
                rgb = (71, 85, 105)
            for index, py in enumerate(points):
                px = 82 + index * 46
                if abs(x - px) <= 5 and abs(y - py) <= 5:
                    rgb = (220, 38, 38)
                if index > 0:
                    prev_x = 82 + (index - 1) * 46
                    prev_y = points[index - 1]
                    if prev_x <= x <= px:
                        expected_y = prev_y + (py - prev_y) * (x - prev_x) / (px - prev_x)
                        if abs(y - expected_y) <= 2:
                            rgb = (37, 99, 235)
            row.extend(rgb)
        rows.append(bytes(row))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + png_chunk(b"IEND", b"")
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
    chart.write_bytes(build_ta_chart_png())


if __name__ == "__main__":
    main()
