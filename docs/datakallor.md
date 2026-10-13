# Datakällor för kantarellprototypen – Östersunds kommun (2380)

Undersökt 2026-10-13 med små anrop (HEAD, katalogvisningar, GetCapabilities och små bbox-frågor). Inga filer över cirka 20 MB har laddats ner. Storlekar på stora filer kommer från `Content-Length` eller från zip-arkivens centralkatalog, som jag läste med HTTP Range.

## Gemensamma referensvärden

| | Värde |
|---|---|
| Kommun | Östersunds kommun, kommunkod/SCB-kod `2380`, OSM-relation `935577` |
| Län | Jämtlands län, länskod `23` (Skogsstyrelsens länsfiler har suffixet `_23`) |
| Bbox WGS84 (lon/lat), från OSM-polygonen | `14.2647, 62.6661, 15.5560, 63.5949` |
| Bbox SWEREF99 TM (EPSG:3006), från OSM-polygonen | `462966, 6948420, 527864, 7051871` |
| Bbox avrundad till 50 m-rutnät | `462950, 6948400, 527900, 7051900` → 1 299 × 2 070 celler (2,69 milj.) |
| Kommunens yta (OSM, inkl. vatten) | ≈ 2 515 km² ≈ 1,0 milj. celler om 50 × 50 m |
| GBIF/GADM-id för kommunen | `SWE.6.6_1` (Jämtlands län = `SWE.6_1`) |

Verktyg: alla rastervägar nedan går att köra med GDAL (`gdalwarp`/`gdal_translate` med `/vsicurl/`) eller rasterio. GDAL läser då bara de byte som behövs via HTTP Range. På den här maskinen finns varken GDAL eller rasterio (bara ren Python 3.14), så något av dem behöver installeras, till exempel `pip install rasterio` eller via OSGeo4W eller conda.

---

## 1. Kommungräns

### a) OpenStreetMap: rekommenderas, inget konto
- **Relation:** `https://www.openstreetmap.org/relation/935577` (taggar: `admin_level=7`, `ref=2380`, `ref:scb=2380`, `name=Östersunds kommun`).
- **Färdig GeoJSON (testad, 70 KB, MultiPolygon i WGS84, 5 delar, 2 960 punkter):**
  `https://polygons.openstreetmap.fr/get_geojson.py?id=935577&params=0`
- **Alternativ via Overpass (testad):**
  `POST https://overpass-api.de/api/interpreter` med `data=[out:json];rel(935577);out geom;`
  Notera: frågan `["ref:se:kommun:kod"="2380"]` ger inget resultat, eftersom taggen heter `ref:scb`.
- **Format/upplösning:** vektor, full OSM-detalj. Den behöver projiceras till EPSG:3006 (`ogr2ogr -t_srs EPSG:3006`).
- **Licens:** ODbL 1.0. Kräver attribution "© OpenStreetMap contributors". Share-alike gäller om man distribuerar en härledd databas.
- **Storlek:** ≈ 70 KB.
- **Avgränsning:** relationen *är* kommunen.

### b) SCB "Digitala gränser" (CC0, inget konto)
- **URL (testad, 215 KB):** `https://www.scb.se/contentassets/3443fea3fa6640f7a57ea15d9a372d33/shape_svenska_260225.zip`
  (sida: `https://www.scb.se/hitta-statistik/regional-statistik-och-kartor/regionala-indelningar/digitala-granser/`). Filnamnet ändras när SCB publicerar en ny version.
- **Innehåll:** nästlade zip-filer, bland annat `Kommun_Sweref99TM.zip` (shapefil i SWEREF99 TM, fälten `KnKod` och `KnNamn`).
- **Licens:** CC0.
- **Varning:** kraftigt generaliserad. Östersund består av en polygon med bara 48 punkter och ≈ 2 312 km², och SCB skriver själva att gränserna "inte är lämpliga för analyser". Södra kanten ligger ≈ 27 km fel jämfört med OSM (N-min 6 975 201 mot 6 948 420). Därför olämplig för en klippmask med 50 m-rutor.

