# Ártrend-figyelő

**Élő demó:** _(ide jön a Vercel URL a deploy után)_

Napi árkövetés 15 fejhallgatóra egyetlen webshopból, grafikonnal és
AI-generált vásárlási verdikttel — *„most éri meg venni, mert 3 hete nem volt
ilyen olcsó"* típusú mondatokkal.

<!-- TODO deploy után: képernyőkép a dashboardról ide (docs/screenshot.png),
     és a fenti demó-link kitöltése. Egy kattintható demó + egy screenshot
     többet ér a repo tetején, mint bármelyik bekezdés alatta. -->


---

## A probléma

Egy 130 000 Ft-os fejhallgatónál az időzítés több pénzt számít, mint a
kiválasztás. Az árak hetente mozognak, az akciók pedig ritkán annyira jók, mint
amennyire annak látszanak: az „–10%" gyakran csak visszatérés az egy héttel
korábbi árszintre. Amit a vásárló tudni akar, az nem az aktuális ár, hanem
hogy **ez az ár jó-e a saját múltjához képest.**

Ehhez ártörténet kell — és valaki, aki egy mondatban megmondja, mit jelent.

## A megoldás

```
Playwright scraper ──► Supabase / JSON ──► Next.js dashboard
   (napi 1×, cron)        (idősor)          (grafikon + verdikt)
                                                    │
                                              Claude API
                                        (statisztika → magyar mondat)
```

1. **Scraper** — Playwright, napi egyszer, 15 termékoldalról olvassa ki az árat.
2. **Adatréteg** — Supabase (`products` + `price_snapshots`), lokális JSON
   fallbackkel, hogy a projekt fiók nélkül is végigvihető legyen.
3. **Dashboard** — Next.js + Tailwind, termékenkénti ártörténet-grafikon.
4. **AI-réteg** — a Claude API az ártörténetből 1–2 mondatos verdiktet ad,
   cache-elve.

---

## Miért nem „csak egy promptolás" az AI-réteg

Ez a projekt megkülönböztető része, ezért érdemes kifejteni. Három döntés:

**1. A modell nem lát nyers idősort.**
A statisztikát (30 napos min/átlag/max, „hány napja nem volt ilyen olcsó",
trend) determinisztikus TypeScript kód számolja
([`lib/stats.ts`](web/lib/stats.ts)), és a modell **kész tényeket** kap. Így
nem tud számot félrehallucinálni — a legrosszabb, ami történhet, hogy a
megfogalmazás gyenge, nem az, hogy hamis árat állít.

**2. Structured output.**
A válasz JSON sémára van kényszerítve (`output_config.format`), így nincs
szükség szövegparszolásra, és a `headline` / `verdict` / `trend` mezők mindig
megvannak.

**3. Tartalommal kulcsolt cache.**
A cache kulcsa az ártörténet SHA-256 ujjlenyomata
([`lib/verdict.ts`](web/lib/verdict.ts)). Ha nem jött új mérés, a verdikt sem
változhat — így napi 1 scrape mellett ez termékenként **napi 1 modellhívás**,
nem oldalbetöltésenként egy. Kétszintű: process-memória + Supabase tábla.

**4. Sosem dől el rajta a dashboard.**
Kulcs nélkül, rate limit esetén vagy API-hibánál egy szabályalapú heurisztika
lép be, és a UI **kiírja, melyik forrásból jött** a szöveg. Egy demóban nem
szabad összemosni a kettőt.

---

## Etikus scraping

A scraping jogilag és etikailag kényes, ezért a projekt szándékosan kicsi:

- **1 webshop, 1 kategória, 15 termék** — nem tömeges adatgyűjtés.
- **Napi 1 lekérés termékenként**, 2–4 mp szünettel: nagyjából annyi forgalom,
  mint egy emberé, aki végignézi a kategóriát.
- **robots.txt ellenőrzés minden futáskor.** Ha nem elérhető, a scraper leáll
  (`exit 2`) ahelyett, hogy vaktában kérne le. A tiltott URL-eket kihagyja.
- **Csak nyilvános árak**, semmilyen személyes adat.
- **A képek/fontok blokkolva** a scraper böngészőjében — kevesebb sávszélesség
  az ő oldalukon is.
- **JSON-LD elsődlegesen.** Az árat a termékoldal `schema.org/Product` blokkjából
  olvassuk — ez az az adat, amit a webshop maga tesz ki a keresőknek. Stabilabb
  is, mint a CSS-osztályokra vadászni.

---

## Stack

| Réteg | Eszköz | Miért |
|---|---|---|
| Scraper | Python + Playwright | JS-renderelt oldalakat is kezel; a JSON-LD kiolvasás triviális benne |
| Ütemezés | GitHub Actions cron | Nem kell szervert üzemeltetni egy napi 1 perces feladathoz |
| Adat | Supabase (Postgres) + JSON fallback | Ingyenes tier, RLS-sel publikus olvasás; a fallback miatt fiók nélkül is fut |
| Frontend | Next.js 16 (App Router) + Tailwind 4 | ISR: az adat naponta frissül, nincs értelme kérésenként újraszámolni |
| Grafikon | Recharts (termékoldal) + kézi SVG (lista) | 15 kártyához 15 chart-példány indokolatlan JS lenne interakció nélkül |
| AI | Claude API (`@anthropic-ai/sdk`) | Structured output + szerver oldali fallback |
| Hosting | Vercel | A Next.js natív célplatformja |

---

## Indítás

### 1. Scraper

```bash
cd scraper
python -m venv .venv && .venv/Scripts/activate   # Windows; Linux/mac: source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python scrape.py --limit 3 --dry-run             # füstteszt: kiolvas, nem ír
python scrape.py                                 # éles futás
```

