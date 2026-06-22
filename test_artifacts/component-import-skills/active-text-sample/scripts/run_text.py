# encoding:utf-8
import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "result.txt").write_text(f"Text sample result: {args.input}", encoding="utf-8")


if __name__ == "__main__":
    main()
