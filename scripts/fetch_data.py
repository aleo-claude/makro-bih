"""
fetch_data.py — Makro BiH
Preuzima podatke s BHAS i sprema kompaktne data/*.json
GitHub Actions: pokreće se svaki dan u 10h
"""

import requests, json, os, re
from datetime import datetime
from io import BytesIO
from collections import defaultdict

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
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    print(f"  OK {filename} ({os.path.getsize(path)//1024} KB)")

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
    try: return round(float(s), 2)
    except: return None

def is_period(val):
    s = str(val or '').strip()
    return bool(
        re.match(r'^(19|20)\d{2}$', s) or
        re.match(r'^(19|20)\d{2}-\d{1,2}$', s) or
        re.match(r'^(19|20)\d{2}[Qq]\d$', s)
    )

def sort_periods(periods):
    def norm(p):
        if '-' in p:
            yr, mo = p.split('-', 1)
            return yr + '-' + mo.zfill(2)
        return p
    return sorted(periods, key=norm)

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

def compact_series(series_dict, n_periods=72, max_series=20):
    """Uzmi zadnjih N perioda i top M serija - reducira veličinu JSON-a"""
    if not series_dict: return {}
    
    # Sve periode sortirane
    all_periods = set()
    for s in series_dict.values():
        all_periods.update(s.keys())
    periods = sort_periods(all_periods)[-n_periods:]
    
    # Top M serija po ukupnoj vrijednosti
    totals = {k: sum(abs(v) for v in s.values()) for k, s in series_dict.items()}
    top_keys = sorted(totals, key=totals.get, reverse=True)[:max_series]
    
    result = {}
    for k in top_keys:
        s = series_dict[k]
        result[k] = {p: s[p] for p in periods if p in s}
    
    return result

# ─────────────────────────────────────────────────────────────
# DATASETI
# ─────────────────────────────────────────────────────────────

def fetch_standard(key, name, urls, sheets_idx, outfile, n_periods=72):
    print(f"-> {name}...")
    last_error = None
    for url in urls:
        fname = url.split('/')[-1]
        try:
            print(f"  Probam: {fname}")
            xls = fetch_excel(url)
            wb = openpyxl.load_workbook(xls, data_only=True)
            all_data = {}
            for idx in sheets_idx:
                if idx >= len(wb.sheetnames): continue
                sname = wb.sheetnames[idx]
                parsed = parse_sheet(wb[sname])
                if parsed:
                    compact = compact_series(parsed, n_periods=n_periods)
                    all_data[sname] = compact
                    first = next(iter(compact.values()))
                    print(f"    OK '{sname}': {len(compact)} serija, {len(first)} perioda")
            if not all_data:
                raise ValueError("Nema podataka")
            save_json(outfile, {
                'source': 'BHAS', 'name': name,
                'url': url, 'updated': datetime.now().isoformat()[:10],
                'sheets': all_data
            })
            return True
        except Exception as e:
            print(f"  X {fname}: {e}")
            last_error = str(e)
    path = os.path.join(DATA_DIR, outfile)
    if not os.path.exists(path):
        save_json(outfile, {'source':'BHAS','name':name,'error':last_error,
                            'updated':datetime.now().isoformat()[:10],'sheets':{}})
    return False

