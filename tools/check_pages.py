"""Check the actual GitHub Pages output under its repository subpath."""
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BASE = "/" + os.environ.get("PAGES_BASE_PATH", "mira-beauty").strip("/")
if BASE == "/":
    BASE = ""
ORIGIN = "http://127.0.0.1:5067"
# Serve the repository as parent so the nested project path matches GitHub Pages.
import tempfile
import shutil
with tempfile.TemporaryDirectory() as temporary:
    public = Path(temporary) / BASE.lstrip("/") if BASE else Path(temporary)
    public.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "_site", public, dirs_exist_ok=True)
    server = subprocess.Popen([sys.executable, "-m", "http.server", "5067", "--bind", "127.0.0.1", "--directory", temporary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                urlopen(ORIGIN + BASE + "/", timeout=1).close()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError("Static test server did not start")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            errors, failures, api = [], [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("response", lambda response: failures.append(response.url) if response.status >= 400 else None)
            page.on("request", lambda request: api.append(request.url) if "/api/" in request.url else None)
            page.add_init_script("document.addEventListener('DOMContentLoaded',()=>document.querySelectorAll('img').forEach(i=>i.loading='eager'))")
            for width in (360, 390, 768, 1440):
                page.set_viewport_size({"width": width, "height": 1000})
                for route in ("", "services/", "masters/", "gallery/", "about/", "booking/", "privacy/", "login/"):
                    response = page.goto(ORIGIN + BASE + "/" + route)
                    assert response.status == 200, route
                    page.locator("img").evaluate_all("images=>Promise.all(images.map(i=>i.decode().catch(()=>null)))")
                    assert page.evaluate("Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)"), route
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), (width, route)
                    assert page.locator("form").count() == 0, route
                    assert page.locator('meta[name="csrf-token"]').count() == 0
                    assert page.locator('a[href$="/login/"]').count() == 0
                    for href in page.locator("a[href]").evaluate_all("links=>links.map(a=>a.getAttribute('href'))"):
                        if href.startswith("/"):
                            assert href.startswith(BASE + "/"), href
            page.goto(ORIGIN + BASE + "/services/")
            page.locator("#service-search").fill("стрижка")
            expect(page.locator("#catalog .service-card:visible")).to_have_count(1)
            page.locator("#service-search").fill("неизвестная процедура")
            expect(page.locator("#catalog-empty")).to_be_visible()
            page.locator("#reset-service-filters").click()
            expect(page.locator("#catalog .service-card:visible")).to_have_count(6)
            page.goto(ORIGIN + BASE + "/gallery/")
            page.locator(".gallery-open").first.click()
            expect(page.locator("#gallery-dialog")).to_be_visible()
            expect(page.locator("#gallery-dialog-image")).to_have_attribute("src", __import__("re").compile("^" + BASE + "/static/images/"))
            page.locator("#gallery-dialog-image").evaluate("(i)=>i.decode()")
            page.locator(".dialog-close").click()
            page.set_viewport_size({"width": 390, "height": 1000})
            page.goto(ORIGIN + BASE + "/")
            page.locator(".menu-toggle").click()
            page.locator("#main-nav").get_by_role("link", name="Мастера", exact=True).click()
            expect(page).to_have_url(ORIGIN + BASE + "/masters/")
            assert not api, api
            assert not failures, failures
            assert not errors, errors
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
print("GitHub Pages checks passed: images, subpath links, mobile menu, filters, gallery; no API calls.")
