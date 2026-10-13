"""Förberäkningen: källornas data på rutnätet → poäng per ruta → kartbild och block för webbappen.

  python -m kantarell.forberakna --demo        påhittade data för ett område kring Östersund (för att pröva appen)
  python -m kantarell.forberakna               riktiga källor för Östersunds kommun (se kantarell/kallor.py)

Resultatet hamnar i web/data: poang.png (kartbilden i Web Mercator), block/<bx>_<by>.bin och meta.json
(rutnätet, källorna med datum och licens, och statistik).
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np

from .poang import Ruta, bedom
from .rutnat import BLOCK, RUTA_M, Rutnat, koda_block

log = logging.getLogger("kantarell")
WEB = Path(__file__).resolve().parent.parent / "web" / "data"
KALLFALT = ["gran", "tall", "bjork", "tradhojd", "ar_sedan_avverkning", "jordart", "fukt", "hojd"]


def berakna(nat: Rutnat, data: dict[str, np.ndarray], innanfor: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Poäng och faktorer för varje ruta. data har källfälten som float-arrayer på rutnätet (NaN = saknas)."""
    shape = (nat.hojd, nat.bredd)
    ut = {f: np.full(shape, np.nan) for f in ["poang", "f_tradslag", "f_alder", "f_jordart", "f_fukt", "f_hojd"]}
    for f in KALLFALT:
        ut[f] = data.get(f, np.full(shape, np.nan)).astype(float)
    val = lambda f, i, j: None if np.isnan(ut[f][i, j]) else float(ut[f][i, j])
    rutor = np.argwhere(innanfor) if innanfor is not None else np.argwhere(np.ones(shape, bool))
    for i, j in rutor:
        r = Ruta(gran=val("gran", i, j), tall=val("tall", i, j), bjork=val("bjork", i, j), tradhojd=val("tradhojd", i, j),
                 ar_sedan_avverkning=None if np.isnan(ut["ar_sedan_avverkning"][i, j]) else int(ut["ar_sedan_avverkning"][i, j]),
                 jordart=None if np.isnan(ut["jordart"][i, j]) else int(ut["jordart"][i, j]),
                 fukt=None if np.isnan(ut["fukt"][i, j]) else int(ut["fukt"][i, j]), hojd=val("hojd", i, j))
        b = bedom(r)
        if b.poang is not None:
            ut["poang"][i, j] = b.poang
        for k, v in b.faktorer.items():
            if v is not None:
                ut[f"f_{k}"][i, j] = v
    if innanfor is not None:
        for f in ut:
            ut[f][~innanfor] = np.nan
    return ut


FARGER = [(0.0, (120, 120, 120, 70)), (0.4, (170, 160, 110, 130)), (0.7, (230, 170, 30, 190)), (1.0, (255, 196, 0, 230))]


def farg(poang: np.ndarray) -> np.ndarray:
    """Poäng till RGBA: grått (osannolikt) till guld (mest sannolikt); genomskinligt där det inte är skog."""
    rgba = np.zeros(poang.shape + (4,), dtype=np.uint8)
    ok = ~np.isnan(poang)
    xs = [p for p, _ in FARGER]
    for k in range(4):
        rgba[..., k][ok] = np.interp(poang[ok], xs, [c[k] for _, c in FARGER]).astype(np.uint8)
    return rgba


