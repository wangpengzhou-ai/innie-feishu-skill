#!/usr/bin/env python3
"""
innie@feishu.skill — Step 8: Export share-card HTML to PNG

This wraps the local HTTP server + Puppeteer flow into one script so the output
path, served directory, and screenshot target stay aligned.

Usage:
    python3 export_png.py
    python3 export_png.py --html share-card.html --png share-card.png
"""

import http.server
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from functools import partial
from pathlib import Path


DEFAULT_CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
]


def find_chrome(explicit: str | None) -> str:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise FileNotFoundError(f"Chrome executable not found: {explicit}")
        return str(path)

    for candidate in DEFAULT_CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError(
        "Could not find Google Chrome. Pass --chrome /path/to/chrome."
    )


def ensure_puppeteer(project_dir: Path):
    if not (project_dir / "node_modules/puppeteer").exists():
        if not shutil.which("npm"):
            raise RuntimeError("npm is required to install Puppeteer")
        subprocess.run(["npm", "init", "-y"], cwd=project_dir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["npm", "install", "puppeteer"], cwd=project_dir, check=True)


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


def start_server(directory: Path, port: int):
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadedTCPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def render_png(html_path: Path, png_path: Path, chrome_path: str, port: int):
    served_dir = html_path.parent.resolve()
    png_path = png_path.resolve()

    with tempfile.TemporaryDirectory(prefix="innie-puppeteer-") as tmp:
        tmp_dir = Path(tmp)
        ensure_puppeteer(tmp_dir)

        server, thread = start_server(served_dir, port)
        time.sleep(0.3)
        try:
            script = f"""
import puppeteer from '{(tmp_dir / 'node_modules/puppeteer/lib/esm/puppeteer/puppeteer.js').as_posix()}';
const browser = await puppeteer.launch({{
  executablePath: {chrome_path!r},
  args: ['--no-sandbox']
}});
const page = await browser.newPage();
await page.setViewport({{width: 760, height: 900, deviceScaleFactor: 2}});
await page.goto('http://127.0.0.1:{port}/{html_path.name}', {{waitUntil: 'domcontentloaded'}});
await new Promise((resolve) => setTimeout(resolve, 2500));
await page.screenshot({{path: {str(png_path)!r}, fullPage: true}});
await browser.close();
console.log('Done: {png_path.name}');
"""
            subprocess.run(
                ["node", "--input-type=module"],
                input=script,
                text=True,
                check=True,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Export share-card HTML to PNG")
    parser.add_argument("--html", default="share-card.html", help="HTML file to render")
    parser.add_argument("--png", default="share-card.png", help="Output PNG path")
    parser.add_argument("--chrome", default=None, help="Path to Chrome executable")
    parser.add_argument("--port", type=int, default=7788, help="Local port for temporary HTTP server")
    args = parser.parse_args()

    html_path = Path(args.html)
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    chrome_path = find_chrome(args.chrome)
    render_png(html_path, Path(args.png), chrome_path, args.port)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[export_png] {exc}", file=sys.stderr)
        raise