### c) Lantmäteriet "Kommun, län och rike" (CC BY 4.0, **kräver konto**)
- **STAC (öppen katalog, testad):** `https://api.lantmateriet.se/stac-vektor/v1/collections/kommun-lan-rike/items`
- **Fil:** `https://dl1.lantmateriet.se/administrativ-indelning/kommun-lan-rike/kommun-lan-rike_aktuell.zip` (≈ 6,0 MB, hela landet). Det finns även årgångar: `_2026`, `_2025`, `_2020` …
- **Åtkomst:** själva filen ger `401 Unauthorized` med `WWW-Authenticate: Basic`. Man behöver ett Geotorget-konto (`https://geotorget.lantmateriet.se/`) och måste beställa produkten (avgiftsfri, öppna data) där. Därefter används Geotorget-användarnamn och lösenord som HTTP Basic auth.
- **Licens:** CC BY 4.0 enligt STAC-katalogen.
- **Närmaste alternativ utan konto:** OSM (a).

---

## 2. SLU Skogskarta – trädslagsandelar (tall, gran, björk)

### a) SLU:s egen nedladdning: rekommenderas, inget konto
- **Katalog (testad):** `https://gis.slu.se/data/slu_forest_map/2018/data/`
  | Fil | Storlek |
  |---|---|
  | `Tall_andel.tif` / `Tall_andel_fixad.tif` | 3,3 GB vardera (använd `_fixad`, som är en rättad version) |
  | `Gran_andel.tif` | 3,3 GB (uppdaterad 2026-04-27) |
  | `Bjork_andel.tif` | 2,7 GB |
  | `Contorta_andel.tif`, `OvrLov_andel.tif`, `Ek_andel.tif`, `Bok_andel.tif` | 0,14–1,1 GB |
- **Dokumentation:** `https://gis.slu.se/data/slu_forest_map/2018/docs/Tradslag_SLUskogskarta.docx`. Den beskriver trädslagsandel **i procent av volymen**, tagen fram med kNN från Skogliga grunddata, Sentinel-2 (2018, ±1 år) och Riksskogstaxeringens provytor.
- **Format (läst ur TIFF-huvudet med Range):** GeoTIFF, Int16 (signed), LZW, nodata `-1`, **12,5 m**, 52 600 × 123 200 px, origo `265000, 7672500`. Projektionen är UTM 33N/GRS80, vilket i praktiken är detsamma som EPSG:3006. Filerna är **strip-indelade (20 rader per strip), inte COG**, men servern stöder `Accept-Ranges: bytes`.
- **Konto:** nej.
- **Licens:** ingen uttrycklig licens står vid filerna. SLU beskriver syftet som att "öppet och fritt tillhandahålla" data. Ange källan "SLU Skogskarta".
- **Storlek för kommunen:** kommunens rader (N 7 051 900–6 948 400) motsvarar 415 strips. Varje strip är hela landets bredd, så GDAL hämtar ≈ **210 MB per trädslag** (≈ 630 MB för tall, gran och björk). Det ger ≈ 5 200 × 8 300 px per trädslag, eller 1 299 × 2 070 efter omsampling till 50 m.
- **Avgränsning:** bbox i EPSG:3006 direkt mot fjärrfilen:
  ```
  gdalwarp -t_srs EPSG:3006 -te 462950 6948400 527900 7051900 -tr 50 50 -r average \
    -cutline ostersund_3006.geojson /vsicurl/https://gis.slu.se/data/slu_forest_map/2018/data/Tall_andel_fixad.tif tall_50m.tif
  ```

### b) Skogsstyrelsens länsfiler med SLU Skogskarta (volym per trädslag): fungerar inte
- **Flöden:** `https://geodpags.skogsstyrelsen.se/geodataport/feeds/SLUSkogskartaTallVolym.xml` (även `GranVolym`, `BjörkVolym`, `Volym` …)
- **Länsfil Jämtland:** `https://geodpags.skogsstyrelsen.se/geodataport/data/sksSLUskogskartaTallVolym23.zip` (198 KB; `Björk` skrivs med `%C3%B6`).
- **Problem:** filen jag laddade ner (tall, Jämtland) packas upp till en 28 000 × 36 000 px raster (12,5 m) där **alla 36 000 rader komprimeras till exakt 390 byte**. Rastret ser alltså ut att vara tomt eller konstant, och det är dessutom en äldre produkt (volym, inte andel). Använd inte den här vägen.

