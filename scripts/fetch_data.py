import requests, json, os
from datetime import datetime
from io import BytesIO
import openpyxl

HEADERS = {'User-Agent': 'Mozilla/5.0'}
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

def save_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✓ {filename}")

def update_meta():
    save_json('meta.json', {
        'last_run': datetime.now().isoformat(),
        'updated': datetime.now().isoformat()[:10]
    })

if __name__ == '__main__':
    print("Osvježavanje podataka...")
    update_meta()
    print("Završeno!")
