# Ártrend-figyelő

**Élő demó:** _(ide jön a Vercel URL a deploy után)_

Napi árkövetés 15 Steam-játékra, grafikonnal és AI-generált vásárlási
verdikttel — *„most éri meg megvenni, mert 3 hete nem volt ilyen olcsó"*
típusú mondatokkal.

<!-- TODO deploy után: képernyőkép a dashboardról ide (docs/screenshot.png),
     és a fenti demó-link kitöltése. Egy kattintható demó + egy screenshot
     többet ér a repo tetején, mint bármelyik bekezdés alatta. -->

---

## A probléma

Egy 60 eurós játéknál az időzítés többet számít, mint a kiválasztás. A Steam
szezonális akciói során ugyanaz a cím lehet −20% és −80% között, és a
„−50%!" gyakran csak visszatérés egy árszinthez, ami két hete is elérhető
volt. Amit a vásárló tudni akar, az nem az aktuális ár, hanem hogy **ez az ár
jó-e a saját múltjához képest.**

Ehhez ártörténet kell — és valaki, aki egy mondatban megmondja, mit jelent.

## A megoldás

```
Steam Store API ──┐
                  ├──► Supabase / JSON ──► Next.js dashboard
Playwright        │       (idősor)         (grafikon + verdikt)
scraper ──────────┘                               │
(mock shop)                                  Claude API
                                    (statisztika → magyar mondat)
```

1. **Adatgyűjtés** — napi egyszer, címenként egy lekérés a Steam publikus
   store API-jából.
2. **Adatréteg** — Supabase (`products` + `price_snapshots`), lokális JSON
   fallbackkel, hogy a projekt fiók nélkül is végigvihető legyen.
3. **Dashboard** — Next.js + Tailwind, címenkénti ártörténet-grafikon.
4. **AI-réteg** — a Claude API az ártörténetből 1–2 mondatos verdiktet ad,
   cache-elve.

---

## Miért két adatgyűjtő ág?

Ez a projekt legtanulságosabb része, ezért nem söpröm a szőnyeg alá.

**Eredetileg egy magyar webshop fejhallgató-kategóriáját scrape-eltem
Playwrighttal.** A kód működött — a `schema.org/Product` JSON-LD blokkból
tisztán kijött az ár, a listaár és a készletállapot. Éles futásnál viszont
kiderült, hogy a bolt bot-védelme az **első** kérés után 403-mal és egy
challenge-oldallal válaszol, és ez 45 másodperces szünettel sem változik.
A másik nagy magyar shop pedig a `robots.txt`-ben tiltja a termékoldalakat.

Ezen a ponton két út van. Az egyik a védelem megkerülése — ez nem opció.
A másik: **más adatforrás, a scraper-kompetencia megtartásával.**

| Ág | Adatforrás | Mit ad | Hol fut |
|---|---|---|---|
| **Élő** | Steam Store API | valós árak a dashboardhoz | napi cron |
| **Scraper** | self-hosted mock shop | a Playwright-réteg végigpróbálása | CI, minden pusholásnál |

A mock shop (`mock-shop/generate.py`) ugyanolyan JSON-LD szerkezetű
termékoldalakat generál, mint egy valódi bolt — `@graph` több node-dal, a
Product nem az első, akciós ár `priceSpecification/StrikethroughPrice`
formában, `robots.txt`-tel és `Crawl-delay`-jel. A scraper tehát ténylegesen
végig van futtatva, csak nem valaki más szerverén.

**Amit a scraper a 403-ból tanult:** a `403`/`429` nem olyan hiba, amit
újrapróbálkozással kell legyőzni. A kód most azonnal leáll, kiírja a
`Retry-After` fejlécet, elmenti az addig összegyűjtött adatot, és külön
kilépőkóddal (`3`) jelzi, hogy nem a parse-logika romlott el.

---

## Miért nem „csak egy promptolás" az AI-réteg

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
változhat — így napi 1 lekérés mellett ez címenként **napi 1 modellhívás**,
nem oldalbetöltésenként egy. Kétszintű: process-memória + Supabase tábla.

**4. Sosem dől el rajta a dashboard.**
Kulcs nélkül, rate limit esetén vagy API-hibánál egy szabályalapú heurisztika
lép be, és a UI **kiírja, melyik forrásból jött** a szöveg. Egy demóban nem
szabad összemosni a kettőt.

---

## Etikus adatgyűjtés

- **Napi 1 lekérés címenként**, 1,5 mp szünettel. A Steam nagyságrendileg
  200 kérést enged 5 percenként — 15 kérés naponta ennek a töredéke.
