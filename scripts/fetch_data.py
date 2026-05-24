"""
fetch_data.py — Makro BiH
"""
import requests, json, os, re
try:
    import pdfplumber
except ImportError:
    os.system('pip install pdfplumber')
    import pdfplumber
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
    if 'html' in ct.lower(): raise ValueError(f"HTML umjesto Excel")
    if len(r.content) < 2000: raise ValueError(f"Premali ({len(r.content)} bytes)")
    return BytesIO(r.content)

def parse_num(val):
    if val is None: return None
    s = str(val).strip().replace('\xa0','').replace(' ','')
    if s in ('','-',':','...','n/a','N/A','x','X'): return None
    if re.match(r'^-?[\d.]+,\d+$', s): s = s.replace('.','').replace(',','.')
    try: return round(float(s), 2)
    except: return None

def is_period(val):
    s = str(val or '').strip()
    return bool(re.match(r'^(19|20)\d{2}$', s) or
                re.match(r'^(19|20)\d{2}-\d{1,2}$', s) or
                re.match(r'^(19|20)\d{2}[Qq]\d$', s))

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
    if not series_dict: return {}
    all_periods = set()
    for s in series_dict.values(): all_periods.update(s.keys())
    periods = sort_periods(all_periods)[-n_periods:]
    totals = {k: sum(abs(v) for v in s.values()) for k, s in series_dict.items()}
    top_keys = sorted(totals, key=totals.get, reverse=True)[:max_series]
    return {k: {p: series_dict[k][p] for p in periods if p in series_dict[k]} for k in top_keys}

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
            if not all_data: raise ValueError("Nema podataka")
            save_json(outfile, {'source':'BHAS','name':name,'url':url,
                                'updated':datetime.now().isoformat()[:10],'sheets':all_data})
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
    """
    ETR_01 = ukupna razmjena (izvoz+uvoz) po HS poglavljima
    ETR_02 = izvoz po HS poglavljima
    ETR_03 = uvoz po HS poglavljima
    """
    print("-> Vanjska trgovina (BHAS ETR_01/02/03)...")
    
    def load_etr(urls):
        for url in urls:
            fname = url.split('/')[-1]
            try:
                print(f"  Probam: {fname}")
                xls = fetch_excel(url)
                wb = openpyxl.load_workbook(xls, data_only=True)
                sname = wb.sheetnames[0]
                full = parse_sheet(wb[sname])
                if not full: raise ValueError("Nema podataka")
                print(f"    OK '{sname}': {len(full)} serija")
                return full, url
            except Exception as e:
                print(f"  X {fname}: {e}")
        return None, None

    # Učitaj sve tri serije
    etr01, url01 = load_etr(['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/ETR_01.xlsx'])
    etr02, url02 = load_etr(['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/ETR_02.xlsx'])
    etr03, url03 = load_etr(['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/ETR_03.xlsx'])

    if not etr01:
        save_json('vanjska_trgovina.json', {'source':'BHAS','error':'ETR_01 nije dostupan',
                                             'updated':datetime.now().isoformat()[:10],'data':{}})
        return False

    # Periodi - zadnjih 84
    all_periods = set()
    for s in etr01.values(): all_periods.update(s.keys())
    periods = sort_periods(all_periods)[-84:]

    # ETR_01 UK = IZVOZ BiH po HS poglavljima (potvrđeno s BHAS PDF saopštenjima)
    # ETR_02 UK = UVOZ BiH po zemljama porijekla (potvrđeno s BHAS PDF saopštenjima)
    # ETR_03 = nedostupan (403)
    
    izvoz_series = etr01.get('UK', {})
    izvoz = {p: izvoz_series[p] for p in periods if p in izvoz_series}
    print(f"  Izvoz (ETR_01 UK): {len(izvoz)} perioda")

    uvoz = {}
    if etr02:
        # ETR_02 ima UK seriju koja je ukupni uvoz
        uvoz_series = etr02.get('UK', etr02.get(list(etr02.keys())[0], {}))
        uvoz = {p: uvoz_series[p] for p in periods if p in uvoz_series}
        print(f"  Uvoz (ETR_02 UK): {len(uvoz)} perioda")
    
    # Za kompatibilnost sa starim kodom
    uk_compact = izvoz
    ex = izvoz
    im = uvoz

    # Godišnji zbroj
    annual_uk, annual_ex, annual_im = defaultdict(float), defaultdict(float), defaultdict(float)
    for p, v in uk.items():
        annual_uk[p.split('-')[0]] += v
    for p, v in ex.items():
        annual_ex[p.split('-')[0]] += v
    for p, v in im.items():
        annual_im[p.split('-')[0]] += v

    # Top 10 HS poglavlja po ukupnoj vrijednosti
    hs_totals = {k: sum(abs(v) for v in s.values()) 
                for k, s in etr01.items() if k != 'UK' and k.isdigit()}
    top10_hs = sorted(hs_totals, key=hs_totals.get, reverse=True)[:10]

    data = {
        'UK': uk_compact,
        'EX': izvoz,  # izvoz (ETR_01)
        'IM': uvoz,   # uvoz (ETR_02)
        'annual': {
            yr: {
                'uk': round(annual_uk.get(yr, 0)/1e9, 3),
                'ex': round(annual_ex.get(yr, 0)/1e9, 3),
                'im': round(annual_im.get(yr, 0)/1e9, 3),
            }
            for yr in sorted(set(list(annual_uk.keys())[-10:]))
        },
    }
    for k in top10_hs:
        data[k] = {p: etr01[k][p] for p in periods if p in etr01.get(k, {})}

    save_json('vanjska_trgovina.json', {
        'source': 'BHAS ETR_01/02/03',
        'name': 'Vanjska trgovina - izvoz, uvoz, razmjena BiH',
        'url': url01,
        'updated': datetime.now().isoformat()[:10],
        'note': 'EX=izvoz(ETR_01 UK), IM=uvoz(ETR_02 UK), 01-99=HS poglavlja',
        'has_ex': bool(izvoz),
        'has_im': bool(uvoz),
        'periods': periods,
        'data': data
    })
    return True

