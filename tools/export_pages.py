"""Render public Flask templates as a static GitHub Pages preview."""
import html
import os
import re
import secrets
import shutil
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "_site"
BASE = "/" + os.environ.get("PAGES_BASE_PATH", "mira-beauty").strip("/")
if BASE == "/":
    BASE = ""
ROUTES = ("/", "/services", "/masters", "/gallery", "/about", "/booking", "/privacy", "/login")

def site_url(value):
    if not value or not value.startswith("/") or value.startswith("//"):
        return value
    parsed = urlsplit(value)
    path = parsed.path
    if path == "/static" or path.startswith("/static/"):
        target = BASE + path
    elif path.rstrip("/") in ROUTES or path == "/":
        target = BASE + path.rstrip("/") + "/"
    else:
        raise ValueError("Unexpected exported link: " + value)
    return urlunsplit(("", "", target, parsed.query, parsed.fragment))

class RewriteLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts = []

    def handle_decl(self, value):
        self.parts.append("<!" + value + ">")

    def tag(self, name, attrs, closing):
        if name == "meta" and dict(attrs).get("name") == "csrf-token":
            return
        attributes = []
        for key, value in attrs:
            if value is None:
                attributes.append(key)
            else:
                if key in {"href", "src", "data-image", "action"}:
                    value = site_url(value)
                attributes.append(key + '="' + html.escape(value, quote=True) + '"')
        self.parts.append("<" + name + (" " + " ".join(attributes) if attributes else "") + closing)

    def handle_starttag(self, name, attrs):
        self.tag(name, attrs, ">")

    def handle_startendtag(self, name, attrs):
        self.tag(name, attrs, " />")

    def handle_endtag(self, name):
        self.parts.append("</" + name + ">")

    def handle_data(self, value):
        self.parts.append(value)

    def handle_entityref(self, value):
        self.parts.append("&" + value + ";")

    def handle_charref(self, value):
        self.parts.append("&#" + value + ";")

    def handle_comment(self, value):
        self.parts.append("<!--" + value + "-->")

def export():
    sys.path.insert(0, str(ROOT))
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir()
    shutil.copytree(ROOT / "static", OUTPUT / "static")
    (OUTPUT / ".nojekyll").touch()
    with tempfile.TemporaryDirectory() as temporary:
        os.environ["MIRA_DATABASE"] = str(Path(temporary) / "preview.sqlite3")
        os.environ["MIRA_SECRET_KEY"] = secrets.token_hex(32)
        from app import create_app
        from flask import render_template
        application = create_app({"TESTING": True})
        application.context_processor(lambda: {"pages_preview": True})
        notices = {
            "/booking": ("Контакты проекта", "В этой демонстрационной версии онлайн-запись отключена. Заявки не отправляются и не сохраняются."),
            "/login": ("Кабинет недоступен", "В этой демонстрационной версии вход администратора отключён."),
            "/privacy": ("Обработка данных", "В этой версии сайта нет формы отправки заявок. Имена, телефоны и пароли посетителей через формы не собираются."),
        }
        with application.test_client() as client:
            for route in ROUTES:
                if route in notices:
                    with application.test_request_context(route):
                        heading, message = notices[route]
                        content = render_template("pages_notice.html", heading=heading, message=message)
                else:
                    response = client.get(route)
                    assert response.status_code == 200, route
                    content = response.get_data(as_text=True)
                content = re.sub(r"Запись действительно сохраняется, но для\s+проверки нужно использовать вымышленные имя и телефон\.", "В опубликованной версии доступен просмотр сайта; онлайн-запись отключена.", content)
                parser = RewriteLinks()
                parser.feed(content)
                parser.close()
                target = OUTPUT / route.lstrip("/") / "index.html" if route != "/" else OUTPUT / "index.html"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("".join(parser.parts), encoding="utf-8")
            error = client.get("/not-a-real-page")
            parser = RewriteLinks()
            parser.feed(error.get_data(as_text=True))
            (OUTPUT / "404.html").write_text("".join(parser.parts), encoding="utf-8")
    print("Static preview built: 8 pages and 19 local photos. No booking API or database is published.")

if __name__ == "__main__":
    export()
