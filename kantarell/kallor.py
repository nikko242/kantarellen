"""De öppna källorna för Östersunds kommun, lagda på rutnätet om 50 m (se docs/datakallor.md).

Varje källa hämtas en gång och sparas i data/raw (checkas inte in): rasterkällor läses direkt från servern för kommunens
bbox (GDAL /vsicurl/), vektorkällor hämtas via API och rastreras. Resultatet per källa sparas som rutnat_<namn>.npy.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests

from .rutnat import Rutnat

log = logging.getLogger("kantarell.kallor")
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
KOMMUN = "2380"
OSM_RELATION = 935577
# GDAL läser bara de delar av fjärrfilerna som behövs
GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif", "GDAL_HTTP_MULTIRANGE": "YES",
            "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES", "VSI_CACHE": "TRUE", "VSI_CACHE_SIZE": "200000000"}
IDAG = time.strftime("%Y-%m-%d")

KALLOR = {
    "gransen": {"namn": "Kommungränsen (OpenStreetMap)", "vad": "kommunens yta", "licens": "ODbL, © OpenStreetMap contributors",
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
                "url": "https://api.sgu.se/oppnadata/jordarter25k-100k/ogc/features/v1"},
    "hojd": {"namn": "Copernicus DEM GLO-30", "vad": "höjd över havet, 30 m (ytmodell)",
             "licens": "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA",
             "url": "https://copernicus-dem-30m.s3.amazonaws.com/"},
}


def _cache(namn: str, nat: Rutnat, hamta) -> np.ndarray:
    p = RAW / f"rutnat_{namn}.npy"
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


def _raster(url_or_path: str, nat: Rutnat, resampling, src_nodata=None) -> np.ndarray:
    """En rasterkälla omsamplad till rutnätet (bara kommunens del läses)."""
    import rasterio
    from rasterio.vrt import WarpedVRT

    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(url_or_path) as src:
            nodata = src_nodata if src_nodata is not None else src.nodata
            with WarpedVRT(src, crs="EPSG:3006", transform=nat.transform, width=nat.bredd, height=nat.hojd,
                           resampling=resampling, src_nodata=nodata, nodata=np.nan, dtype="float32") as vrt:
                return vrt.read(1)


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


# ---------- Källorna ----------

def gransen():
    import geopandas as gpd
    p = RAW / "gransen.geojson"
    if not p.exists():
        r = requests.get(f"https://polygons.openstreetmap.fr/get_geojson.py?id={OSM_RELATION}&params=0", timeout=60)
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
        p = RAW / "avverkningar.geojson"
        if not p.exists():
            # Tjänsten svarar 500 på stora sidor, offset och okända fält: hämta id:n först, sedan små omgångar
            url = KALLOR["avverkning"]["url"] + "/query"
            ids = _get(url, {"where": f"Kommunnr='{KOMMUN}'", "returnIdsOnly": "true", "f": "json"})["objectIds"]
            feats = []
            for i in range(0, len(ids), 200):
                d = _get(url, {"objectIds": ",".join(map(str, ids[i:i + 200])), "outFields": "OBJECTID,Avvdatum", "f": "geojson"})
                feats += d.get("features", [])
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


def fukt(nat: Rutnat) -> np.ndarray:
    """Klassad markfuktighet (dominerande klass i rutan) → våra klasser i kantarell/poang.py.

    SLU:s klassade karta: 1 torr–frisk, 2 frisk–fuktig, 3 blöt, 4 vatten, 7 saknas. Tolkningen bygger på stickprov
    (Storsjön ger 4, en myr 3, tätorten 1); torr hällmark skiljs inte ut, så 1 räknas som frisk.
    """
    from rasterio.enums import Resampling

    def h():
        tif = next((RAW / "markfuktighet").rglob("*.tif"))
        klass = _raster(str(tif), nat, Resampling.mode)
        return np.select([klass == 1, klass == 2, klass == 3], [2, 3, 4], np.nan)   # 4 (vatten) och 7 blir NaN
    return _cache("fukt", nat, h)


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


def jordart(nat: Rutnat, lonlat_bbox: tuple[float, float, float, float]) -> np.ndarray:
    from shapely.geometry import shape

    def h():
        p = RAW / "jordarter.geojson"
        if not p.exists():
            url = KALLOR["jordart"]["url"] + "/collections/grundlager/items"
            params = {"f": "json", "limit": 1000, "bbox": ",".join(f"{v:.4f}" for v in lonlat_bbox),
                      "crs": "http://www.opengis.net/def/crs/EPSG/0/3006"}
            feats = []
            while url:
                r = requests.get(url, params=params, timeout=180)
                r.raise_for_status()
                d = r.json()
                feats += [{"geometry": f["geometry"], "properties": {"jg2_tx": f["properties"].get("jg2_tx")}} for f in d.get("features", [])]
                log.info("jordarter: %d av %s hämtade", len(feats), d.get("numberMatched", "?"))
                url = next((l["href"] for l in d.get("links", []) if l.get("rel") == "next"), None)
                params = None
            p.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
        feats = json.loads(p.read_text(encoding="utf-8"))["features"]
        return _rastrera(((shape(f["geometry"]), jordartsgrupp(f["properties"]["jg2_tx"])) for f in feats
                          if f.get("geometry") and not np.isnan(jordartsgrupp(f["properties"]["jg2_tx"]))), nat)
    return _cache("jordart", nat, h)


def hojd(nat: Rutnat) -> np.ndarray:
    from rasterio.enums import Resampling

    def h():
        lager = []
        for lat in (62, 63):
            for lon in (14, 15):
                namn = f"Copernicus_DSM_COG_10_N{lat}_00_E0{lon}_00_DEM"
                lager.append(_raster(f"/vsicurl/https://copernicus-dem-30m.s3.amazonaws.com/{namn}/{namn}.tif", nat, Resampling.bilinear))
        return np.nanmax(np.stack(lager), axis=0)
    return _cache("hojd", nat, h)


def arSkog(data: dict[str, np.ndarray]) -> np.ndarray:
    """Vilka rutor som är skog. Trädslagskartan ger andelar överallt, även över sjöar, så skog avgörs av trädhöjden
    (minst 3 m) eller en avverkning de senaste 30 åren, och inte vatten enligt markfuktighetskartan. Tätorter med
    träd räknas med; en marktäckeskarta (NMD) skulle skilja ut dem."""
    hog = np.nan_to_num(data["tradhojd"], nan=0) >= 3
    avverkad = np.nan_to_num(data["ar_sedan_avverkning"], nan=99) < 30
    vatten = np.isnan(data["fukt"]) if "fukt" in data else np.zeros_like(hog)
    return (hog | avverkad) & ~vatten


def hamta():
    """Rutnät, källdata, källornas beskrivning och kommunens yta på rutnätet."""
    from pyproj import Transformer
    from rasterio.features import rasterize

    RAW.mkdir(parents=True, exist_ok=True)
    yta = gransen()
    nat = Rutnat.kring(*yta.bounds)
    log.info("Östersunds kommun: %d × %d rutor om 50 m", nat.bredd, nat.hojd)
    innanfor = rasterize([(yta, 1)], out_shape=(nat.hojd, nat.bredd), transform=nat.transform, fill=0, dtype="uint8").astype(bool)
    t = Transformer.from_crs("EPSG:3006", "EPSG:4326", always_xy=True)
    lon0, lat0 = t.transform(nat.bounds[0], nat.bounds[1])
    lon1, lat1 = t.transform(nat.bounds[2], nat.bounds[3])
    data = tradslag(nat)
    data["tradhojd"] = tradhojd(nat)
    data["ar_sedan_avverkning"] = avverkning(nat)
    data["jordart"] = jordart(nat, (lon0, lat0, lon1, lat1))
    data["hojd"] = hojd(nat)
    if any((RAW / "markfuktighet").rglob("*.tif")) if (RAW / "markfuktighet").exists() else False:
        data["fukt"] = fukt(nat)
    else:
        log.warning("fukt: markfuktighetskartan saknas i data/raw/markfuktighet; faktorn räknas som saknad")
    skog = arSkog(data)
    log.info("skog: %.0f %% av kommunens rutor", 100 * float(skog[innanfor].mean()))
    for f in ("gran", "tall", "bjork"):
        data[f] = np.where(skog, data[f], np.nan)
    kallor = [{**k, "datum": IDAG} for n, k in KALLOR.items() if n != "fukt" or "fukt" in data]
    return nat, data, kallor, innanfor