def update_meta(results):
    meta = {'last_run': datetime.now().isoformat(),
            'updated': datetime.now().isoformat()[:10],
            'datasets': {}}
    for fname in ['maloprodaja.json','turizam.json','industrija.json',
                  'vanjska_trgovina.json','cpi.json','place.json']:
        path = os.path.join(DATA_DIR, fname)
        if os.path.exists(path):
            with open(path) as f: d = json.load(f)
            key = fname.replace('.json','')
            meta['datasets'][key] = {
                'name': d.get('name', key),
                'updated': d.get('updated'),
                'has_data': bool(d.get('sheets') or d.get('data')),
                'has_error': 'error' in d,
                'size_kb': os.path.getsize(path) // 1024
            }
    save_json('meta.json', meta)


# ─────────────────────────────────────────────────────────────
# DODATAK: fetch_vanjska_trgovina_detalji
# Parsira BHAS saopštenja (PDF) za zasebni izvoz i uvoz
# ─────────────────────────────────────────────────────────────
def fetch_etr_detalji():
    """
    Parsira BHAS PDF saopštenja za vanjsku trgovinu.
    Svako saopštenje sadrži tablicu: Izvoz i Uvoz po mjesecima.
    URL: https://bhas.gov.ba/data/Publikacije/Saopstenja/YYYY/ETR_01_YYYY_MM_1_BS.pdf
    """
    print("-> Vanjska trgovina detalji (BHAS PDF saopstenja)...")
    
    try:
        import pdfplumber
    except ImportError:
        os.system("pip install pdfplumber")
        import pdfplumber
    
    results_ex = {}  # izvoz po periodu
    results_im = {}  # uvoz po periodu
    
    # Generiraj URL-ove za zadnjih 30 mjeseci
    from datetime import date
    today = date.today()
    
    for delta in range(0, 30):
        month = today.month - delta
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        
        period = f"{year}-{month}"
        
        # Probaj BS i HR verziju
        for lang in ['BS', 'HR']:
            url = f"https://bhas.gov.ba/data/Publikacije/Saopstenja/{year}/ETR_01_{year}_{month:02d}_1_{lang}.pdf"
            try:
                r = requests.get(url, headers=HEADERS, timeout=20)
                if r.status_code != 200 or len(r.content) < 5000:
                    continue
                
                with pdfplumber.open(BytesIO(r.content)) as pdf:
                    text = ""
                    for page in pdf.pages[:2]:
                        t = page.extract_text()
                        if t:
                            text += t + "\n"
                
                if not text:
                    continue
                
                # Parsira tablicu UKUPNO/TOTAL
                # Format: UKUPNO TOTAL [ex_prev] [ex_curr] [im_prev] [im_curr] ...
                import re
                
                # Traži redak s UKUPNO i brojeve
                for line in text.split('\n'):
                    if 'UKUPNO' in line or ('TOTAL' in line and any(c.isdigit() for c in line)):
                        # Izvuci sve grupe cifara (000 KM)
                        nums = re.findall(r'(\d[\d\s]{3,12}\d)', line)
                        cleaned = []
                        for n in nums:
                            try:
                                val = int(n.replace(' ', ''))
                                if 500000 < val < 5000000:  # razumne vrijednosti u 000 KM
                                    cleaned.append(val * 1000)  # pretvori u KM
                            except:
                                pass
                        
                        if len(cleaned) >= 4:
                            # Format: [ex_prev, ex_curr, im_prev, im_curr, ...]
                            # ili [ex_prev, im_prev, ex_curr, im_curr, ...]
                            # Odredit ćemo na osnovu veličine (uvoz je veći od izvoza)
                            ex_curr = min(cleaned[1], cleaned[0])
                            im_curr = max(cleaned[1], cleaned[0])
                            if len(cleaned) >= 4:
                                # Probaj 3. i 4. broj kao curr period
                                if cleaned[2] < cleaned[3]:
                                    ex_curr = cleaned[2]
                                    im_curr = cleaned[3]
                                else:
                                    ex_curr = cleaned[3]
                                    im_curr = cleaned[2]
                            
                            results_ex[period] = ex_curr
                            results_im[period] = im_curr
                            print(f"  OK {period} ({lang}): Ex={ex_curr/1e9:.3f}, Im={im_curr/1e9:.3f} mlrd")
                            break
                
                if period in results_ex:
                    break  # Ne trebamo drugu jezičnu verziju
                    
            except Exception as e:
                pass
    
    if not results_ex:
        print("  Nema podataka iz PDF saopstenja")
        return False
    
    # Spremi u poseban JSON
    save_json('vt_detalji.json', {
        'source': 'BHAS PDF Saopstenja',
        'name': 'Vanjska trgovina - Izvoz i Uvoz zasebno',
        'updated': datetime.now().isoformat()[:10],
        'note': 'Izvoz i uvoz u KM, parsiran iz PDF saopstenja',
        'EX': results_ex,
        'IM': results_im,
    })
    return True

