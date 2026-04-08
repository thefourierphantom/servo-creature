import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def load_json(relative_path: str):
    with open(BASE_DIR / relative_path, "r", encoding="utf-8") as f:
        return json.load(f)