- **429 esetén megvárjuk a `Retry-After`-t**, nem próbálkozunk tovább.
- **A scraper-ág `robots.txt`-et ellenőriz minden futáskor**, és betartja a
  `Crawl-delay`-t. Ha a `robots.txt` nem elérhető, leáll (`exit 2`) ahelyett,
  hogy vaktában kérne le.
- **Csak nyilvános árak**, semmilyen személyes adat.
- **Nincs bot-védelem-megkerülés.** Ha egy oldal kizár, az válasz, nem
  akadály.

---

## Stack

| Réteg | Eszköz | Miért |
|---|---|---|
| Élő adat | Python stdlib (`urllib`) | A Steam API JSON-t ad; nem kell hozzá se böngésző, se HTTP-könyvtár |
| Scraper-ág | Python + Playwright | JS-renderelt oldalakhoz; a JSON-LD kiolvasás triviális benne |
| Ütemezés | GitHub Actions cron | Nem kell szervert üzemeltetni egy napi 1 perces feladathoz |
| Adat | Supabase (Postgres) + JSON fallback | Ingyenes tier, RLS-sel publikus olvasás; a fallback miatt fiók nélkül is fut |
| Frontend | Next.js 16 (App Router) + Tailwind 4 | ISR: az adat naponta frissül, nincs értelme kérésenként újraszámolni |
| Grafikon | Recharts (termékoldal) + kézi SVG (lista) | 15 kártyához 15 chart-példány indokolatlan JS lenne interakció nélkül |
| AI | Claude API (`@anthropic-ai/sdk`) | Structured output + szerver oldali fallback |
| Hosting | Vercel | A Next.js natív célplatformja |

---

## Indítás

### 1. Élő adat lekérése

```bash
cd scraper
pip install -r requirements-api.txt   # csak supabase, vagy semmi
python fetch_steam.py --dry-run       # lekér, nem ír
python fetch_steam.py                 # éles: ír a DB-be
```

Kulcs nélkül a `web/public/data/db.json` fájlba ír. Ha be van állítva a
`SUPABASE_URL` és `SUPABASE_SERVICE_ROLE_KEY`, akkor Supabase-be.

### 2. Scraper-ág (mock shop)

```bash
cd scraper
pip install -r requirements.txt
python -m playwright install chromium
python test_extract.py && python test_steam.py   # hálózat nélkül, pár mp

python ../mock-shop/generate.py
python -m http.server 8000 --directory ../mock-shop/site &
python scrape.py --catalog products.mock.json --dry-run
```

A parse-olás (`extract.py`, `steam_extract.py`) szándékosan külön van a
hálózati rétegtől, így valódi, mentett válaszokon tesztelhető böngésző és
internet nélkül. Ez fut a CI-ban is, minden más előtt.

> **Windows-buktató:** ha a Playwright `ImportError: DLL load failed while
> importing _greenlet` hibával indul, hiányzik a Microsoft Visual C++
> Redistributable: `winget install --id Microsoft.VCRedist.2015+.x64`, majd
> új terminál. Linuxon/macOS-en és a CI-futtatón nem jelentkezik.

### 3. Adatbázis (opcionális)

