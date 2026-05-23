"""
fetch_data.py — Makro BiH
Preuzima podatke s BHAS i sprema u data/*.json
Pokreće se automatski svaki dan putem GitHub Actions.
"""

import requests, json, os, re
from datetime import datetime
from io import BytesIO

try:
    import openpyxl
except ImportError:
    os.system("pip install openpyxl")
    import openpyxl

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*',
    'Referer': 'https://bhas.gov.ba/',
}
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

def save_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✓ {filename} ({os.path.getsize(path)//1024} KB)")

def fetch_excel(url, timeout=30):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    ct = r.headers.get('Content-Type', '')
    if 'html' in ct.lower():
        raise ValueError(f"HTML umjesto Excel")
    if len(r.content) < 2000:
        raise ValueError(f"Fajl premali ({len(r.content)} bytes)")
    return BytesIO(r.content)

def parse_num(val):
    if val is None: return None
    s = str(val).strip().replace('\xa0','').replace(' ','')
    if s in ('','-',':','...','n/a','N/A','x','X'): return None
    if re.match(r'^-?[\d.]+,\d+$', s):
        s = s.replace('.','').replace(',','.')
    try: return round(float(s), 4)
    except: return None

def is_period(val):
    s = str(val or '').strip()
    return bool(
        re.match(r'^(19|20)\d{2}$', s) or
        re.match(r'^(19|20)\d{2}-\d{1,2}$', s) or
        re.match(r'^(19|20)\d{2}[Qq]\d$', s)
    )

def parse_sheet(ws):
    rows = list(ws.iter_rows(values_only=True))
    if not rows: return {}
    first_row = [str(c or '').strip() for c in rows[0]]
    periods_in_cols = sum(1 for c in first_row if is_period(c))
    result = {}
    if periods_in_cols >= 3:
        for row in rows[1:]:
            if not row[0]: continue
            label = str(row[0]).strip()
            if not label: continue
            series = {}
            for j, h in enumerate(first_row[1:], 1):
                if h and is_period(h) and j < len(row):
                    v = parse_num(row[j])
                    if v is not None: series[h] = v
            if series: result[label] = series
    else:
        col_headers = first_row[1:]
        for row in rows[1:]:
            if not row[0] or not is_period(str(row[0])): continue
            period = str(row[0]).strip()
            for j, h in enumerate(col_headers):
                if not h: continue
                v = parse_num(row[j+1] if j+1 < len(row) else None)
                if v is not None:
                    if h not in result: result[h] = {}
                    result[h][period] = v
    return result

DATASETS = {
    'maloprodaja': {
        'name': 'Indeksi prometa trgovine na malo',
        'urls': ['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/STS_01.xlsx'],
        'file': 'maloprodaja.json', 'sheets': [0, 1],
    },
    'turizam': {
        'name': 'Turizam — dolasci i nocenja',
        'urls': ['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/TUR_01.xlsx'],
        'file': 'turizam.json', 'sheets': [0, 1, 2],
    },
    'industrija': {
        'name': 'Indeks industrijske proizvodnje',
        'urls': ['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/IND_01.xlsx'],
        'file': 'industrija.json', 'sheets': [0, 1],
    },
    'vanjska_trgovina': {
        'name': 'Vanjska trgovina - izvoz i uvoz',
        'urls': [
            'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/ETR_01.xlsx',
            'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/ETR_02.xlsx',
            'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/EXT_01.xlsx',
            'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/EXT_02.xlsx',
            'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/ETR_00.xlsx',
            'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/ETR_03.xlsx',
        ],
        'file': 'vanjska_trgovina.json', 'sheets': [0, 1, 2, 3],
    },
    'cpi': {
        'name': 'Indeks potrosackih cijena (CPI)',
        'urls': [
            'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/CPI_01.xlsx',
            'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/CPI_02.xlsx',
        ],
        'file': 'cpi.json', 'sheets': [0, 1],
    },
    'place': {
        'name': 'Place i zaposlenost',
        'urls': [
            'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/LAB_01.xlsx',
            'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/EMP_01.xlsx',
        ],
        'file': 'place.json', 'sheets': [0, 1, 2],
    },
}

def fetch_dataset(key, config):
    print(f"-> {config['name']}...")
    last_error = None
    for url in config['urls']:
        fname = url.split('/')[-1]
        try:
            print(f"  Probam: {fname}")
            xls = fetch_excel(url)
            wb = openpyxl.load_workbook(xls, data_only=True)
            all_data = {}
            for idx in config['sheets']:
                if idx >= len(wb.sheetnames): continue
                sname = wb.sheetnames[idx]
                parsed = parse_sheet(wb[sname])
                if parsed:
                    all_data[sname] = parsed
                    first = next(iter(parsed.values()))
                    print(f"    OK '{sname}': {len(parsed)} serija, {len(first)} perioda")
            if not all_data:
                raise ValueError("Nema parsiranih podataka")
            save_json(config['file'], {
                'source': 'BHAS', 'name': config['name'],
                'url': url, 'updated': datetime.now().isoformat()[:10],
                'sheets': all_data
            })
            return True
        except Exception as e:
            print(f"  X {fname}: {e}")
            last_error = str(e)

    path = os.path.join(DATA_DIR, config['file'])
    if not os.path.exists(path):
        save_json(config['file'], {
            'source': 'BHAS', 'name': config['name'],
            'error': last_error,
            'updated': datetime.now().isoformat()[:10],
            'sheets': {}
        })
    return False

def update_meta(results):
    meta = {'last_run': datetime.now().isoformat(), 'updated': datetime.now().isoformat()[:10], 'datasets': {}}
    for key, config in DATASETS.items():
        path = os.path.join(DATA_DIR, config['file'])
        if os.path.exists(path):
            with open(path) as f:
                d = json.load(f)
            meta['datasets'][key] = {
                'name': config['name'], 'updated': d.get('updated'),
                'has_data': bool(d.get('sheets')), 'has_error': 'error' in d,
                'size_kb': os.path.getsize(path) // 1024
            }
    save_json('meta.json', meta)

if __name__ == '__main__':
    print(f"\n{'='*55}")
    print(f"Makro BiH — Osvjezavanje podataka")
    print(f"Datum: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*55}\n")

    results = {}
    for key, config in DATASETS.items():
        results[key] = fetch_dataset(key, config)
        print()

    print("-> Meta...")
    update_meta(results)

    success = sum(results.values())
    print(f"\n{'='*55}")
    print(f"Zavrseno: {success}/{len(results)} uspjesno")
    for key, ok in results.items():
        print(f"  {'OK' if ok else 'X '} {DATASETS[key]['name']}")
    print(f"{'='*55}\n")
