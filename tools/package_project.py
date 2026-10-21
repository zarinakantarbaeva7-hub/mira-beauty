"""Create one self-contained, clean project ZIP without local data or environments."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "download"
ROOT_FILES = {
    ".gitignore", "README.md", "НАЧНИ_ЗДЕСЬ.txt", "Mira-Beauty.code-workspace",
    "OPEN_VSCODE.bat", "START.bat", "app.py", "data.py", "operator_app.py",
    "wsgi.py", "requirements.txt",
}
EXCLUDED_PARTS = {".git", ".venv", "instance", "__pycache__", ".package-check", "download"}
REQUIRED = {
    "app.py", "data.py", "operator_app.py", "wsgi.py", "requirements.txt",
    "START.bat", "OPEN_VSCODE.bat", "Mira-Beauty.code-workspace", "НАЧНИ_ЗДЕСЬ.txt",
    ".vscode/launch.json", "static/style.css", "static/script.js",
    "templates/index.html", "templates/base.html", "templates/_macros.html",
    "templates/services.html", "templates/booking.html", "templates/admin.html",
    "tests/test_app.py", "docs/РАЗМЕЩЕНИЕ.md", "docs/ЗАЩИТА.md",
    "docs/PHOTO_SOURCES.json", "tools/check_visual_refresh.py",
}

def selected(path):
    relative = path.relative_to(ROOT)
    if path.is_symlink() or any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    name = relative.as_posix()
    if name in ROOT_FILES:
        return True
    if name == ".vscode/launch.json":
        return True
    return relative.parts[0] in {"templates", "static", "docs", "tests", "tools"}

def main():
    files = [p for p in sorted(ROOT.rglob("*")) if p.is_file() and selected(p)]
    names = {p.relative_to(ROOT).as_posix() for p in files}
    assert REQUIRED <= names, "Missing required files: " + repr(REQUIRED - names)
    photos = json.loads((ROOT / "docs/PHOTO_SOURCES.json").read_text(encoding="utf-8"))
    assert len(photos) == 19
    hashes = []
    for photo in photos:
        name = "static/images/" + photo["filename"]
        assert name in names, name
        body = (ROOT / name).read_bytes()
        assert body.startswith(b"\xff\xd8\xff") and len(body) > 2000, name
        hashes.append(hashlib.sha256(body).hexdigest())
    assert len(set(hashes)) == 19, "Repeated photographs"
    workspace = json.loads((ROOT / "Mira-Beauty.code-workspace").read_text(encoding="utf-8"))
    assert workspace["folders"][0]["path"] == "."
    launch = json.loads((ROOT / ".vscode/launch.json").read_text(encoding="utf-8"))
    assert launch["configurations"][0]["env"]["MIRA_PORT"] == "5019"
    for filename in ("START.bat", "OPEN_VSCODE.bat"):
        assert b"\r\n" in (ROOT / filename).read_bytes(), filename
    assert "START_PHOTOS.bat" not in names
    assert not any(name.endswith((".sqlite3", ".db", ".pyc", ".env")) for name in names)
    OUTPUT.mkdir(exist_ok=True)
    target = OUTPUT / "Mira-Beauty.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            archive.write(path, "Mira-Beauty/" + path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None, "Damaged ZIP"
        assert len(archive.namelist()) == len(files)
        assert {name.split("/", 1)[0] for name in archive.namelist()} == {"Mira-Beauty"}
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (OUTPUT / "Mira-Beauty.sha256").write_text(digest + "  Mira-Beauty.zip\n", encoding="utf-8")
    print(f"Ready: {target.name}; {len(files)} files; 19 unique photos; {target.stat().st_size} bytes.")
    print("SHA256: " + digest)

if __name__ == "__main__":
    main()
