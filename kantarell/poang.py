"""Poängreglerna: hur sannolikt det är att hitta kantareller i en ruta (Saida: DO-2, DO-4, DO-5).

Varje faktor ger ett värde mellan 0 och 1 ur rutans data. Sannolikheten är det viktade medelvärdet av faktorerna,
men en faktor som nästan utesluter kantareller (ett färskt hygge, torv, kalfjäll) begränsar rutan: poängen blir aldrig
högre än den faktorn. Saknas data för en faktor räknas den bort och rutan markeras. Utan trädslag är rutan inte skog.

Funktionerna här är rena (inga filer, inget nätverk) så att reglerna kan testas med påhittade rutor.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Faktorernas vikt i medelvärdet. Justeras efter fynden i Artportalen.
VIKTER = {"tradslag": 0.30, "alder": 0.30, "jordart": 0.15, "fukt": 0.15, "hojd": 0.10}
# Under den här nivån begränsar en faktor hela rutan.
BEGRANSANDE = 0.15

# Jordarter, grupperade ur SGU:s jordartskarta (kod i kartfilerna → namn och värde).
JORDARTER: dict[int, tuple[str, float]] = {
    1: ("morän", 1.0),
    2: ("sand", 0.9),
    3: ("grus", 0.8),
    4: ("silt", 0.5),
    5: ("lera", 0.2),
    6: ("torv", 0.0),
    7: ("berg i dagen", 0.3),
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
    """Gran och tall ger hög poäng, gärna med inslag av björk (5–30 %)."""
    if r.gran is None and r.tall is None:
        return None
    barr = (r.gran or 0) + (r.tall or 0)
    v = ramp(barr, 20, 80)
    if r.bjork is not None and 5 <= r.bjork <= 30:
        v = min(1.0, v + 0.1)
    return v


def alder(r: Ruta) -> float | None:
    """Ålder räknas som trädhöjd och avverkningar (beslutet i KS-5): hög skog utan sentida avverkning ger hög poäng."""
    if r.ar_sedan_avverkning is not None and r.ar_sedan_avverkning < 30:
        return 0.0 if r.ar_sedan_avverkning < 10 else 0.3
    if r.tradhojd is None:
        return None
    return ramp(r.tradhojd, 5, 15)


def jordart(r: Ruta) -> float | None:
    if r.jordart is None or r.jordart not in JORDARTER:
        return None
    return JORDARTER[r.jordart][1]


def fukt(r: Ruta) -> float | None:
    if r.fukt is None or r.fukt not in FUKTKLASSER:
        return None
    return FUKTKLASSER[r.fukt][1]


def hojd(r: Ruta) -> float | None:
    """Under trädgränsen har höjden liten betydelse; närmare fjället sjunker poängen."""
    if r.hojd is None:
        return None
    return ramp(r.hojd, 900, 700)


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