---

## 3. Skogsstyrelsen: medelhöjd, markfuktighet och utförda avverkningar

Licens: Skogsstyrelsen skriver "Om inget annat anges är Skogsstyrelsens geodata öppna data och är släppta under licensen CC0" (`https://www.skogsstyrelsen.se/e-tjanster-och-kartor/karttjanster/geodatatjanster/villkor/`).
Nedladdning sker via Atom-flöden i `https://geodpags.skogsstyrelsen.se/geodataport/feeds/` (katalogvisning öppen) och zip-filer i `…/geodataport/data/`. Inget konto behövs.
Skogsstyrelsens ArcGIS-server `https://geodata.skogsstyrelsen.se/arcgis/rest/services` ger däremot **401 Unauthorized** och kräver användarkonto (`https://www.skogsstyrelsen.se/e-tjanster-och-kartor/karttjanster/geodatatjanster/anvandarkonto/`). Den behövs inte för vägarna nedan.

### 3a) Medelhöjd (Skogliga grunddata, grundytevägd medelhöjd HGV)
**Rekommenderat: SLU:s rikstäckande SGD2-fil (inget konto, gör bbox-läsning möjlig)**
- `https://gis.slu.se/data/slu_skogliga_grunddata/SGD2/data/SGD2_HGV.tif` (4,0 GB)
- Andra lager i samma katalog: `SGD2_VOL`, `SGD2_GY`, `SGD2_DGV`, `SGD2_BIO`, `SGD2_P95`, `SGD2_Vegkvot`, samt underkatalogerna `alder/` och `sis/`.
- Dokumentation: `https://gis.slu.se/data/slu_skogliga_grunddata/SGD2/documents/` (produktbeskrivning, kvalitet, `SGD2_metadata.gpkg` på 133 MB med skanningsdatum).
- **Format (läst med Range):** BigTIFF, **tiled 128 × 128**, LZW, Int16, nodata `-1`, **10 m**, EPSG:3006, origo `200000, 7700000`, 80 000 × 160 000 px. Höjden anges i **decimeter**. Celler med medelhöjd under 3 m har värdet 0. IFD ligger sist i filen, så filen är inte en formell COG, men `/vsicurl/` fungerar.
- **Storlek för kommunen:** ≈ 6 500 × 10 350 px ≈ 4 100 tiles. Uppskattningsvis 20–40 MB data plus ≈ 9 MB tile-index.
- **Avgränsning:** `gdalwarp -te … -tr 50 50 -r average /vsicurl/https://gis.slu.se/…/SGD2_HGV.tif`.

**Alternativ: Skogsstyrelsens länsfiler**
- Flöde: `https://geodpags.skogsstyrelsen.se/geodataport/feeds/SGDMedelh%C3%B6jd_omdrev3.xml` (även `_omdrev1`, `_omdrev2`)
- Jämtland: `https://geodpags.skogsstyrelsen.se/geodataport/data/sks_Medelh%C3%B6jd_omdrev2_23.zip` (539 MB, tif 564 MB, 10 m, origo `300000, 7250000`)
- `…_omdrev3_23.zip` är bara 28 MB (49 MB okomprimerat). Omdrev 3 täcker alltså bara en liten del av länet än så länge.
- Zip-filen måste laddas ner hel innan den kan klippas.

**Trädhöjd 1 m (inte nödvändig vid 50 m):** `https://geodpags.skogsstyrelsen.se/geodataport/data/sks_Tradhojd_omdrev3_23.zip` (2,5 GB, 1 m, dm). Flödet anger rättigheterna "User registration and agreement on not sub distributing and commercial use", så den har andra villkor än CC0. Filen svarade ändå 200 utan inloggning. Den behövs inte, eftersom HGV räcker.

