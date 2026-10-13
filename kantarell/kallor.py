"""De öppna källorna för Jämtlands län, lagda på rutnätet om 50 m (se docs/datakallor.md).

Varje källa hämtas en gång och sparas i data/raw (checkas inte in). Rasterkällor på servrar läses direkt för länets yta
(GDAL /vsicurl/), i band och parallellt; stora filer som bara finns som nedladdning (markfuktigheten, NMD, SGU:s
jordarter) läses lokalt. Vektorkällor rastreras. Resultatet per källa sparas som data/raw/lan23/rutnat_<namn>.npy.
"""
from __future__ import annotations

import json
import logging
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests

from .rutnat import RUTA_M, Rutnat

log = logging.getLogger("kantarell.kallor")
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
OMRADE = "Jämtlands län"
LANNR = "23"
OSM_RELATION = 52826
CACHE = RAW / f"lan{LANNR}"
# GDAL läser bara de delar av fjärrfilerna som behövs
GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif", "GDAL_HTTP_MULTIRANGE": "YES",
            "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES", "VSI_CACHE": "TRUE", "VSI_CACHE_SIZE": "200000000",
            "GDAL_HTTP_MAX_RETRY": "5", "GDAL_HTTP_RETRY_DELAY": "3"}
IDAG = time.strftime("%Y-%m-%d")
BAND = 500   # rader i rutnätet per band när stora raster läses (25 km)

KALLOR = {
    "gransen": {"namn": "Länsgränsen (OpenStreetMap)", "vad": "länets yta", "licens": "ODbL, © OpenStreetMap contributors",
                "url": f"https://www.openstreetmap.org/relation/{OSM_RELATION}"},
    "tradslag": {"namn": "SLU Skogskarta, trädslag", "vad": "gran, tall och björk (andel av volymen, 12,5 m)", "licens": "öppet och fritt (SLU), ange källan",
                 "url": "https://gis.slu.se/data/slu_forest_map/2018/data/"},
    "tradhojd": {"namn": "SLU Skogliga grunddata, medelhöjd (SGD2)", "vad": "trädhöjd, 10 m", "licens": "öppet och fritt (SLU), ange källan",
                 "url": "https://gis.slu.se/data/slu_skogliga_grunddata/SGD2/data/SGD2_HGV.tif"},
    "avverkning": {"namn": "Skogsstyrelsen, utförda avverkningar", "vad": "avverkade ytor med datum", "licens": "CC0",
                   "url": "https://geodpags.skogsstyrelsen.se/arcgis/rest/services/Geodataportal/GeodataportalVisaUtfordavverkning/MapServer/1"},
    "fukt": {"namn": "SLU markfuktighetskarta, klassad (Skogsstyrelsen)", "vad": "markfuktighet, 2 m (klasserna tolkade: torr–frisk, frisk–fuktig, blöt, vatten)", "licens": "CC0",
             "url": "https://geodpags.skogsstyrelsen.se/geodataport/data/sksSLUMarkfuktighet_klassad23.zip"},
    "jordart": {"namn": "SGU jordarter 1:25 000–1:100 000", "vad": "jordart", "licens": "CC0",
                "url": "https://resource.sgu.se/data/oppnadata/jordarter25k-100k/jordarter25k-100k.zip"},
    "hojd": {"namn": "Copernicus DEM GLO-30", "vad": "höjd över havet, 30 m (ytmodell)",
             "licens": "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA",
             "url": "https://copernicus-dem-30m.s3.amazonaws.com/"},
    "nmd": {"namn": "Nationella marktäckedata 2023 (NMD, Naturvårdsverket)", "vad": "bebyggd mark, 10 m (för att skilja ut tätorter)", "licens": "CC0, NMD, Naturvårdsverket",
            "url": "https://geodata.naturvardsverket.se/nedladdning/marktacke/NMD2023/Basskikt_v2_x/NMD2023_basskikt_v2_1.zip"},
}


def _cache(namn: str, nat: Rutnat, hamta) -> np.ndarray:
    p = CACHE / f"rutnat_{namn}.npy"
    if p.exists():
        a = np.load(p)
        if a.shape == (nat.hojd, nat.bredd):
            log.info("%s: från cachen", namn)
            return a
    t0 = time.time()
    a = hamta().astype(np.float32)
    np.save(p, a)
    log.info("%s: hämtad på %.0f s (%.0f %% av rutorna har värde)", namn, time.time() - t0, 100 * float((~np.isnan(a)).mean()))
    return a