[Supabase](https://supabase.com) projekt → SQL Editor → futtasd le a
[`supabase/schema.sql`](supabase/schema.sql) fájlt. Három táblát hoz létre
(`products`, `price_snapshots`, `ai_verdicts`), egy összegző nézetet, és
beállítja az RLS-t: az anon kulcs csak olvashat, írni kizárólag a
service_role kulcs tud.

### 4. Frontend

```bash
cd web
npm install
cp .env.example .env.local     # opcionális kulcsok
npm run dev
```

Kulcsok nélkül is elindul: a repóban lévő JSON pillanatképből olvas, és
szabályalapú verdiktet ad.

**Demó-adat a UI fejlesztéséhez.** Induláskor címenként 1 mérés van, amin
nincs mit grafikonozni. Ehhez:

```bash
python scraper/seed_demo.py    # 45 nap szintetikus történet
# web/.env.local:
NEXT_PUBLIC_DEMO_DATA=1
```

A generált görbe a Steam árazását utánozza (hosszú mozdulatlan szakaszok, egy
éles akció), és a **valós, ma lekért árban végződik**. Ez **nem valós adat**:
külön fájlba megy (`db.demo.json`), és a dashboard figyelmeztető sávot rak ki,
ha be van kapcsolva.

### 5. Automatizálás

| Workflow | Mikor | Mit csinál |
|---|---|---|
| [`scrape.yml`](.github/workflows/scrape.yml) | naponta 06:12 UTC | tesztek → Steam-lekérés → adat visszacommitolása |
| [`scraper-e2e.yml`](.github/workflows/scraper-e2e.yml) | scraper/mock-shop módosításakor | mock shop generálás + kiszolgálás + teljes Playwright-futás |

Repository secrets (opcionális): `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`. Ezek nélkül a napi workflow a lokális JSON-t
frissíti és visszacommitolja a repóba — ami egyben új Vercel deployt is
kivált, tehát a dashboard így is friss marad.

**Ezt érdemes legelőször beindítani.** A grafikon addig szegényes, amíg nincs
5–7 nap valós adat; ez a rész fut a háttérben, amíg a frontenden dolgozol.

### 6. Deploy

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
  games.json          figyelt Steam-címek (slug, appid, név)
  steam_extract.py    tiszta parse-logika a Steam API válaszához
  fetch_steam.py      napi lekérés: HTTP + retry + 429-kezelés
  extract.py          tiszta parse-logika weboldalhoz (JSON-LD + DOM fallback)
  scrape.py           Playwright-vezérlés: robots.txt, retry, 403-kezelés
  store.py            adatréteg: Supabase VAGY lokális JSON, azonos felülettel
  test_extract.py     43 assertion mentett JSON-LD fixture-ökön
  test_steam.py       a Steam-válasz feldolgozásának tesztjei
  seed_demo.py        szintetikus történet a UI fejlesztéséhez
mock-shop/
  generate.py         statikus termékoldalak a scraper célpontjául
supabase/
  schema.sql          táblák, nézet, RLS
web/
  lib/stats.ts        ártörténet → tények (min/max, trend, "x napja")
  lib/verdict.ts      Claude-hívás, cache, heurisztikus fallback
  lib/data.ts         Supabase / lokális JSON / demó forrásválasztás
  lib/format.ts       valutafüggő pénzformázás (EUR cent, HUF forint)
  components/         Sparkline (SVG), PriceChart (recharts), VerdictCard
  app/                dashboard, termékoldal, /api/verdict
```

## API

```bash
curl "https://<demo-url>/api/verdict?slug=cyberpunk-2077"
```

```json
{
  "slug": "cyberpunk-2077",
  "verdict": { "trend": "csokkeno", "headline": "30 napos mélyponton", "verdict": "…", "source": "claude" },
  "stats": { "current": 1799, "min30": 1799, "daysSinceCheaper": 21, "…": "…" }
}
```

Az árak a valuta legkisebb egységében jönnek (EUR-nál cent) — a formázás a
kliens dolga, `lib/format.ts` mintájára.

---

## Mit tanultam belőle

- **A scraping-célpont választása nem technikai kérdés.** A kódom működött;
  a projekt mégis elakadt, mert a bolt jogosan nem akar automatizált
  forgalmat. Az „ez menni fog, csak elég ügyes legyek" hozzáállás rossz
  mérnöki válasz — a jó válasz az adatforrás cseréje volt.
- **A JSON-LD a jobb scraping-célpont**, ha egyáltalán scrape-elsz. A
  `schema.org/Product` blokk stabilabb, mint bármelyik CSS-osztály, és
  strukturáltan adja az áthúzott árat és a készletállapotot is.
- **A parse-olást érdemes szétválasztani a hálózattól.** Amíg a kiolvasás a
  Playwright `page` objektumon ült, csak élő futással lehetett tesztelni.
  Külön modulban a bemenet egy string-lista — így valódi mentett válaszon fut
  a teszt, másodpercek alatt.
- **Az idempotencia a cronban nem opcionális.** A `(product_id, captured_on)`
  unique kulcs miatt egy kézi újrafuttatás nem duplikál — enélkül a
  „gyorsan nézzük meg, működik-e" pillanat elrontja az idősort.
- **AI-t termékbe építeni főleg határolás.** A nehéz rész nem a prompt, hanem
  eldönteni, mit *ne* bízzunk a modellre (számolás), és mi történjen, ha nem
  válaszol (heurisztika, látható forrásjelöléssel).
- **A statisztika és az emberi jelentés nem ugyanaz.** A „most a 30 napos
  minimumon van" triviálisan igaz egy soha nem mozduló árra — a kódnak külön
  kell kezelnie a „nem volt akció" esetet, különben magabiztosan mond
  semmitmondót.