### 3b) Markfuktighetskarta (SLU, distribueras av Skogsstyrelsen)
- **Klassad (rekommenderas):** flöde `https://geodpags.skogsstyrelsen.se/geodataport/feeds/SLUMarkfuktighetKlassad.xml`
  Jämtland: `https://geodpags.skogsstyrelsen.se/geodataport/data/sksSLUMarkfuktighet_klassad23.zip`
  742 MB zip, tif 864 MB. **2 m**, 8-bit, LZW, 135 000 × 205 000 px, origo `340000, 7230000`, EPSG:3006.
- **Kontinuerlig (0–100 %):** `https://geodpags.skogsstyrelsen.se/geodataport/data/SKSSLUMarkfuktighet23.zip`, **11,2 GB**. Undvik den.
- **Rättigheter i flödet:** "no conditions apply", vilket ger CC0 enligt Skogsstyrelsens villkor.
- **Konto:** nej.
- **Storlek och avgränsning:** zip-filen måste laddas ner hel (742 MB, deflate går inte att läsa med Range). Packa upp och kör sedan `gdalwarp -te 462950 6948400 527900 7051900 -tr 50 50 -r mode` (för klasser), eller beräkna andelen blöt mark per 50 m-ruta. Resultatet blir litet (≈ 2,7 milj. celler).

### 3c) Utförda avverkningar (med datum)
**Rekommenderat: öppen ArcGIS REST-tjänst med kommunfilter (inget konto, testad)**
- Lager: `https://geodpags.skogsstyrelsen.se/arcgis/rest/services/Geodataportal/GeodataportalVisaUtfordavverkning/MapServer/1`
  (lager 0 = bara senaste året)
- Fält: `Kommunnr`, `Kommun`, `Lannr`, `Avvdatum` (datum), `Avverktyp`, `Skogstyp`, `Arealha`, `AnmaldHa`, `KallaDatum`, `Forebild`, `Efterbild` m.fl.
- Spatial referens: EPSG:3006. `maxRecordCount` = 2000. Paginering stöds (`resultOffset`). Format: JSON, GeoJSON och PBF.
- **Antal i kommunen:** `where=Kommunnr='2380'` ger **7 093 polygoner**, med `Avvdatum` från 1996-11 till 2026-09. 2 253 av dem är från 2020 eller senare.
- **Exempelanrop (4 sidor à 2 000):**
  ```
  …/MapServer/1/query?where=Kommunnr%3D%272380%27&outFields=OBJECTID,Avvdatum,Avverktyp,Arealha
    &orderByFields=OBJECTID&resultOffset=0&resultRecordCount=2000&outSR=3006
    &geometryPrecision=0&maxAllowableOffset=5&f=geojson
  ```
- **Storlek:** ≈ 0,86 KB per objekt med generalisering, alltså ≈ **6 MB** för kommunen (≈ 70 MB med full geometri).

**Alternativ: hela landet som GeoPackage**
- Flöde: `https://geodpags.skogsstyrelsen.se/geodataport/feeds/UtfordAvverk.xml`
- Fil: `https://geodpags.skogsstyrelsen.se/geodataport/data/sksUtfordAvverk_gpkg.zip`. Zip-filen är 2,7 GB och innehåller en GeoPackage på 7,5 GB, EPSG:3006, och uppdateras dagligen. Inget länsuttag finns.

---

## 4. SGU – Jordarter 1:25 000–1:100 000

- **Licens:** CC0 1.0 enligt produktbeskrivningen `https://resource.sgu.se/dokument/produkter/jordarter-25-100000-beskrivning.pdf`.
- **Konto:** nej.