def _band(nat: Rutnat, rader: int = BAND):
    """Rutnätet i band: (rad0, rader, delnät)."""
    for r0 in range(0, nat.hojd, rader):
        n = min(rader, nat.hojd - r0)
        yield r0, n, Rutnat(nat.x0, nat.y0 - r0 * RUTA_M, nat.bredd, n)


def _las_band(url_or_path: str, del_: Rutnat, resampling, src_nodata) -> np.ndarray:
    import rasterio
    from rasterio.vrt import WarpedVRT

    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(url_or_path) as src:
            nodata = src_nodata if src_nodata is not None else src.nodata
            with WarpedVRT(src, crs="EPSG:3006", transform=del_.transform, width=del_.bredd, height=del_.hojd,
                           resampling=resampling, src_nodata=nodata, nodata=np.nan, dtype="float32") as vrt:
                return vrt.read(1)


def _raster(url_or_path: str, nat: Rutnat, resampling, src_nodata=None, tradar: int = 8) -> np.ndarray:
    """En rasterkälla omsamplad till rutnätet, i band och parallellt (bara länets del läses)."""
    ut = np.full((nat.hojd, nat.bredd), np.nan, dtype=np.float32)
    band = list(_band(nat))
    with ThreadPoolExecutor(tradar) as ex:
        for (r0, n, _), a in zip(band, ex.map(lambda b: _las_band(url_or_path, b[2], resampling, src_nodata), band)):
            ut[r0:r0 + n] = a
            log.debug("%s: rad %d–%d", url_or_path.rsplit("/", 1)[-1], r0, r0 + n)
    return ut


def _get(url: str, params: dict, forsok: int = 4) -> dict:
    """GET med omförsök (de öppna tjänsterna svarar ibland 500 vid last)."""
    for n in range(forsok):
        try:
            r = requests.get(url, params=params, timeout=180)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if n == forsok - 1:
                raise
            log.warning("%s: %s; försöker igen", url, e)
            time.sleep(5 * (n + 1))
    raise RuntimeError("oåtkomligt")


def _rastrera(geoms_varden, nat: Rutnat, fyll=np.nan) -> np.ndarray:
    from rasterio.features import rasterize
    ut = rasterize(((g, v) for g, v in geoms_varden), out_shape=(nat.hojd, nat.bredd), transform=nat.transform,
                   fill=-9999, dtype="float32")
    ut[ut == -9999] = fyll
    return ut


def _packa_upp(zip_namn: str, filandelse: str) -> Path:
    """Den första filen med ändelsen ur en nedladdad zip i data/raw/dl (packas upp en gång)."""
    z = RAW / "dl" / zip_namn
    mal = RAW / "dl" / z.stem
    if not mal.exists() or not any(mal.rglob(f"*{filandelse}")):
        if not z.exists():
            raise FileNotFoundError(f"{z} saknas: ladda ner den (se docs/datakallor.md)")
        with zipfile.ZipFile(z) as zf:
            fil = next(n for n in zf.namelist() if n.endswith(filandelse))
            # Bara filen och dess sidofiler (t.ex. .tif.vat.dbf), inte resten av paketet
            delar = [n for n in zf.namelist() if n.startswith(fil.rsplit(".", 1)[0] + ".")]
            log.info("packar upp %s ur %s", ", ".join(d.rsplit("/", 1)[-1] for d in delar), z.name)
            zf.extractall(mal, members=delar)
    return next(mal.rglob(f"*{filandelse}"))


def _innanfor_bild(src, nat: Rutnat, upplosning: float):
    """Fönstret i en lokal rasterfil (samma CRS, kanter på jämna meter) som motsvarar rutnätet."""
    from rasterio.windows import Window
    col0 = round((nat.x0 - src.bounds.left) / upplosning)
    row0 = round((src.bounds.top - nat.y0) / upplosning)
    steg = round(RUTA_M / upplosning)
    return Window(col0, row0, nat.bredd * steg, nat.hojd * steg), steg


# ---------- Källorna ----------

def gransen():
    import geopandas as gpd
    p = CACHE / "gransen.geojson"
    if not p.exists():
        r = requests.get(f"https://polygons.openstreetmap.fr/get_geojson.py?id={OSM_RELATION}&params=0", timeout=120)
        r.raise_for_status()
        p.write_bytes(r.content)
    g = gpd.read_file(p).to_crs("EPSG:3006")
    return g.union_all()


