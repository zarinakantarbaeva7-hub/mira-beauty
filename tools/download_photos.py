"""Скачать выбранные фотографии Pexels в проект. Источники — docs/PHOTO_SOURCES.json."""
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "static" / "images"

def download_photos():
    items = json.loads((ROOT / "docs" / "PHOTO_SOURCES.json").read_text(encoding="utf-8"))
    TARGET.mkdir(parents=True, exist_ok=True)
    hashes = set()
    for item in items:
        name = item["filename"]
        if Path(name).name != name or not name.endswith(".jpg"):
            raise ValueError("Некорректное имя файла фотографии.")
        parsed = urlparse(item["url"])
        if parsed.scheme != "https" or parsed.hostname != "images.pexels.com":
            raise ValueError("Неожиданный источник фотографии.")
        path = TARGET / name
        if path.exists() and path.read_bytes().startswith(b"\xff\xd8\xff"):
            body = path.read_bytes()
        else:
            body = None
            last_error = None
            for attempt in range(3):
                try:
                    request = Request(item["url"], headers={"User-Agent": "MiraBeautyPhotoDownloader/1.0"})
                    with urlopen(request, timeout=45) as response:
                        body = response.read(12 * 1024 * 1024 + 1)
                    if not body.startswith(b"\xff\xd8\xff") or not 2000 <= len(body) <= 12 * 1024 * 1024:
                        raise ValueError("Вместо фотографии получен неожиданный файл.")
                    break
                except Exception as error:
                    last_error = error
                    body = None
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))
            if body is None:
                raise RuntimeError("Не удалось загрузить " + name + ": " + str(last_error))
            temporary = path.with_suffix(".download")
            temporary.write_bytes(body)
            temporary.replace(path)
        digest = hashlib.sha256(body).hexdigest()
        if digest in hashes:
            raise ValueError("Найдены одинаковые фотографии.")
        hashes.add(digest)
        print(name + ": OK (" + str(len(body)) + " bytes)")
    print("Готово: " + str(len(items)) + " разных фотографий сохранены локально.")

if __name__ == "__main__":
    download_photos()