def skriv(nat: Rutnat, ut: dict[str, np.ndarray], kallor: list[dict], ut_dir: Path = WEB) -> dict:
    import warnings

    import rasterio
    from rasterio.errors import NotGeoreferencedWarning
    from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds

    (ut_dir / "block").mkdir(parents=True, exist_ok=True)
    for gammal in (ut_dir / "block").glob("*.bin"):
        gammal.unlink()
    antal = 0
    for bx, by, r0, k0, nr, nk in nat.block():
        falt = {f: ut[f][r0:r0 + nr, k0:k0 + nk] for f in ut}
        if np.all(np.isnan(falt["poang"])):
            continue
        # Kanterna fylls ut till hela block, så att webbappen alltid räknar med 100 × 100
        fullt = {f: np.pad(v, ((0, BLOCK - nr), (0, BLOCK - nk)), constant_values=np.nan) for f, v in falt.items()}
        (ut_dir / "block" / f"{bx}_{by}.bin").write_bytes(koda_block(fullt))
        antal += 1

    # Kartbilden: RGBA i EPSG:3006, omprojicerad till Web Mercator för MapLibre
    rgba = farg(ut["poang"]).transpose(2, 0, 1)
    dst_t, w, h = calculate_default_transform("EPSG:3006", "EPSG:3857", nat.bredd, nat.hojd, *nat.bounds)
    dst = np.zeros((4, h, w), dtype=np.uint8)
    for k in range(4):
        reproject(rgba[k], dst[k], src_transform=nat.transform, src_crs="EPSG:3006", dst_transform=dst_t, dst_crs="EPSG:3857",
                  resampling=Resampling.nearest)
    warnings.simplefilter("ignore", NotGeoreferencedWarning)   # PNG:en är georefererad via meta.json
    with rasterio.open(ut_dir / "poang.png", "w", driver="PNG", width=w, height=h, count=4, dtype="uint8") as png:
        png.write(dst)
    for extra in ut_dir.glob("poang.png.aux.xml"):
        extra.unlink()
    west, north = dst_t * (0, 0)
    east, south = dst_t * (w, h)
    lon0, lat0, lon1, lat1 = transform_bounds("EPSG:3857", "EPSG:4326", west, south, east, north)
    poang = ut["poang"][~np.isnan(ut["poang"])]
    meta = {
        "skapad": time.strftime("%Y-%m-%d %H:%M"),
        "rutnat": {"crs": "EPSG:3006", "x0": nat.x0, "y0": nat.y0, "bredd": nat.bredd, "hojd": nat.hojd, "ruta_m": RUTA_M, "block": BLOCK},
        "bild": {"fil": "poang.png", "hornen": [[lon0, lat1], [lon1, lat1], [lon1, lat0], [lon0, lat0]]},
        "kallor": kallor,
        "statistik": {"skogsrutor": int(poang.size), "block": antal,
                      "andel_hog": round(float((poang >= 0.7).mean()), 3) if poang.size else 0},
    }
    (ut_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def demodata(nat: Rutnat, seed: int = 7) -> dict[str, np.ndarray]:
    """Påhittade men sammanhängande data (mjuka fält), för att pröva appen utan riktiga källor."""
    rng = np.random.default_rng(seed)
    shape = (nat.hojd, nat.bredd)

    def falt(skala: int) -> np.ndarray:
        grov = rng.random((shape[0] // skala + 2, shape[1] // skala + 2))
        return np.kron(grov, np.ones((skala, skala)))[: shape[0], : shape[1]]

    barr = falt(8)
    gran = 40 + 50 * barr
    tall = 10 + 30 * (1 - barr)
    bjork = 30 * falt(6)
    tradhojd = 3 + 20 * falt(5)
    avverk = np.where(falt(10) < 0.12, np.round(25 * falt(3)), np.nan)
    tradhojd = np.where(~np.isnan(avverk) & (avverk < 10), 1 + 3 * falt(2), tradhojd)
    jord = np.select([falt(12) < 0.6, falt(12) < 0.75, falt(12) < 0.85], [1, 2, 6], 5).astype(float)
    fukt = np.clip(np.round(1 + 3 * falt(7)), 1, 4)
    hojd = 300 + 450 * falt(20)
    vatten = falt(15) < 0.08
    data = {"gran": gran, "tall": tall, "bjork": bjork, "tradhojd": tradhojd, "ar_sedan_avverkning": avverk,
            "jordart": jord, "fukt": fukt, "hojd": hojd}
    for f in ("gran", "tall", "bjork"):
        data[f] = np.where(vatten, np.nan, data[f])
    return data


DEMO_KALLOR = [{"namn": "Påhittade demodata", "vad": "alla faktorer", "datum": time.strftime("%Y-%m-%d"),
                "licens": "–", "url": "", "not": "Bara för att pröva appen; säger ingenting om verkliga kantareller."}]


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Förberäkna sannolikhetskartan för kantareller")
    p.add_argument("--demo", action="store_true", help="påhittade data för ett område om 10 × 10 km kring Östersund")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    t0 = time.time()
    if a.demo:
        nat = Rutnat.kring(476000, 7002000, 486000, 7012000)
        log.info("Demo: %d × %d rutor om %d m", nat.bredd, nat.hojd, RUTA_M)
        data, kallor, innanfor = demodata(nat), DEMO_KALLOR, None
    else:
        from .kallor import hamta
        nat, data, kallor, innanfor = hamta()
    for f in KALLFALT:
        if f == "ar_sedan_avverkning":   # saknas = ingen känd avverkning, inte en lucka
            continue
        saknas = float(np.isnan(data[f]).mean()) if f in data else 1.0
        (log.warning if saknas > 0.5 else log.info)("%s: data saknas för %.0f %% av rutorna", f, 100 * saknas)
    ut = berakna(nat, data, innanfor)
    meta = skriv(nat, ut, kallor)
    log.info("Klart på %.1f s: %d skogsrutor, %d block, %.0f %% med hög sannolikhet", time.time() - t0,
             meta["statistik"]["skogsrutor"], meta["statistik"]["block"], 100 * meta["statistik"]["andel_hog"])


if __name__ == "__main__":
    main()
