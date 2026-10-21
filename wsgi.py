"""WSGI entry point for hosting Mira Beauty over HTTPS."""
import os
import sys
from pathlib import Path

project_path = str(Path(__file__).resolve().parent)
if project_path not in sys.path:
    sys.path.insert(0, project_path)
os.environ.setdefault("MIRA_HTTPS", "1")

from app import app as application