def tradslag(nat: Rutnat) -> dict[str, np.ndarray]:
    from rasterio.enums import Resampling
    bas = "/vsicurl/https://gis.slu.se/data/slu_forest_map/2018/data/"
    ut = {}
    for namn, fil in (("gran", "Gran_andel.tif"), ("tall", "Tall_andel_fixad.tif"), ("bjork", "Bjork_andel.tif")):
        ut[namn] = _cache(namn, nat, lambda fil=fil: _raster(bas + fil, nat, Resampling.average, src_nodata=-1))
    # Där inget trädslag har volym är det inte skog
    ingen = np.nansum(np.stack([ut["gran"], ut["tall"], ut["bjork"]]), axis=0) < 1
    for k in ut:
        ut[k] = np.where(ingen, np.nan, ut[k])
    return ut


def tradhojd(nat: Rutnat) -> np.ndarray:
    from rasterio.enums import Resampling
    def h():
        dm = _raster("/vsicurl/" + KALLOR["tradhojd"]["url"], nat, Resampling.average, src_nodata=-1)
        return np.where(dm < 30, np.where(np.isnan(dm), np.nan, 1.5), dm / 10)   # under 3 m anges som 0
    return _cache("tradhojd", nat, h)


def avverkning(nat: Rutnat) -> np.ndarray:
    """År sedan senaste slutavverkning (NaN = ingen känd)."""

    def h():
        p = CACHE / "avverkningar.geojson"
        if not p.exists():
            # Tjänsten svarar 500 på stora sidor, offset och okända fält: hämta id:n först, sedan små omgångar
            url = KALLOR["avverkning"]["url"] + "/query"
            ids = _get(url, {"where": f"Lannr='{LANNR}'", "returnIdsOnly": "true", "f": "json"})["objectIds"]
            delar = [ids[i:i + 200] for i in range(0, len(ids), 200)]
            feats = []
            with ThreadPoolExecutor(4) as ex:
                for d in ex.map(lambda d: _get(url, {"objectIds": ",".join(map(str, d)), "outFields": "OBJECTID,Avvdatum", "f": "geojson"}), delar):
                    feats += d.get("features", [])
                    if len(feats) % 10000 < 200:
                        log.info("avverkningar: %d av %d hämtade", len(feats), len(ids))
            p.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
        import geopandas as gpd
        g = gpd.read_file(p).set_crs("EPSG:4326", allow_override=True).to_crs("EPSG:3006")
        nu = datetime.now(timezone.utc)
        rader = []
        for ms, geom in zip(g["Avvdatum"], g.geometry):
            if ms is None or geom is None or (isinstance(ms, float) and np.isnan(ms)):
                continue
            dt = ms.to_pydatetime() if hasattr(ms, "to_pydatetime") else datetime.fromtimestamp(ms / 1000, timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            rader.append(((nu - dt).days / 365.25, geom))
        rader.sort(key=lambda r: -r[0])   # äldst först, så att den senaste avverkningen skriver sist
        return _rastrera(((g, round(a)) for a, g in rader), nat)
    return _cache("avverkning", nat, h)


def _fukt_band(args) -> np.ndarray:
    """Den vanligaste klassen per ruta i ett band (filen har rader om 2 m utan översikter, så GDAL:s mode blir långsam)."""
    import rasterio
    tif, del_ = args
    with rasterio.open(tif) as src:
        fonster, steg = _innanfor_bild(src, del_, src.res[0])
        a = src.read(1, window=fonster, boundless=True, fill_value=0)
    a = a.reshape(del_.hojd, steg, del_.bredd, steg)
    klasser = (1, 2, 3, 4, 7)
    antal = np.stack([(a == k).sum(axis=(1, 3)) for k in klasser])
    vanligast = np.array(klasser)[antal.argmax(axis=0)].astype(np.float32)
    vanligast[antal.sum(axis=0) == 0] = np.nan
    return vanligast


def fukt(nat: Rutnat) -> np.ndarray:
    """Klassad markfuktighet (dominerande klass i rutan) → våra klasser i kantarell/poang.py.

    SLU:s klassade karta: 1 torr–frisk, 2 frisk–fuktig, 3 blöt, 4 vatten, 7 saknas. Tolkningen bygger på stickprov
    (Storsjön ger 4, en myr 3, tätorten 1); torr hällmark skiljs inte ut, så 1 räknas som frisk.
    """
    def h():
        tif = next((RAW / "markfuktighet").rglob("*.tif"))
        band = list(_band(nat, 100))   # 2 m: ett band om 100 rader är 2 500 × 130 000 pixlar
        klass = np.full((nat.hojd, nat.bredd), np.nan, dtype=np.float32)
        with ProcessPoolExecutor(8) as ex:
            for (r0, n, _), a in zip(band, ex.map(_fukt_band, [(str(tif), b[2]) for b in band])):
                klass[r0:r0 + n] = a
        return np.select([klass == 1, klass == 2, klass == 3], [2, 3, 4], np.nan)   # 4 (vatten) och 7 blir NaN
    return _cache("fukt", nat, h)


# NMD:s klasser för bebyggd mark (klasstabellen i NMD2023bas_v2_1.tif.vat.dbf): 51 Byggnad, 52 Anlagd mark (ej byggnad
# eller väg/järnväg) och 53 Väg eller järnväg. Gatorna behövs för att villaområden ska nå gränsen; en skogsbilväg
# ger högst omkring 15 % inom 250 × 250 m (99:e percentilen kring Östersund) och gör alltså ingen tätort.
NMD_BEBYGGD = (51, 52, 53)


def _nmd_band(args) -> np.ndarray:
    """Andel bebyggd mark (NMD_BEBYGGD) per ruta i ett band."""
    import rasterio
    tif, del_ = args
    with rasterio.open(tif) as src:
        fonster, steg = _innanfor_bild(src, del_, src.res[0])
        a = src.read(1, window=fonster, boundless=True, fill_value=0)
    return np.isin(a, NMD_BEBYGGD).reshape(del_.hojd, steg, del_.bredd, steg).mean(axis=(1, 3)).astype(np.float32)


def bebyggd_andel(nat: Rutnat) -> np.ndarray:
    """Andel bebyggd mark per ruta enligt NMD 2023 (0–1)."""
    def h():
        tif = _packa_upp("NMD2023_basskikt_v2_1.zip", ".tif")
        band = list(_band(nat))
        ut = np.zeros((nat.hojd, nat.bredd), dtype=np.float32)
        with ProcessPoolExecutor(8) as ex:
            for (r0, n, _), a in zip(band, ex.map(_nmd_band, [(str(tif), b[2]) for b in band])):
                ut[r0:r0 + n] = a
        return ut
    return _cache("bebyggd", nat, h)


def _lada(a: np.ndarray, r: int) -> np.ndarray:
    """Medelvärdet i en ruta om (2r+1) × (2r+1) kring varje cell (kanterna räknar bara det som finns)."""
    p = np.pad(a, r)
    s = p.cumsum(0).cumsum(1)
    s = np.pad(s, ((1, 0), (1, 0)))
    k = 2 * r + 1
    summa = s[k:, k:] - s[:-k, k:] - s[k:, :-k] + s[:-k, :-k]
    ett = np.pad(np.ones_like(a), r).cumsum(0).cumsum(1)
    ett = np.pad(ett, ((1, 0), (1, 0)))
    antal = ett[k:, k:] - ett[:-k, k:] - ett[k:, :-k] + ett[:-k, :-k]
    return summa / antal


# En ruta räknas som tätort när minst så här stor andel av marken inom 250 × 250 m är bebyggd (NMD). Med 20 % blir
# Östersunds tätort 28,6 km², nära SCB:s tätortsyta.
TATORT_ANDEL = 0.2


def tatort(bebyggd: np.ndarray) -> np.ndarray:
    """Tätort: bebyggd mark i omgivningen (250 × 250 m), så att villaträdgårdar och parker mellan husen räknas med."""
    return _lada(np.nan_to_num(bebyggd).astype(np.float64), 2) >= TATORT_ANDEL


# SGU:s jordarter (jg2_tx) → våra grupper (kantarell/poang.py: JORDARTER)
def jordartsgrupp(text: str) -> float:
    t = (text or "").lower()
    if "vatten" in t:
        return np.nan
    if "torv" in t or "gyttja" in t or "kärr" in t or "mosse" in t:
        return 6
    if "berg" in t:
        return 7
    if "morän" in t:
        return 4 if "lera" in t or "lerig" in t else 1
    if "lera" in t:
        return 5
    if "silt" in t or "mjäla" in t:
        return 4
    if "grus" in t or "isälv" in t or "rullsten" in t:
        return 3
    if "sand" in t:
        return 2
    return 8


def jordart(nat: Rutnat) -> np.ndarray:
    def h():
        import pyogrio
        gpkg = _packa_upp("jordarter25k-100k.zip", ".gpkg")
        lager = next(n for n, _ in pyogrio.list_layers(gpkg) if "grund" in n.lower())
        g = pyogrio.read_dataframe(gpkg, layer=lager, bbox=nat.bounds, columns=["jg2_tx"])
        log.info("jordarter: %d ytor i länets bbox (lagret %s)", len(g), lager)
        grupp = g["jg2_tx"].map(jordartsgrupp)
        ok = grupp.notna() & g.geometry.notna()
        return _rastrera(zip(g.geometry[ok], grupp[ok]), nat)
    return _cache("jordart", nat, h)


def hojd(nat: Rutnat) -> np.ndarray:
    from pyproj import Transformer
    from rasterio.enums import Resampling

    def h():
        t = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True)
        x0, y0, x1, y1 = nat.bounds
        lons, lats = t.transform([x0, x1, x0, x1], [y0, y0, y1, y1])
        ut = np.full((nat.hojd, nat.bredd), np.nan, dtype=np.float32)
        for lat in range(int(np.floor(min(lats))), int(np.floor(max(lats))) + 1):
            for lon in range(int(np.floor(min(lons))), int(np.floor(max(lons))) + 1):
                namn = f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM"
                try:
                    a = _raster(f"/vsicurl/https://copernicus-dem-30m.s3.amazonaws.com/{namn}/{namn}.tif", nat, Resampling.bilinear)
                except Exception as e:   # rutor utan land finns inte
                    log.info("höjd: %s saknas (%s)", namn, str(e)[:80])
                    continue
                ut = np.fmax(ut, a)
        return ut
    return _cache("hojd", nat, h)