def fetch_place_neto_bruto():
    """
    Preuzima plaće s BHAS LAB_01:
    - Sheet 0: NPL BPL = bruto plaće po sektorima  
    - Sheet 1: NPL NPL = neto plaće po sektorima (ako postoji)
    Probava i LAB_02/03 za neto.
    """
    print("-> Place neto i bruto po sektorima (BHAS LAB)...")
    
    urls = [
        'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/LAB_01.xlsx',
        'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/LAB_02.xlsx',
        'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/LAB_03.xlsx',
    ]
    
    all_sheets = {}
    used_url = None
    
    for url in urls:
        fname = url.split('/')[-1]
        try:
            print(f"  Probam: {fname}")
            xls = fetch_excel(url)
            wb = openpyxl.load_workbook(xls, data_only=True)
            
            print(f"    Sheetovi: {wb.sheetnames}")
            
            for idx, sname in enumerate(wb.sheetnames[:4]):
                parsed = parse_sheet(wb[sname])
                if parsed:
                    compact = compact_series(parsed, n_periods=72)
                    all_sheets[sname] = compact
                    first = next(iter(compact.values()))
                    print(f"    OK '{sname}': {len(compact)} serija, {len(first)} perioda")
            
            if all_sheets:
                used_url = url
                break
        except Exception as e:
            print(f"  X {fname}: {e}")
    
    if not all_sheets:
        path = os.path.join(DATA_DIR, 'place.json')
        if not os.path.exists(path):
            save_json('place.json', {'source':'BHAS','error':'Nedostupno',
                                     'updated':datetime.now().isoformat()[:10],'sheets':{}})
        return False
    
    save_json('place.json', {
        'source': 'BHAS',
        'name': 'Place neto i bruto po sektorima',
        'url': used_url,
        'updated': datetime.now().isoformat()[:10],
        'sheets': all_sheets
    })
    return True

if __name__ == '__main__':
    print(f"\n{'='*55}")
    print(f"Makro BiH - Osvjezavanje podataka")
    print(f"Datum: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*55}\n")

    results = {}
    results['maloprodaja'] = fetch_standard('maloprodaja','Indeksi prometa trgovine na malo',
        ['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/STS_01.xlsx'],[0,1],'maloprodaja.json')
    print()
    results['turizam'] = fetch_standard('turizam','Turizam',
        ['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/TUR_01.xlsx'],[0,1,2],'turizam.json')
    print()
    results['industrija'] = fetch_standard('industrija','Ind. proizvodnja',
        ['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/IND_01.xlsx'],[0,1],'industrija.json')
    print()
    results['vanjska_trgovina'] = fetch_vanjska_trgovina()
    print()
    results['vt_detalji'] = fetch_etr_detalji()
    print()
    results['cpi'] = fetch_standard('cpi','CPI',
        ['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/CPI_01.xlsx',
         'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/CPI_02.xlsx'],[0,1],'cpi.json')
    print()
    # LAB_01: sheet 0=bruto, sheet 1=neto (ako postoji)
    # LAB_02/03: alternativni izvori neto plaća
    results['place'] = fetch_place_neto_bruto()
    print()
    results['zaposlenost'] = fetch_standard('zaposlenost','Zaposleni po djelatnostima',
        ['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/LAB_04.xlsx',
         'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/EMP_01.xlsx',
         'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/EMP_02.xlsx'],
        [0,1,2],'zaposlenost.json')
    print()
    results['nezaposlenost'] = fetch_standard('nezaposlenost','Registrovana nezaposlenost',
        ['https://bhas.gov.ba/data/Publikacije/VremenskeSerije/LAB_05.xlsx',
         'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/UNE_01.xlsx',
         'https://bhas.gov.ba/data/Publikacije/VremenskeSerije/UNE_02.xlsx'],
        [0,1,2],'nezaposlenost.json')
    print()

    print("-> Meta...")
    update_meta(results)
    success = sum(results.values())
    print(f"\n{'='*55}")
    print(f"Zavrseno: {success}/{len(results)} uspjesno")
    for key, ok in results.items():
        print(f"  {'OK' if ok else 'X '} {key}")
    print(f"{'='*55}\n")
