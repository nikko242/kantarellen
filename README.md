# Kantarellen

En karta att ha med i skogen som visar var det är mest sannolikt att hitta kantareller, räknat ur öppna data om skogen och marken. Fynd markeras på kartan och sparas bara i telefonen.

Prototyp för Jämtlands län (varv 1 gällde Östersunds kommun). Idén står i [ide.md](ide.md); kunskapen om systemet (varför det är byggt så här) finns i Saida.

## Så fungerar det

- **Förberäkningen** (`kantarell/`, Python) lägger länet i rutor om 50 × 50 m (omkring 40 miljoner rutor) och räknar en poäng per ruta ur trädslag, skogens ålder (trädhöjd och avverkningar), jordart, markfuktighet och höjd. Reglerna står i [kantarell/poang.py](kantarell/poang.py). Tätorter räknas inte som skog (bebyggd mark enligt NMD).
- **Webbappen** (`web/`) är statisk: MapLibre visar kartan som tiles (`web/data/tiles/`, zoom 5–11), och trycker man på en ruta läses dess förklaring ur de gzip-komprimerade blocken i `web/data/block/`. Fynden sparas i webbläsaren (localStorage) och kan exporteras som GeoJSON.

## Kom igång

```sh
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Linux/macOS: .venv/bin/pip

.venv/Scripts/python -m kantarell.forberakna --demo   # påhittade data kring Östersund
.venv/Scripts/python -m kantarell.forberakna          # riktiga källor för Jämtlands län (ungefär en timme första gången)

python -m http.server 8000 -d web                     # visa appen på http://localhost:8000
.venv/Scripts/python -m pytest                        # testerna
```

Mobilen ger sin position bara till sidor med https; prova positionen på GitHub Pages.

Tre källor finns bara som stora nedladdningar och läggs i `data/raw/dl/` (packas upp automatiskt): NMD 2023 (`NMD2023_basskikt_v2_1.zip`, 2,5 GB), SGU:s jordarter (`jordarter25k-100k.zip`, 3,4 GB) och markfuktigheten för Jämtland i `data/raw/markfuktighet/`. Adresserna står i [docs/datakallor.md](docs/datakallor.md).

## Datakällor

Källorna, deras datum och licenser visas i appen under "Om kartan" (ur `web/data/meta.json`). Se också [docs/datakallor.md](docs/datakallor.md).

## Publicering

GitHub Actions kör testerna vid varje push och publicerar `web/` på GitHub Pages bara när de går igenom (`.github/workflows/ci.yml`).

Kartdatan förberäknas lokalt och ligger inte i main, utan på grenen `kartdata` som en enda commit utan historik (ett län är flera hundra MB och byts vid varje omräkning). CI hämtar den när Pages byggs:

```sh
.venv/Scripts/python -m kantarell.publicera     # web/data → grenen kartdata
git push -f origin kartdata
gh workflow run ci.yml --ref main               # publicera om Pages
```
