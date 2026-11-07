"""Optional offline, script-disabled DOM capture of already fetched HTML."""
from __future__ import annotations

import subprocess
import os
import signal
import sys
from dataclasses import replace

from mira.fetch import FetchedPage

_SCRIPT = '''
import sys, os
from playwright.sync_api import sync_playwright
body = sys.stdin.buffer.read().decode("utf-8", errors="replace")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=os.environ.get("MIRA_BROWSER_EXECUTABLE"))
    context = browser.new_context(offline=True, java_script_enabled=False, service_workers="block")
    context.route("**/*", lambda route: route.abort())
    page = context.new_page()
    page.set_content(body, wait_until="domcontentloaded", timeout=5000)
    sys.stdout.buffer.write(page.content().encode("utf-8"))
    context.close()
    browser.close()
'''


def _render(body: bytes, timeout: float) -> bytes:
    process = subprocess.Popen([sys.executable, "-c", _SCRIPT], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, _ = process.communicate(input=body, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise
    if process.returncode != 0:
        raise RuntimeError("offline browser failed")
    if len(stdout) > 2_000_000:
        raise ValueError("browser capture exceeds limit")
    return stdout


class OfflineBrowserCapture:
    def __init__(self, *, renderer=_render, timeout: float = 8) -> None:
        if not 0 < timeout <= 10:
            raise ValueError("browser timeout exceeds limit")
        self.renderer, self.timeout = renderer, timeout

    def with_timeout(self, remaining: float) -> "OfflineBrowserCapture":
        return OfflineBrowserCapture(renderer=self.renderer, timeout=min(self.timeout, remaining))

    def capture(self, page: FetchedPage) -> FetchedPage | None:
        if page.kind != "html" or page.source.connector_config.get("allow_browser") is not True:
            return None
        if len(page.body) > 1_000_000:
            return None
        body = self.renderer(page.body, self.timeout)
        if not isinstance(body, bytes) or len(body) > 2_000_000:
            raise ValueError("invalid browser capture")
        return replace(page, body=body)