### a) OGC API – Features: rekommenderas
- Landningssida: `https://api.sgu.se/oppnadata/jordarter25k-100k/ogc/features/v1`
- Samlingar (testade): `grundlager` (jordart i grundlagret, huvudlagret), `ytlager`, `oversta-ytlager`, `underliggande-lager`, `blockighet`, `landform`, `linjer`, `punkter` och `tackningskarta` (karttyp och skala per karteringsområde).
- CRS: lagras i EPSG:3006. Utdata kan fås i CRS84, 3006, 3007–3018 och 2400 via `crs=`.
- Attribut i `grundlager`: `jg2` (jordartskod), `jg2_tx` (t.ex. "Morän", "Berg", "Moränlera eller lerig morän", "Vatten"), `kartering`, `karttyp`, `symbol`, `geom_area`.
- **Viktigt:** `bbox-crs=…/EPSG/0/3006` **ignoreras**, så frågan ger 0 träffar. Ange därför bbox i lon/lat (CRS84) och begär utdata i 3006:
  ```
  https://api.sgu.se/oppnadata/jordarter25k-100k/ogc/features/v1/collections/grundlager/items
    ?f=json&limit=1000&bbox=14.2647,62.6661,15.5560,63.5949
    &crs=http://www.opengis.net/def/crs/EPSG/0/3006
  ```
  Bläddra vidare med länken `rel=next` (parametern `startIndex`).
- **Storlek:** `numberMatched` = **31 865** polygoner i kommunens bbox. En sida med 300 objekt var ≈ 1,0 MB (≈ 3,4 KB per objekt), så totalt blir det ≈ **110 MB GeoJSON**. Spara som GeoPackage och rastrera till 50 m (dominerande jordart eller andel per klass).
- **Täckning i kommunen:** i huvudsak karttyp 3 (1:50 000, karteringarna "ostersund", "brunflo", "myrviken" m.fl., 2015–2024), med kanter av karttyp 5 (1:100 000, ≈ 2000).
- WFS finns också: `https://api.sgu.se/oppnadata/jordarter25k-100k/wfs`.

### b) Hela landet som GeoPackage
- `https://resource.sgu.se/data/oppnadata/jordarter25k-100k/jordarter25k-100k.zip`: 3,4 GB zip som innehåller `jordarter25k_100k.gpkg` (8,7 GB) samt `.lyrx`, `.qlr` och en symbolfont. Inget uttag per län. Den är för stor för prototypen.

---

## 5. Höjd

### a) Lantmäteriet Markhöjdmodell (grid 1+): **kräver konto**
- STAC (öppen katalog, testad): `https://api.lantmateriet.se/stac-hojd/v1/collections/dtm-cog/items?bbox=14.2647,62.6661,15.556,63.5949`
- Ger **84 tiles** à 10 × 10 km, **1 m**, float32 COG (512-block, deflate), EPSG:5845 (SWEREF99 TM + RH2000), totalt ≈ **19,9 GB**.
  Exempel: `https://dl1.lantmateriet.se/hojd/data/grid/mhm/70_4/m700_48.tif` (207 MB).
- Data ger `401` med Basic auth. Metadatafilerna `…/hojd/pub/…_info.json` och thumbnails är öppna.
- Licens: CC BY 4.0 (Lantmäteriets "Användningsvillkor för värdefulla datamängder").
- **Så skaffar man åtkomst:** skapa ett konto på `https://geotorget.lantmateriet.se/`, beställ "Markhöjdmodell Nedladdning" (avgiftsfri) och använd Geotorget-användarnamn och lösenord som Basic auth. Guide: `https://www.lantmateriet.se/contentassets/6b85c93c6954407e855c896da5a415f2/guide_radiant_earth_markhojdmodell.pdf`.
- **Grid 50+** finns inte som STAC-samling. Den beställs via Geotorget (eller via FTP, som också kräver användarkonto). Inget konto, ingen åtkomst.

### b) Copernicus DEM GLO-30: rekommenderas för prototypen, inget konto
- AWS Open Data, COG, inget konto: `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{N|S}{lat}_00_{E|W}{lon}_00_DEM/Copernicus_DSM_COG_10_{…}_DEM.tif`
- Rutor för kommunen (HEAD testad, alla 200):
  | Ruta | Storlek |
  |---|---|
  | `N62_00_E014_00` | 20,6 MB |
  | `N62_00_E015_00` | 21,3 MB |
  | `N63_00_E014_00` | 19,6 MB |
  | `N63_00_E015_00` | 21,2 MB |
  Totalt ≈ **83 MB**. Med `/vsicurl/` och `-te` läses bara de delar som behövs.
