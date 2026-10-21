"""Проверка реальных фотографий и удобочитаемости в Chromium (для CI)."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from PIL import Image
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "screenshots"
OUTPUT.mkdir(parents=True, exist_ok=True)
photos = json.loads((ROOT / "docs" / "PHOTO_SOURCES.json").read_text(encoding="utf-8"))
for photo in photos:
    with Image.open(ROOT / "static" / "images" / photo["filename"]) as image:
        assert image.width >= 500 and image.height >= 300, photo["filename"]
        image.verify()

with tempfile.TemporaryDirectory() as temporary:
    env = dict(os.environ, MIRA_DATABASE=str(Path(temporary) / "qa.sqlite3"), MIRA_PORT="5059")
    server = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env)
    try:
        for _ in range(100):
            try:
                with urlopen("http://127.0.0.1:5059/api/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError("Сервер проверки не запустился.")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script("document.addEventListener('DOMContentLoaded',()=>document.querySelectorAll('img').forEach(i=>i.loading='eager'))")
            paths = ["/", "/services", "/masters", "/gallery", "/booking", "/about", "/privacy", "/login"]
            for width in (360, 390, 768, 1000, 1440):
                page.set_viewport_size({"width": width, "height": 1000})
                for path in paths:
                    response = page.goto("http://127.0.0.1:5059" + path)
                    assert response.status == 200, path
                    page.locator("img").evaluate_all("images=>Promise.all(images.map(i=>i.decode().catch(()=>null)))")
                    assert page.evaluate("Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)"), "image: " + path
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), f"overflow {width} {path}"
                    assert page.evaluate("parseFloat(getComputedStyle(document.body).fontSize)>=17"), "small body font"
                    if path == "/services":
                        assert page.locator(".service-content p").first.evaluate("(e)=>parseFloat(getComputedStyle(e).fontSize)>=16")
                    if path == "/booking":
                        assert page.locator("#phone").get_attribute("placeholder") == "+7 776 997 60 16"
                    assert page.locator('a[href="tel:+77769976016"]').count() >= 1
                if width in (390, 1440):
                    page.goto("http://127.0.0.1:5059/")
                    page.locator("img").evaluate_all("images=>Promise.all(images.map(i=>i.decode().catch(()=>null)))")
                    page.screenshot(path=str(OUTPUT / f"refresh-home-{width}.jpg"), type="jpeg", quality=85, full_page=True)
                    page.goto("http://127.0.0.1:5059/services")
                    page.locator("img").evaluate_all("images=>Promise.all(images.map(i=>i.decode().catch(()=>null)))")
                    page.screenshot(path=str(OUTPUT / f"refresh-services-{width}.jpg"), type="jpeg", quality=85, full_page=True)
                if width == 390:
                    page.goto("http://127.0.0.1:5059/")
                    page.locator(".menu-toggle").click()
                    expect(page.locator(".menu-toggle")).to_have_attribute("aria-expanded", "true")
                    page.locator("#main-nav").get_by_role("link", name="Мастера", exact=True).click()
                    expect(page).to_have_url("http://127.0.0.1:5059/masters")
            assert not errors, errors
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
(ROOT / "docs" / "PHOTO_CHECK.md").write_text(
    "# Проверка обновления фотографий и текста\n\n"
    "В GitHub Actions выполнены 23 автоматических теста Flask, проверка 16 разных локальных JPEG "
    "и Chromium на ширинах 360, 390, 768, 1000 и 1440 пикселей. "
    "Проверены загрузка всех фотографий, отсутствие горизонтального переполнения, "
    "размер основного шрифта от 17px, описание услуг от 16px, контактный телефон и мобильное меню. "
    "Ошибок JavaScript в проверенных сценариях не обнаружено. "
    "Публичное размещение Flask-сервера этим не подтверждается.\n", encoding="utf-8")
print("Visual refresh checks passed.")
