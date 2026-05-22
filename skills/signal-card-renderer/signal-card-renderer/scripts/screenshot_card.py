#!/usr/bin/env python3
"""
signal-card-screenshot: 将卡片 HTML 截图输出为高清 PNG

用法:
  python screenshot_card.py <html_path> <output_png_path>

依赖: playwright (pip install playwright && python -m playwright install chromium)
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def bundled_node() -> tuple[str | None, str | None]:
    candidates = [
        str(Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"),
        str(Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node"),
        shutil.which("node"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            node_path = Path(candidate)
            node_modules = node_path.parents[1] / "node_modules"
            if node_modules.joinpath("playwright").exists():
                return str(node_path), str(node_modules)
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            node_path = Path(candidate)
            node_modules = node_path.parents[1] / "node_modules"
            return str(node_path), str(node_modules) if node_modules.exists() else None
    return None, None


def screenshot_with_node(file_url: str, out_path: Path) -> None:
    node, node_modules = bundled_node()
    if not node:
        raise RuntimeError("未找到 Node.js，且 Python Playwright 不可用。")

    script = """
const { chromium } = require('playwright');
const [fileUrl, outPath] = process.argv.slice(1);
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: 600, height: 1000 },
    deviceScaleFactor: 3
  });
  await page.goto(fileUrl, { waitUntil: 'load' });
  await page.waitForFunction(() => document.fonts ? document.fonts.status === 'loaded' : true);
  const card = page.locator('.card');
  await card.waitFor({ state: 'visible' });
  await card.screenshot({ path: outPath, animations: 'disabled' });
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
"""
    env = os.environ.copy()
    if node_modules:
        env["NODE_PATH"] = node_modules
    subprocess.run([node, "-e", script, file_url, str(out_path)], check=True, env=env)


def main():
    if len(sys.argv) < 3:
        print("用法: python screenshot_card.py <html_path> <output_png_path>")
        sys.exit(1)

    html_path = Path(sys.argv[1]).resolve()
    out_path = Path(sys.argv[2]).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    file_url = html_path.as_uri()

    print(f"[signal-card] 截图 HTML: {html_path}")
    print(f"[signal-card] 输出 PNG: {out_path}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[signal-card] Python Playwright 不可用，切换到 Node Playwright")
        screenshot_with_node(file_url, out_path)
    else:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": 600, "height": 1000},
                device_scale_factor=3,
            )
            page.goto(file_url, wait_until="load")
            page.wait_for_function("document.fonts ? document.fonts.status === 'loaded' : true")
            card = page.locator(".card")
            card.wait_for(state="visible")
            card.screenshot(path=str(out_path), animations="disabled")
            browser.close()

    size_kb = os.path.getsize(out_path) / 1024
    print(f"[signal-card] 完成：{out_path} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
