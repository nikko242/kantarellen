"""Kontroll av poängen mot rapporterade kantarellfynd i Artportalen (via GBIF, CC0).

  python -m kantarell.kontroll

Jämför poängen i rutorna med fynd mot poängen i alla skogsrutor. Fynden är få och skeva (de rapporteras där folk går),
så kontrollen visar en riktning, inte en träffsäkerhet.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import requests

from .forberakna import WEB
from .rutnat import BLOCK, FALT, SAKNAS

log = logging.getLogger("kantarell.kontroll")
GBIF = "https://api.gbif.org/v1/occurrence/search"
KANTARELL = 5249504
ARTPORTALEN = "38b4c89f-584c-41bb-bd8f-cd1def33e92f"


def fynd(lon0, lat0, lon1, lat1) -> list[tuple[float, float, int | None]]:
    ut, offset = [], 0
    poly = f"POLYGON(({lon0} {lat0},{lon1} {lat0},{lon1} {lat1},{lon0} {lat1},{lon0} {lat0}))"
    while True:
        r = requests.get(GBIF, timeout=60, params={"taxonKey": KANTARELL, "datasetKey": ARTPORTALEN, "geometry": poly,
                                                   "hasCoordinate": "true", "limit": 300, "offset": offset})
        r.raise_for_status()
        d = r.json()
        ut += [(o["decimalLongitude"], o["decimalLatitude"], o.get("year")) for o in d["results"]]
        if d.get("endOfRecords", True):
            return ut
        offset += 300


def poang_vid(meta: dict, x: float, y: float, cache: dict) -> float | None:
    n = meta["rutnat"]
    kol, rad = int((x - n["x0"]) // n["ruta_m"]), int((n["y0"] - y) // n["ruta_m"])
    if not (0 <= kol < n["bredd"] and 0 <= rad < n["hojd"]):
        return None
    nyckel = f"{kol // BLOCK}_{rad // BLOCK}"
    if nyckel not in cache:
        p = WEB / "block" / f"{nyckel}.bin"
        cache[nyckel] = p.read_bytes() if p.exists() else None
    b = cache[nyckel]
    if b is None:
        return None
    v = b[((rad % BLOCK) * BLOCK + kol % BLOCK) * len(FALT)]
    return None if v == SAKNAS else v / 250


def alla_poang(meta: dict) -> np.ndarray:
    v = []
    for p in (WEB / "block").glob("*.bin"):
        a = np.frombuffer(p.read_bytes(), dtype=np.uint8).reshape(-1, len(FALT))[:, 0]
        v.append(a[a != SAKNAS] / 250)
    return np.concatenate(v)


def main() -> None:
    from pyproj import Transformer
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    meta = json.loads((WEB / "meta.json").read_text(encoding="utf-8"))
    h = meta["bild"]["hornen"]
    lista = fynd(h[0][0], h[2][1], h[1][0], h[0][1])
    t = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True)
    cache: dict = {}
    vid = [p for lon, lat, _ in lista if (p := poang_vid(meta, *t.transform(lon, lat), cache)) is not None]
    alla = alla_poang(meta)
    print(f"Fynd i kartans område: {len(lista)}, varav {len(vid)} i en skogsruta.")
    if vid:
        hog = float(np.quantile(alla, 0.7))
        print(f"Medelpoäng: fynden {np.mean(vid):.2f}, alla skogsrutor {alla.mean():.2f}.")
        print(f"Andel fynd i de 30 % bästa rutorna: {np.mean(np.array(vid) >= hog):.0%} (slumpen ger 30 %).")
    print("Få fynd ger en osäker kontroll; se det som en riktning.")


if __name__ == "__main__":
    main()
