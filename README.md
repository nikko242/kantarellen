# Kantarellen

En karta att ha med i skogen som visar var det är mest sannolikt att hitta kantareller, räknat ur öppna data om skogen och marken. Fynd markeras på kartan och sparas bara i telefonen.

Prototyp för Östersunds kommun. Idén står i [ide.md](ide.md); kunskapen om systemet (varför det är byggt så här) finns i Saida.

## Så fungerar det

- **Förberäkningen** (`kantarell/`, Python) lägger kommunen i rutor om 50 × 50 m och räknar en poäng per ruta ur trädslag, skogens ålder (trädhöjd och avverkningar), jordart, markfuktighet och höjd. Reglerna står i [kantarell/poang.py](kantarell/poang.py).
- **Webbappen** (`web/`) är statisk: MapLibre visar kartbilden, och trycker man på en ruta läses dess förklaring ur `web/data/block/`. Fynden sparas i webbläsaren (localStorage) och kan exporteras som GeoJSON.

## Kom igång

```sh
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Linux/macOS: .venv/bin/pip

.venv/Scripts/python -m kantarell.forberakna --demo   # påhittade data kring Östersund
.venv/Scripts/python -m kantarell.forberakna          # riktiga källor för Östersunds kommun

python -m http.server 8000 -d web                     # visa appen på http://localhost:8000
.venv/Scripts/python -m pytest                        # testerna
```

Mobilen ger sin position bara till sidor med https; prova positionen på GitHub Pages.

## Datakällor

Källorna, deras datum och licenser visas i appen under "Om kartan" (ur `web/data/meta.json`). Se också [docs/datakallor.md](docs/datakallor.md).

## Publicering

GitHub Actions kör testerna vid varje push och publicerar `web/` på GitHub Pages bara när de går igenom (`.github/workflows/ci.yml`). Kartdata förberäknas lokalt och checkas in i `web/data/`.
