"""Poängreglerna: hur sannolikt det är att hitta kantareller i en ruta (Saida: DO-2, DO-4, DO-5).

Varje faktor ger ett värde mellan 0 och 1 ur rutans data. Sannolikheten är det viktade medelvärdet av faktorerna,
men en faktor som nästan utesluter kantareller (ett färskt hygge, torv, kalfjäll) begränsar rutan: poängen blir aldrig
högre än den faktorn. Saknas data för en faktor räknas den bort och rutan markeras. Utan trädslag är rutan inte skog.
Reglerna är desamma i alla län, utom trädhöjden som ger full ålderspoäng (ALDER_HOJD_LAN).

Funktionerna här är rena (inga filer, inget nätverk) så att reglerna kan testas med påhittade rutor.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Faktorernas vikt i medelvärdet. Justeras efter fynden i Artportalen; i varv 5 (KS-12) väger åldern mer, efter fynden i
# Södermanland (0,30/0,30/0,15 före).
VIKTER = {"tradslag": 0.25, "alder": 0.40, "jordart": 0.10, "fukt": 0.15, "hojd": 0.10}
# Under den här nivån begränsar en faktor hela rutan.
BEGRANSANDE = 0.15
# Tall räknas som halv gran i trädslaget, och höjden sänker poängen mellan 800 och 1000 m (varv 3, KS-9): fynden i länet
# har mer gran och mindre tall än skogen i stort och ligger högre. Med tall 0,5 hamnar 32 % av fynden bland de 30 %
# bästa rutorna (27 % före); 0,25 gav 42 %, men fynden är få och skeva, så steget är försiktigt.
TALL_VIKT = 0.5
HOJD_FULL, HOJD_NOLL = 800, 1000
# Åldern ökar med trädhöjden mellan de här höjderna (m). I Södermanland står fynden i högre skog än i länet i stort
# (hälften där träden är minst 20 m, mot en femtedel av skogen), men en senare tröskel gör Jämtland sämre (varv 5, KS-12).
ALDER_HOJD = (5, 15)
ALDER_HOJD_LAN = {"04": (10, 25)}

# Jordarter, grupperade ur SGU:s jordartskarta (kod i kartfilerna → namn och värde). Sand, grus och berg i dagen höjdes
# i varv 5 (KS-12): fynden i Södermanland ligger oftare där än skogen i stort (sand 0,9, grus 0,8, berg 0,3 före).
JORDARTER: dict[int, tuple[str, float]] = {
    1: ("morän", 1.0),
    2: ("sand", 1.0),
    3: ("grus", 1.0),
    4: ("silt", 0.5),
    5: ("lera", 0.2),
    6: ("torv", 0.0),
    7: ("berg i dagen", 0.8),
    8: ("annat", 0.4),
}
# Markfuktighet i klasser ur markfuktighetskartan.
FUKTKLASSER: dict[int, tuple[str, float]] = {
    1: ("torr", 0.5),
    2: ("frisk", 1.0),
    3: ("fuktig", 0.6),
    4: ("blöt", 0.1),
}


@dataclass
class Ruta:
    """Det som är känt om en ruta. None betyder att data saknas."""
    gran: float | None = None          # andel av volymen, procent
    tall: float | None = None
    bjork: float | None = None
    tradhojd: float | None = None      # medelhöjd i meter
    ar_sedan_avverkning: int | None = None  # år sedan slutavverkning; None om ingen känd
    jordart: int | None = None         # kod i JORDARTER
    fukt: int | None = None            # kod i FUKTKLASSER
    hojd: float | None = None          # meter över havet
    lan: str | None = None             # länskoden, t.ex. "04" (styr ALDER_HOJD_LAN)


@dataclass
class Bedomning:
    poang: float | None                # 0–1, None om rutan inte är skog
    faktorer: dict[str, float | None] = field(default_factory=dict)
    begransas_av: str | None = None
    saknas: list[str] = field(default_factory=list)


def ramp(x: float, fran: float, till: float) -> float:
    """0 vid fran, 1 vid till, linjärt emellan (fungerar åt båda hållen)."""
    if fran == till:
        return 1.0 if x >= till else 0.0
    t = (x - fran) / (till - fran)
    return max(0.0, min(1.0, t))


def tradslag(r: Ruta) -> float | None:
    """Gran ger hög poäng, tall hälften så mycket (TALL_VIKT), gärna med inslag av björk (5–30 %)."""
    if r.gran is None and r.tall is None:
        return None
    barr = (r.gran or 0) + TALL_VIKT * (r.tall or 0)
    v = ramp(barr, 20, 80)
    if r.bjork is not None and 5 <= r.bjork <= 30:
        v = min(1.0, v + 0.1)
    return v


def alder_hojd(lan: str | None) -> tuple[float, float]:
    """Trädhöjderna där åldern går från 0 till full poäng i länet."""
    return ALDER_HOJD_LAN.get(lan, ALDER_HOJD)


def alder(r: Ruta) -> float | None:
    """Ålder räknas som trädhöjd och avverkningar (beslutet i KS-5): hög skog utan sentida avverkning ger hög poäng."""
    if r.ar_sedan_avverkning is not None and r.ar_sedan_avverkning < 30:
        return 0.0 if r.ar_sedan_avverkning < 10 else 0.3
    if r.tradhojd is None:
        return None
    return ramp(r.tradhojd, *alder_hojd(r.lan))


def jordart(r: Ruta) -> float | None:
    if r.jordart is None or r.jordart not in JORDARTER:
        return None
    return JORDARTER[r.jordart][1]


def fukt(r: Ruta) -> float | None:
    if r.fukt is None or r.fukt not in FUKTKLASSER:
        return None
    return FUKTKLASSER[r.fukt][1]


def hojd(r: Ruta) -> float | None:
    """Under trädgränsen har höjden liten betydelse; närmare fjället (HOJD_FULL–HOJD_NOLL) sjunker poängen."""
    if r.hojd is None:
        return None
    return ramp(r.hojd, HOJD_NOLL, HOJD_FULL)


FAKTORER = {"tradslag": tradslag, "alder": alder, "jordart": jordart, "fukt": fukt, "hojd": hojd}


def bedom(r: Ruta) -> Bedomning:
    """Sannolikheten för rutan: viktat medelvärde, begränsat av en faktor som nästan utesluter kantareller."""
    v = {namn: f(r) for namn, f in FAKTORER.items()}
    if v["tradslag"] is None:
        return Bedomning(poang=None, faktorer=v, saknas=[k for k, x in v.items() if x is None])
    kanda = {k: x for k, x in v.items() if x is not None}
    medel = sum(VIKTER[k] * x for k, x in kanda.items()) / sum(VIKTER[k] for k in kanda)
    lagst_namn, lagst = min(kanda.items(), key=lambda kv: kv[1])
    begransas = lagst_namn if lagst < BEGRANSANDE and lagst < medel else None
    poang = min(medel, lagst) if begransas else medel
    return Bedomning(poang=round(poang, 3), faktorer=v, begransas_av=begransas, saknas=[k for k, x in v.items() if x is None])


# ---------- Samma regler för hela rutnätet på en gång ----------
# bedom() går ruta för ruta och är lätt att läsa och testa; för ett helt län (miljontals rutor) räknas samma regler
# med numpy. Testet test_falten_ger_samma_svar_som_bedom håller dem lika.

def _ramp(x, fran: float, till: float):
    import numpy as np
    return np.clip((x - fran) / (till - fran), 0.0, 1.0)


def _tabell(kod, tabell: dict[int, tuple[str, float]]):
    import numpy as np
    ut = np.full(kod.shape, np.nan)
    for k, (_, v) in tabell.items():
        ut[kod == k] = v
    return ut


def bedom_falt(d: dict, lan: str | None = None) -> dict:
    """bedom() för arrayer: d har gran, tall, bjork, tradhojd, ar_sedan_avverkning, jordart, fukt och hojd (NaN = saknas),
    alla i länet lan. Ger poang och f_<faktor> som arrayer (NaN = saknas; poang är NaN där rutan inte är skog)."""
    import numpy as np
    gran, tall, bjork = d["gran"], d["tall"], d["bjork"]
    ts = _ramp(np.nan_to_num(gran) + TALL_VIKT * np.nan_to_num(tall), 20, 80)
    ts = np.where((bjork >= 5) & (bjork <= 30), np.minimum(1.0, ts + 0.1), ts)
    ts = np.where(np.isnan(gran) & np.isnan(tall), np.nan, ts)
    avv = d["ar_sedan_avverkning"]
    al = np.where(avv < 30, np.where(avv < 10, 0.0, 0.3), _ramp(d["tradhojd"], *alder_hojd(lan)))
    f = {"tradslag": ts, "alder": al, "jordart": _tabell(d["jordart"], JORDARTER), "fukt": _tabell(d["fukt"], FUKTKLASSER),
         "hojd": _ramp(d["hojd"], HOJD_NOLL, HOJD_FULL)}
    summa = sum(np.nan_to_num(f[k]) * VIKTER[k] for k in f)
    vikt = sum(np.where(np.isnan(f[k]), 0.0, VIKTER[k]) for k in f)
    medel = summa / vikt
    lagst = np.fmin.reduce([f[k] for k in f])
    poang = np.where((lagst < BEGRANSANDE) & (lagst < medel), lagst, medel)
    poang = np.where(np.isnan(ts), np.nan, np.round(poang, 3))
    return {"poang": poang, **{f"f_{k}": v for k, v in f.items()}}
