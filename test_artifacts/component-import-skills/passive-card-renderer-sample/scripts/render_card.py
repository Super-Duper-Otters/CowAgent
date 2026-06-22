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


def build_signal_card_png(width: int = 480, height: int = 240) -> bytes:
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            if x < 6 or y < 6 or x >= width - 6 or y >= height - 6:
                rgb = (26, 54, 93)
            elif 28 <= x <= width - 28 and 28 <= y <= 76:
                rgb = (37, 99, 235)
            elif 48 <= x <= width - 48 and 118 <= y <= 138:
                rgb = (22, 163, 74)
            elif 48 <= x <= width - 120 and 164 <= y <= 184:
                rgb = (245, 158, 11)
            else:
                rgb = (248, 250, 252)
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
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(build_signal_card_png())


if __name__ == "__main__":
    main()