- Format: GeoTIFF COG, float32, EPSG:4326, 1" × 1,5" vid 60–70°N (≈ 30 m). Måste omprojiceras till 3006.
- **Obs:** detta är en **ytmodell (DSM, inklusive träd och byggnader)**, inte en markmodell. Lutning och exposition vid 50 m påverkas lite, men höjden i skog blir för hög med trädhöjden.
- Licens: Copernicus DEM-licens (fri användning, även kommersiell, med attribution "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA").
- Exempel:
  ```
  gdalbuildvrt dem.vrt /vsicurl/https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N62_00_E014_00_DEM/Copernicus_DSM_COG_10_N62_00_E014_00_DEM.tif …(4 st)
  gdalwarp -t_srs EPSG:3006 -te 462950 6948400 527900 7051900 -tr 50 50 -r bilinear dem.vrt dem_50m.tif
  ```

---

## 6. Kantarellfynd (Cantharellus cibarius) via GBIF

- **Taxon:** `taxonKey=5249504` (Cantharellus cibarius Fr., ACCEPTED, via `https://api.gbif.org/v1/species/match?scientificName=Cantharellus%20cibarius`).
- **Dataset:** Artportalen `38b4c89f-584c-41bb-bd8f-cd1def33e92f`, licens **CC0**.
- **API:** `https://api.gbif.org/v1/occurrence/search`. Inget konto för sök (max 300 per sida, offset upp till 100 000). Asynkrona nedladdningar (`/occurrence/download`) kräver ett gratis GBIF-konto, men behövs inte här.
- **Exempel:**
  ```
  https://api.gbif.org/v1/occurrence/search?taxonKey=5249504&datasetKey=38b4c89f-584c-41bb-bd8f-cd1def33e92f
    &gadmGid=SWE.6.6_1&limit=300
  # eller med polygon (moturs WKT), t.ex. bbox:
  &geometry=POLYGON((14.2647 62.6661,15.556 62.6661,15.556 63.5949,14.2647 63.5949,14.2647 62.6661))
  ```
- **Antal fynd (2026-10-13):**
  | Urval | Antal |
  |---|---|
  | Östersunds kommun (`gadmGid=SWE.6.6_1`) | **2** (2002 Bringåsen, 2018 Kotjärnen; osäkerhet 100 resp. 50 m) |
  | Kommunens bbox (även delar av Krokom, Berg, Bräcke) | 10 (1990–2023) |
  | Jämtlands län (`SWE.6_1`) | 113 |
  | Hela Sverige, Artportalen | 14 527 |
  Alla fynd i området kommer från Artportalen. Inga andra dataset i GBIF har kantarell här.
- **Slutsats:** **2 fynd räcker inte för att validera modellen.** Bredda till länet (113), eller använd Artportalen direkt.
- **Artportalen direkt (fler och nyare fynd):** SLU Artdatabankens Species Observation System, `https://api.artdatabanken.se/species-observation-system/v1/`. Den ger `401 – missing subscription key`, så **ett konto krävs**: registrera dig på `https://api-portal.artdatabanken.se/` och prenumerera på "Species Observation System" för att få en `Ocp-Apim-Subscription-Key`. Närmaste väg utan konto är GBIF enligt ovan.

---

## 7. Bakgrundskarta för MapLibre (statisk webbapp)

### a) OpenFreeMap: rekommenderas, inget konto, vektortiles
- Stil (testad, 200): `https://tiles.openfreemap.org/styles/liberty` (även `bright` och `positron`). Källa: `https://tiles.openfreemap.org/planet` (OpenMapTiles-schema).
- Ingen nyckel, ingen registrering och ingen gräns för antal visningar enligt OpenFreeMap.
- Attribution: "OpenFreeMap © OpenMapTiles Data from OpenStreetMap".
- MapLibre: `new maplibregl.Map({ style: 'https://tiles.openfreemap.org/styles/liberty', … })`. Vektortiles fungerar bra tillsammans med ett eget raster- eller GeoJSON-lager med sannolikheten.

