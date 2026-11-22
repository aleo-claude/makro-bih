"""
Fiskalni promet FBiH (Porezna uprava FBiH) - azuriranje dashboarda iz PDF izvjestaja.

Kako radi: u mapu data/fiskalni_raw/ uploadas mjesecni PDF izvjestaj (npr. 2611.pdf).
Skripta procita SVE PDF-ove iz te mape, nade mjesece koji jos nisu u dashboardu
i dopise ih u docs/docs/index.html (blokovi DATA i YOY_DATA + tekstovi KPI kartica).
Mjesec se prepoznaje iz naslova unutar PDF-a, pa ime datoteke nije bitno.
"""
import sys, json, re, glob, os
import pdfplumber
num=r'-?\d{1,3}(?:\.\d{3})*,\d{2}'
def pn(x): return float(x.replace('.','').replace(',','.'))
def parse(path):
    rows={}
    title=None
    with pdfplumber.open(path) as p:
        for pg in p.pages:
            t=pg.extract_text() or ''
            for ln in t.split('\n'):
                if title is None and 'Izvje' in ln: title=ln
                m=re.match(r'^(\D+?)\s+('+num+r')\s+('+num+r')\s+[\d,]+\s+('+num+r')\s',ln)
                if m:
                    rows[m.group(1).strip()]=(pn(m.group(2)),pn(m.group(3)))
    return title,rows

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
RAW = os.path.join(ROOT, 'data', 'fiskalni_raw')
HTML_FILES = [os.path.join(ROOT, 'docs', 'docs', 'index.html')]
MJ = {'januar':1,'februar':2,'mart':3,'april':4,'maj':5,'juni':6,'juli':7,'avgust':8,'septembar':9,'oktobar':10,'novembar':11,'decembar':12}
HR=['','Siječanj','Veljača','Ožujak','Travanj','Svibanj','Lipanj','Srpanj','Kolovoz','Rujan','Listopad','Studeni','Prosinac']
HS=['','Sij','Velj','Ožu','Tra','Svi','Lip','Srp','Kol','Ruj','Lis','Stu','Pro']
RIM=['','I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII']

def period_from_title(t):
    m = re.search(r'mjesec\s+(\w+)\s+(\d{4})', t or '', re.I)
    if not m or m.group(1).lower() not in MJ: return None
    return '%s-%02d' % (m.group(2), MJ[m.group(1).lower()])

def read_pdfs():
    out = {}
    for pf in sorted(glob.glob(os.path.join(RAW, '*.pdf'))):
        try:
            t, r = parse(pf)
            p = period_from_title(t)
            if p and len(r) >= 70:
                out[p] = {k: v[1] for k, v in r.items()}
            else:
                print('  X preskacem %s (naslov/format nije prepoznat)' % os.path.basename(pf))
        except Exception as e:
            print('  X %s: %s' % (os.path.basename(pf), e))
    return out