Kulcs nélkül a `web/public/data/db.json` fájlba ír. Ha be van állítva a
`SUPABASE_URL` és `SUPABASE_SERVICE_ROLE_KEY`, akkor Supabase-be.

> **Windows-buktató:** ha a Playwright `ImportError: DLL load failed while
> importing _greenlet` hibával indul, hiányzik a Microsoft Visual C++
> Redistributable. Telepítés: `winget install --id Microsoft.VCRedist.2015+.x64`
> (rendszergazdaként), majd új terminál. Linuxon/macOS-en és a GitHub Actions
> futtatón nem jelentkezik.

### 2. Adatbázis (opcionális)

[Supabase](https://supabase.com) projekt → SQL Editor → futtasd le a
[`supabase/schema.sql`](supabase/schema.sql) fájlt. Három táblát hoz létre
(`products`, `price_snapshots`, `ai_verdicts`), egy összegző nézetet, és
beállítja az RLS-t: az anon kulcs csak olvashat, írni kizárólag a
service_role kulcs tud.

### 3. Frontend

```bash
cd web
npm install
cp .env.example .env.local     # opcionális kulcsok
npm run dev
```

Kulcsok nélkül is elindul: a repóban lévő JSON pillanatképből olvas, és
szabályalapú verdiktet ad.

**Demó-adat a UI fejlesztéséhez.** Induláskor termékenként 1 mérés van, amin
nincs mit grafikonozni. Ehhez:

```bash
python scraper/seed_demo.py        # 45 nap szintetikus történet
# web/.env.local:
NEXT_PUBLIC_DEMO_DATA=1
```

Ez **nem valós adat**, külön fájlba megy (`db.demo.json`), és a dashboard
figyelmeztető sávot rak ki, ha be van kapcsolva.

### 4. Automatizálás

A [`.github/workflows/scrape.yml`](.github/workflows/scrape.yml) naponta
06:12 UTC-kor fut. Repository secrets (opcionális):
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`. Ezek nélkül a workflow a lokális
JSON-t frissíti és visszacommitolja a repóba — ami egyben új Vercel deployt is
kivált, tehát a dashboard így is friss marad.

**Ezt érdemes legelőször beindítani.** A grafikon addig üres, amíg nincs
5–7 nap valós adat; ez a rész fut a háttérben, amíg a frontenden dolgozol.

### 5. Deploy

Vercel → Import repo → **Root Directory: `web`**. Környezeti változók:

| Változó | Kell? |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` | csak Supabase módban |
| `SUPABASE_SERVICE_ROLE_KEY` | csak a verdikt-cache írásához |
| `ANTHROPIC_API_KEY` | AI-verdikthez; enélkül szabályalapú |
| `ANTHROPIC_MODEL` | opcionális, alap: `claude-opus-5` |

> **Költség.** Alapértelmezésben `claude-opus-5` fut. A cache miatt ez napi
> ~15 rövid hívás, de egy publikus demóhoz a `claude-haiku-4-5` bőven elég
> ehhez a feladathoz (kész tények → egy mondat), és nagyságrenddel olcsóbb —
> egyetlen env-változó.

---

## Projektstruktúra

```
scraper/
  products.json      figyelt termékek (slug, név, URL)
  scrape.py          Playwright scraper, JSON-LD kiolvasással
  store.py           adatréteg: Supabase VAGY lokális JSON, azonos felülettel
  seed_demo.py       szintetikus történet a UI fejlesztéséhez
supabase/
  schema.sql         táblák, nézet, RLS
web/
  lib/stats.ts       ártörténet → tények (min/max, trend, "x napja")
  lib/verdict.ts     Claude-hívás, cache, heurisztikus fallback
  lib/data.ts        Supabase / lokális JSON / demó forrásválasztás
  components/        Sparkline (SVG), PriceChart (recharts), VerdictCard
  app/               dashboard, termékoldal, /api/verdict
.github/workflows/
  scrape.yml         napi cron
```

## API

```bash
curl "https://<demo-url>/api/verdict?slug=sony-wh-1000xm6-fekete"
```

```json
{
  "slug": "sony-wh-1000xm6-fekete",
  "verdict": { "trend": "csokkeno", "headline": "Jó belépő", "verdict": "…", "source": "claude" },
  "stats": { "current": 134990, "min30": 126990, "daysSinceCheaper": 21, "…": "…" }
}
```

---

## Mit tanultam belőle

- **A JSON-LD a jobb scraping-célpont.** A `schema.org/Product` blokk stabilabb,
  mint bármelyik CSS-osztály, és strukturáltan adja az áthúzott árat és a
  készletállapotot is. A CSS-selector csak fallback.
- **Az idempotencia a cronban nem opcionális.** A `(product_id, captured_on)`
  unique kulcs miatt egy kézi újrafuttatás nem duplikál — enélkül a
  „gyorsan nézzük meg, működik-e" pillanat elrontja az idősort.
- **AI-t termékbe építeni főleg határolás.** A nehéz rész nem a prompt, hanem
  eldönteni, mit *ne* bízzunk a modellre (számolás), és mi történjen, ha nem
  válaszol (heurisztika, látható forrásjelöléssel).
- **Cache-kulcsnak a tartalom hash-e való**, nem az idő. Így nem lehet
  „elavult, de még friss" verdikt, és a hívásszám az adat változásához kötött.
- **A demó üressége terméktervezési kérdés.** Napi 1 mérés mellett az első hét
  grafikonjai szükségszerűen szegényesek — ezt vagy kezeli a UI (üres állapotok,
  „gyűlik az adat"), vagy rosszul néz ki a bemutatón.
