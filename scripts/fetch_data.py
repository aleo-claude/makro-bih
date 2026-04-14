"""
fetch_data.py — Makro BiH
Preuzima podatke s BHAS i sprema u data/*.json
Pokreće se automatski svaki dan putem GitHub Actions.
"""

import requests
import json
import os
import re
from datetime import datetime
from io import BytesIO

try:
    import openpyxl
except ImportError:
    os.system("pip install openpyxl")
    import openpyxl

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; MakroBiH/1.0; +https://github.com/aleo-claude/makro-bih)'}
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

def save_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    size = os.path.getsize(path)
    print(f"  ✓ {filename} ({size//1024} KB)")

def fetch_excel(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BytesIO(r.content)

def parse_num(val):
    if val is None:
        return None
    s = str(val).strip().replace('\xa0', '').replace(' ', '')
    if s in ('', '-', ':', '...', 'n/a', 'N/A'):
        return None
    if re.match(r'^-?[\d.]+,\d+$', s):
        s = s.replace('.', '').replace(',', '.')
    try:
        f = float(s)
        return None if (f == 0 and len(s) < 2) else f
    except:
        return None

def is_period(val):
    """Provjeri je li vrijednost period (godina, kvartal, mjesec)."""
    s = str(val or '').strip()
    return bool(re.match(r'^(19|20)\d{2}', s) or re.match(r'^\d{4}[Qq]\d$', s) or re.match(r'^\d{4}-\d{2}$', s))

def parse_sheet_as_timeseries(ws):
    """
    Parsira sheet gdje su:
    - Redovi = serije podataka (indikatori)
    - Kolone = periodi (godine, kvartali, mjeseci)
    Ili obrnuto — funkcija otkriva automatski.
    """
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {}

    # Probaj: prvi red = periodi (kolone su periodi)
    first_row = [str(c or '').strip() for c in rows[0]]
    periods_in_cols = sum(1 for c in first_row if is_period(c))

    result = {}

    if periods_in_cols >= 3:
        # Periodi su u kolonama (uobičajeni BHAS format)
        headers = first_row
        for row in rows[1:]:
            if not row[0]:
                continue
            label = str(row[0]).strip()
            if not label or label.lower() in ('ukupno', 'total', 'indeks', 'index'):
                continue
            series = {}
            for j, h in enumerate(headers[1:], 1):
                if h and is_period(h) and j < len(row):
                    v = parse_num(row[j])
                    if v is not None:
                        series[h] = v
            if series:
                result[label] = series
    else:
        # Periodi su u redovima (transponiran format)
        first_col = [str(r[0] or '').strip() if r else '' for r in rows]
        periods_in_rows = sum(1 for c in first_col if is_period(c))

        if periods_in_rows >= 3:
            # Zaglavlja su u prvom redu, periodi u prvoj koloni
            col_headers = first_row[1:]
            for row in rows[1:]:
                if not row[0] or not is_period(str(row[0])):
                    continue
                period = str(row[0]).strip()
                for j, h in enumerate(col_headers):
                    if not h:
                        continue
                    v = parse_num(row[j+1] if j+1 < len(row) else None)
                    if v is not None:
                        if h not in result:
                            result[h] = {}
                        result[h][period] = v

    return result

# ─────────────────────────────────────────────────────────────
# BHAS DATASETI
# ─────────────────────────────────────────────────────────────

BHAS_DATASETS = {
    'maloprodaja': {
        'name': 'Indeksi prometa trgovine na malo',
        'url': 'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/STS_01.xlsx',
        'file': 'maloprodaja.json',
        'sheets': [0, 1],  # Prvih N listova
    },
    'turizam': {
        'name': 'Turizam — dolasci i noćenja',
        'url': 'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/TUR_01.xlsx',
        'file': 'turizam.json',
        'sheets': [0, 1, 2],
    },
    'cpi': {
        'name': 'Indeks potrošačkih cijena (CPI)',
        'url': 'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/CPI_01.xlsx',
        'file': 'cpi.json',
        'sheets': [0, 1],
    },
    'industrija': {
        'name': 'Indeks industrijske proizvodnje',
        'url': 'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/IND_01.xlsx',
        'file': 'industrija.json',
        'sheets': [0, 1],
    },
    'vanjska_trgovina': {
        'name': 'Vanjska trgovina — izvoz i uvoz',
        'url': 'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/EXT_01.xlsx',
        'file': 'vanjska_trgovina.json',
        'sheets': [0, 1, 2],
    },
    'bdp': {
        'name': 'Bruto domaći proizvod (BDP)',
        'url': 'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/NAT_01.xlsx',
        'file': 'bdp.json',
        'sheets': [0, 1],
    },
}

def fetch_bhas_dataset(key, config):
    print(f"→ {config['name']}...")
    try:
        xls = fetch_excel(config['url'])
        wb = openpyxl.load_workbook(xls, data_only=True)
        
        all_data = {}
        sheet_names = wb.sheetnames
        
        for idx in config['sheets']:
            if idx >= len(sheet_names):
                continue
            sheet_name = sheet_names[idx]
            ws = wb[sheet_name]
            parsed = parse_sheet_as_timeseries(ws)
            if parsed:
                all_data[sheet_name] = parsed
                n_series = len(parsed)
                # Broj perioda u prvoj seriji
                first_series = next(iter(parsed.values()))
                n_periods = len(first_series)
                print(f"    Sheet '{sheet_name}': {n_series} serija, {n_periods} perioda")

        if not all_data:
            raise ValueError("Nema parsiranih podataka")

        save_json(config['file'], {
            'source': 'BHAS',
            'name': config['name'],
            'url': config['url'],
            'updated': datetime.now().isoformat()[:10],
            'sheets': all_data
        })
        return True

    except Exception as e:
        print(f"  ✗ Greška: {e}")
        # Spremi error JSON da pipeline ne puca
        path = os.path.join(DATA_DIR, config['file'])
        if not os.path.exists(path):
            save_json(config['file'], {
                'source': 'BHAS',
                'name': config['name'],
                'url': config['url'],
                'error': str(e),
                'updated': datetime.now().isoformat()[:10],
                'sheets': {}
            })
        return False

# ─────────────────────────────────────────────────────────────
# META
# ─────────────────────────────────────────────────────────────

def update_meta(results):
    meta = {
        'last_run': datetime.now().isoformat(),
        'updated': datetime.now().isoformat()[:10],
        'datasets': {}
    }
    
    for key, config in BHAS_DATASETS.items():
        path = os.path.join(DATA_DIR, config['file'])
        if os.path.exists(path):
            with open(path) as f:
                d = json.load(f)
            has_data = bool(d.get('sheets'))
            meta['datasets'][key] = {
                'name': config['name'],
                'updated': d.get('updated'),
                'has_data': has_data,
                'has_error': 'error' in d,
                'size_kb': os.path.getsize(path) // 1024
            }
    
    save_json('meta.json', meta)

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print(f"\n{'='*50}")
    print(f"Makro BiH — Osvježavanje podataka")
    print(f"Datum: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*50}\n")

    results = {}
    for key, config in BHAS_DATASETS.items():
        results[key] = fetch_bhas_dataset(key, config)

    print("\n→ Meta status...")
    update_meta(results)

    success = sum(results.values())
    total = len(results)
    print(f"\n{'='*50}")
    print(f"Završeno: {success}/{total} dataseta preuzeto uspješno")
    print(f"{'='*50}\n")
