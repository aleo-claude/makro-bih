# Makro FBiH — Ekonomski Dashboard

Automatski dashboard koji svaki dan preuzima makro podatke s BHAS, FZS i CBBH portala i prikazuje ih u interaktivnoj web stranici.

## Arhitektura

```
GitHub Actions (cron svaki dan u 10h)
    ↓
scripts/fetch_data.py
    ↓  preuzima Excel s bhas.gov.ba i fzs.ba
    ↓  parsira u čisti JSON
    ↓
data/*.json  (commitaju se automatski)
    ↓
GitHub Pages
    ↓
docs/index.html  (dashboard čita JSON svaki put kad se otvori)
```

**Nikad ne trebaš ručno ažurirati podatke.**

---

## Postavljanje (jednom)

### 1. Fork ili kreiraj repozitorij

Idi na GitHub i kreiraj novi **javni** repozitorij naziva `makro-bih`.

### 2. Uploadaj fajlove

Uploadaj sve fajlove iz ovog ZIP-a u repozitorij:
```
makro-bih/
├── .github/workflows/update-data.yml
├── scripts/fetch_data.py
├── data/               ← GitHub Actions će ovo popunjavati
├── docs/index.html     ← tvoj dashboard
└── README.md
```

### 3. Uključi GitHub Pages

1. Idi na **Settings → Pages**
2. Source: **Deploy from branch**
3. Branch: `main`, folder: `/docs`
4. Klikni **Save**

Nakon par minuta tvoj dashboard je živ na:
`https://TVOJE-IME.github.io/makro-bih/`

### 4. Pokreni prvi fetch ručno

1. Idi na **Actions → Osvježi podatke**
2. Klikni **Run workflow**
3. Čekaj ~2 minute

To je to! Od sada se podaci osvježavaju svakog dana automatski.

---

## Izvori podataka

| Dataset | Izvor | Frekvencija | URL |
|---------|-------|-------------|-----|
| Maloprodajni indeks | BHAS STS_01 | Mjesečno | [bhas.gov.ba](https://bhas.gov.ba/Calendar/Category/20) |
| Turizam (noćenja) | BHAS TUR_01 | Mjesečno | [bhas.gov.ba](https://bhas.gov.ba/Calendar/Category/19) |
| CPI Inflacija | BHAS CPI_01 | Mjesečno | [bhas.gov.ba](https://bhas.gov.ba/Calendar/Category/10) |
| Plaće FBiH | FZS | Mjesečno | [fzs.ba](https://fzs.ba) |
| Fiskalni promet | FIA FBiH | Mjesečno | Ručno upload |

---

## Dodavanje novih dataseta

1. Otvori `scripts/fetch_data.py`
2. Dodaj novu funkciju `fetch_NAZIV()`
3. Pozovi je u `main`
4. Dashboard automatski čita novi JSON iz `data/`

---

## Troubleshooting

**Actions ne rade?**
- Settings → Actions → General → Allow all actions ✓

**Podaci stari?**
- Actions → Osvježi podatke → Run workflow (ručni trigger)

**BHAS promijenio URL?**
- Provjeri `scripts/fetch_data.py` i ažuriraj URL