### b) OpenStreetMap-rutor (tile.openstreetmap.org): tillåtet men med villkor
- URL: `https://tile.openstreetmap.org/{z}/{x}/{y}.png` (raster, 256 px; testad 200, `Access-Control-Allow-Origin: *`).
- Användningsvillkor (`https://operations.osmfoundation.org/policies/tiles/`):
  - synlig attribution "© OpenStreetMap contributors"
  - webbläsaren ska skicka en giltig Referer
  - cache-headers ska respekteras
  - **ingen bulk-nedladdning, förhämtning eller offline-användning**
  - ingen SLA, och tjänsten kan blockeras vid tung användning
- Den passar en prototyp med låg trafik. Byt till (a) eller egen hosting om appen sprids.

### c) Lantmäteriet Topografisk webbkarta (CC BY)
- Den kräver Geotorget-konto/nyckel enligt Lantmäteriets upplägg. Jag har inte testat den här, och den behövs inte för prototypen.

---

## Rekommendation – väg per källa

| # | Källa | Väg för prototypen | Konto? | Ungefärlig hämtning |
|---|---|---|---|---|
| 1 | Kommungräns | OSM-relation 935577 via `polygons.openstreetmap.fr` (GeoJSON), omprojicerad till 3006 och använd som klippmask | Nej | 70 KB |
| 2 | Trädslag tall/gran/björk | `gis.slu.se/data/slu_forest_map/2018/data/{Tall_andel_fixad,Gran_andel,Bjork_andel}.tif` via `/vsicurl/` + `gdalwarp -te … -tr 50 50 -r average` | Nej | ≈ 210 MB per trädslag (Range) |
| 3a | Medelhöjd | `gis.slu.se/data/slu_skogliga_grunddata/SGD2/data/SGD2_HGV.tif` via `/vsicurl/` (10 m, dm) | Nej | ≈ 30–50 MB (Range) |
| 3b | Markfuktighet | `sksSLUMarkfuktighet_klassad23.zip` (Jämtland, 2 m klassad), laddas ner en gång och klipps lokalt | Nej | 742 MB |
| 3c | Avverkningar | ArcGIS REST `GeodataportalVisaUtfordavverkning/MapServer/1`, `where=Kommunnr='2380'`, GeoJSON, 4 sidor | Nej | ≈ 6 MB |
| 4 | Jordarter | OGC API Features `jordarter25k-100k`, samling `grundlager`, bbox i CRS84 + `crs=EPSG:3006`, bläddra med `next` | Nej | ≈ 110 MB |
| 5 | Höjd | Copernicus GLO-30 (4 COG-rutor på AWS) omprojicerad till 50 m. Byt till Lantmäteriets markhöjdmodell (STAC `dtm-cog`) om ett Geotorget-konto skaffas | Nej (LM: ja) | ≈ 83 MB (LM: ≈ 20 GB för 1 m) |
| 6 | Kantarellfynd | GBIF `occurrence/search` med `taxonKey=5249504`, Artportalens datasetKey och `gadmGid=SWE.6_1` (länet, 113 fynd). Kommunen har bara 2 fynd. För fler: Artdatabankens SOS-API (kräver nyckel) | Nej (SOS: ja) | < 1 MB |
| 7 | Bakgrundskarta | OpenFreeMap-stilen `liberty` i MapLibre. OSM-rutor går bra vid låg trafik om villkoren följs | Nej | – |

**Kräver konto:**
- Lantmäteriets höjddata och administrativa gränser (Geotorget, Basic auth)
- Skogsstyrelsens REST-tjänster på `geodata.skogsstyrelsen.se`
- Artdatabankens SOS-API (prenumerationsnyckel)
- GBIF:s asynkrona nedladdningar

Inget av detta behövs för de rekommenderade vägarna.