def fetch_vanjska_trgovina():
    """Posebna obrada - ETR ima samo jednu seriju UK + HS poglavlja"""
    print("-> Vanjska trgovina (BHAS ETR_01)...")
    urls = [
        'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/ETR_01.xlsx',
        'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/ETR_02.xlsx',
    ]
    for url in urls:
        fname = url.split('/')[-1]
        try:
            print(f"  Probam: {fname}")
            xls = fetch_excel(url)
            wb = openpyxl.load_workbook(xls, data_only=True)
            sname = wb.sheetnames[0]
            full = parse_sheet(wb[sname])
            if not full: raise ValueError("Nema podataka")
            
            # Sortirani periodi - zadnjih 84 (7 godina)
            all_periods = set()
            for s in full.values(): all_periods.update(s.keys())
            periods = sort_periods(all_periods)[-84:]
            
            # UK = ukupna razmjena
            uk = {p: full['UK'][p] for p in periods if p in full.get('UK', {})}
            
            # Godišnji zbroj
            annual = defaultdict(float)
            for p, v in full.get('UK', {}).items():
                annual[p.split('-')[0]] += v
            
            # Top 15 HS poglavlja
            hs_totals = {k: sum(abs(v) for v in s.values()) 
                        for k, s in full.items() if k != 'UK' and k.isdigit()}
            top15_hs = sorted(hs_totals, key=hs_totals.get, reverse=True)[:15]
            
            compact = {
                'UK': uk,
                'annual': {yr: round(v/1e9, 3) for yr, v in sorted(annual.items())[-10:]},
            }
            for k in top15_hs:
                compact[k] = {p: full[k][p] for p in periods if p in full.get(k, {})}
            
            save_json('vanjska_trgovina.json', {
                'source': 'BHAS ETR_01',
                'name': 'Vanjska trgovina - robna razmjena BiH',
                'url': url,
                'updated': datetime.now().isoformat()[:10],
                'note': 'UK=ukupna robna razmjena, 01-99=HS poglavlja',
                'periods': periods,
                'data': compact
            })
            
            # Provjeri veličinu
            p = os.path.join(DATA_DIR, 'vanjska_trgovina.json')
            print(f"    UK serija: {len(uk)} perioda, {periods[-1]} zadnji")
            print(f"    Godišnji UK 2024: {annual.get('2024', 0)/1e9:.2f} mlrd BAM")
            return True
            
        except Exception as e:
            print(f"  X {fname}: {e}")
    
    return False

def update_meta(results):
    meta = {'last_run': datetime.now().isoformat(), 
            'updated': datetime.now().isoformat()[:10], 
            'datasets': {}}
    for fname in ['maloprodaja.json','turizam.json','industrija.json',
                  'vanjska_trgovina.json','cpi.json','place.json']:
        path = os.path.join(DATA_DIR, fname)
        if os.path.exists(path):
            with open(path) as f:
                d = json.load(f)
            key = fname.replace('.json','')
            meta['datasets'][key] = {
                'name': d.get('name', key),
                'updated': d.get('updated'),
                'has_data': bool(d.get('sheets') or d.get('data')),
                'has_error': 'error' in d,
                'size_kb': os.path.getsize(path) // 1024
            }
    save_json('meta.json', meta)

if __name__ == '__main__':
    print(f"\n{'='*55}")
    print(f"Makro BiH - Osvjezavanje podataka")
    print(f"Datum: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*55}\n")

    results = {}

    results['maloprodaja'] = fetch_standard(
        'maloprodaja', 'Indeksi prometa trgovine na malo',
        ['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/STS_01.xlsx'],
        [0, 1], 'maloprodaja.json')
    print()

    results['turizam'] = fetch_standard(
        'turizam', 'Turizam - dolasci i nocenja',
        ['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/TUR_01.xlsx'],
        [0, 1, 2], 'turizam.json')
    print()

    results['industrija'] = fetch_standard(
        'industrija', 'Indeks industrijske proizvodnje',
        ['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/IND_01.xlsx'],
        [0, 1], 'industrija.json')
    print()

    results['vanjska_trgovina'] = fetch_vanjska_trgovina()
    print()

    results['cpi'] = fetch_standard(
        'cpi', 'Indeks potrosackih cijena (CPI)',
        ['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/CPI_01.xlsx',
         'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/CPI_02.xlsx'],
        [0, 1], 'cpi.json')
    print()

    results['place'] = fetch_standard(
        'place', 'Place i zaposlenost',
        ['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/LAB_01.xlsx',
         'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/EMP_01.xlsx'],
        [0, 1, 2], 'place.json')
    print()

    print("-> Meta...")
    update_meta(results)

    success = sum(results.values())
    print(f"\n{'='*55}")
    print(f"Zavrseno: {success}/{len(results)} uspjesno")
    for key, ok in results.items():
        print(f"  {'OK' if ok else 'X '} {key}")
    print(f"{'='*55}\n")