def arSkog(data: dict[str, np.ndarray]) -> np.ndarray:
    """Vilka rutor som är skog. Trädslagskartan ger andelar överallt, även över sjöar, så skog avgörs av trädhöjden
    (minst 3 m) eller en avverkning de senaste 30 åren, och inte vatten enligt markfuktighetskartan. Tätorter räknas
    inte som skog (bebyggd mark i omgivningen enligt NMD, se tatort())."""
    hog = np.nan_to_num(data["tradhojd"], nan=0) >= 3
    avverkad = np.nan_to_num(data["ar_sedan_avverkning"], nan=99) < 30
    vatten = np.isnan(data["fukt"]) if "fukt" in data else np.zeros_like(hog)
    tatort_ = data["tatort"].astype(bool) if "tatort" in data else np.zeros_like(hog)
    return (hog | avverkad) & ~vatten & ~tatort_


def hamta():
    """Rutnät, källdata, källornas beskrivning och länets yta på rutnätet."""
    from rasterio.features import rasterize

    CACHE.mkdir(parents=True, exist_ok=True)
    yta = gransen()
    nat = Rutnat.kring(*yta.bounds)
    log.info("%s: %d × %d rutor om 50 m", OMRADE, nat.bredd, nat.hojd)
    innanfor = rasterize([(yta, 1)], out_shape=(nat.hojd, nat.bredd), transform=nat.transform, fill=0, dtype="uint8").astype(bool)
    data = tradslag(nat)
    data["tradhojd"] = tradhojd(nat)
    data["ar_sedan_avverkning"] = avverkning(nat)
    data["jordart"] = jordart(nat)
    data["hojd"] = hojd(nat)
    data["fukt"] = fukt(nat)
    data["tatort"] = tatort(bebyggd_andel(nat))
    log.info("tätort: %.1f %% av länets rutor", 100 * float(data["tatort"][innanfor].mean()))
    skog = arSkog(data)
    log.info("skog: %.0f %% av länets rutor", 100 * float(skog[innanfor].mean()))
    for f in ("gran", "tall", "bjork"):
        data[f] = np.where(skog, data[f], np.nan)
    kallor = [{**k, "datum": IDAG} for k in KALLOR.values()]
    return nat, data, kallor, innanfor