def patch(f, pdfs):

    s=open(f,encoding='utf-8').read()
    i=s.index('const DATA = ')+len('const DATA = ')
    D,e=json.JSONDecoder().raw_decode(s[i:])
    dend=i+e
    j=s.index('const YOY_DATA = ')+len('const YOY_DATA = ')
    Y,e2=json.JSONDecoder().raw_decode(s[j:])
    yend=j+e2
    new={p:r for p,r in pdfs.items() if p not in D['monthly_fbih'] and p > max(D['monthly_fbih'])}
    if not new:
        return 'nema novih mjeseci'
    names=set(Y['all_grads'])
    for p,r in new.items():
        miss=set(r)-names; assert not miss,(p,miss)
    for p in sorted(new):
        r=new[p]; tot=sum(r.values()); py='%d-%s'%(int(p[:4])-1,p[5:])
        D['monthly_fbih'][p]=round(tot,2); D['all_periods'].append(p)
        D['monthly_yoy'][p]=round((tot/D['monthly_fbih'][py]-1)*100,2)
        for g in D['top_grads']: D['grad_monthly'][g][p]=r[g]
    # trailing 12m
    def prevm(p,n):
        y,m=int(p[:4]),int(p[5:]); k=y*12+m-1-n; return '%d-%02d'%(k//12,k%12+1)
    for p in sorted(new):
        w=[prevm(p,n) for n in range(12)]
        if all(x in D['monthly_fbih'] for x in w): D['trailing_12m'][p]=sum(D['monthly_fbih'][x] for x in w)
    # provjera metode na postojecem
    w=[prevm('2026-02',n) for n in range(12)]
    assert abs(sum(D['monthly_fbih'][x] for x in w)-D['trailing_12m']['2026-02'])<1, 'trailing metoda'
    # YOY_DATA
    for p in sorted(new):
        r=new[p]; pm=prevm(p,1); py='%d-%s'%(int(p[:4])-1,p[5:])
        for g,v in r.items():
            gd=Y['grad_data'][g]
            c=gd.get(pm,{}).get('curr'); y=gd.get(py,{}).get('curr')
            gd[p]={'curr':v,'mom':round((v/c-1)*100,2) if c else None,'yoy':round((v/y-1)*100,2) if y else None}
        t=D['monthly_fbih'][p]; fd=Y['fbih_data']
        fd[p]={'curr':t,'mom':round((t/fd[pm]['curr']-1)*100,2),'yoy':round((t/fd[py]['curr']-1)*100,2)}
        Y['periods'].append(p)
    Y['periods']=Y['periods'][-12:]
    last=sorted(D['monthly_fbih'])[-1]; ly,lm=int(last[:4]),int(last[5:])
    yoyv=list(D['monthly_yoy'].values()); avg=sum(yoyv)/len(yoyv)
    peakp=max(D['monthly_fbih'],key=D['monthly_fbih'].get)
    out=s[:i]+json.dumps(D,ensure_ascii=False)+s[dend:j]+json.dumps(Y,ensure_ascii=False)+s[yend:]
    def rx(pattern, repl):
        nonlocal out
        out, n = re.subn(pattern, lambda m: repl, out, count=1)
        assert n == 1, 'tekst nije pronadjen: ' + pattern
    rim = '%s/%d' % (RIM[lm], ly)
    rx(r'Ažurirano: [IVX]+/\d{4}', 'Ažurirano: ' + rim)
    rx(r'id="trailing-as-of">do [IVX]+/\d{4}<', 'id="trailing-as-of">do ' + rim + '<')
    rx(r'YoY [A-Za-zčćžšđ]+ \d{4}</div>', 'YoY %s %d</div>' % (HS[lm], ly))
    rx(r'<div class="kpi-value">[+-][\d.]+%</div>\n(\s*)<div class="kpi-change neu">vs prosjek [+-][\d.]+%</div>',
       '<div class="kpi-value">%+.1f%%</div>\n        <div class="kpi-change neu">vs prosjek %+.1f%%</div>' % (D['monthly_yoy'][last], avg))
    rx(r"change: '[A-Za-zčćžšđ]+ \d{4}', changeColor: 'var\(--accent\)'", "change: '%s %d', changeColor: 'var(--accent)'" % (HS[int(peakp[5:])], int(peakp[:4])))
    rx(r'id="trailing-val">[^<]*</div>', 'id="trailing-val">%.1f mlrd</div>' % (D['trailing_12m'][last]/1e9))
    rx(r'<div class="kpi-label">Peak mjesec</div>\n\s*<div class="kpi-value">[^<]*</div>\n\s*<div class="kpi-change neu">[^<]*</div>',
       '<div class="kpi-label">Peak mjesec</div>\n        <div class="kpi-value">%.2f mlrd</div>\n        <div class="kpi-change neu">%s %d</div>' % (D['monthly_fbih'][peakp]/1e9, HS[int(peakp[5:])], int(peakp[:4])))
    # MONTHS_LABEL
    a=out.index('const MONTHS_LABEL = {'); b=out.index('};',a)+2
    ml=',\n  '.join("'%s':'%s %s'"%(p,HR[int(p[5:])],p[2:4]) for p in Y['periods'])
    out=out[:a]+'const MONTHS_LABEL = {\n  '+ml+'\n};'+out[b:]
    p0,p1=Y['periods'][0],Y['periods'][-1]
    rx(r"sub = 'Promet [^']*\(M BAM\)';", "sub = 'Promet %s %s – %s %s (M BAM)';" % (HS[int(p0[5:])], p0[:4], HS[int(p1[5:])], p1[:4]))
    rng = '%s %s – %s %s' % (HS[int(p0[5:])], p0[:4], HS[int(p1[5:])], p1[:4])
    out = re.sub(r'Mjesečni YoY [^<]*</h3>', 'Mjesečni YoY ' + rng + '</h3>', out)
    out = re.sub(r'Promet po općinama — [^<]*</div>', 'Promet po općinama — ' + rng + '</div>', out)
    out = re.sub(r'<option value="latest_desc">[^<]*</option>', '<option value="latest_desc">%s %s ↓</option>' % (HS[int(p1[5:])], p1[:4]), out)
    open(f,'w',encoding='utf-8').write(out)
    return last,avg,peakp,{p:(round(D['monthly_fbih'][p]/1e9,3),D['monthly_yoy'][p],round(D['trailing_12m'].get(p,0)/1e9,2)) for p in sorted(new)}

def main():
    print("-> Fiskalni promet FBiH (PDF izvjestaji)...")
    pdfs = read_pdfs()
    print('  PDF mjeseci u mapi: %s' % (sorted(pdfs)[-3:] if pdfs else 'nema'))
    ok = True
    for f in HTML_FILES:
        if not os.path.exists(f):
            print('  X ne postoji %s' % f); ok = False; continue
        try:
            print('  OK %s: %s' % (os.path.basename(f), patch(f, pdfs)))
        except AssertionError as e:
            print('  X provjera nije prosla: %s' % e); ok = False
    return ok

if __name__ == '__main__':
    sys.exit(0 if main() else 1)
