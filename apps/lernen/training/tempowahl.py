"""Die Geschwindigkeit suchen, bei der dieser Sprecher am besten verstanden wird.

Dysarthrische Sprache ist oft stark verlangsamt, und vorgespult versteht
Whisper sie messbar besser. Das Optimum hängt am Sprecher.

**Gemessen am Grundmodell**, auf einer Stichprobe der Lernzeilen der Faltung,
je Faktor ein Dekodierdurchgang - etwa eine Minute je Faltung statt acht
Trainings je Faktor. Ein Stellvertreter: Gesucht ist das Tempo des
*feingetunten* Modells, angenommen wird, dass ein besserer Ausgangspunkt
besser bleibt. Zwei Läufe mit festen Faktoren prüfen das in der Tafel.

**Je Faltung**, auf deren Lernzeilen - die Wahl sieht nichts, woran gemessen
wird. Das Endmodell nimmt das Minimum der zusammengelegten Kurven
(`zusammengelegt`, `finetune.kreuzvalidiere`).

**Ein grobes Raster:** Über zwei Dutzend Aufnahmen ist der WER selbst eine
Zufallsgröße; feiner optimierte das Rauschen.
"""

from __future__ import annotations

import math
import random
import statistics
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wortlaut import metriken, tempo
from wortlaut.text import chunker
from wortlaut.augmentierung import ORIGINAL

# Unten dicht, oben weit: Zwischen 1,0 und 2,0 entscheidet sich das meiste.
RASTER = (0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)

# Nachgelegt, solange der oberste Faktor gewinnt - ein Optimum am Rand ist
# keines. Höchstens bis `tempo.SPANNE`.
ERWEITERUNG = (3.5, 4.0)

# Aufnahmen je Faktor: genug für eine Gegend, wenig genug für eine Minute.
PROBEN = 24

# Fest, damit eine Faltung überall dieselbe Stichprobe zieht.
KEIM = 8_1_2026


@dataclass(frozen=True)
class Ergebnis:
    """Was die Suche gefunden hat - für Protokoll, Stand und Vergleichstafel."""

    faktor: float
    # `gesucht` oder `geschaetzt` - welches Verfahren diesen Faktor fand.
    art: str = "gesucht"
    # Nur bei `geschaetzt`: die beiden Summen und ihr ungerundetes Verhältnis.
    ton_s: float | None = None
    text_s: float | None = None
    roh: float | None = None
    # Je Faktor sein WER - die Kurve hinter der Wahl.
    versuche: tuple[tuple[float, float], ...] = ()
    # Wie viele Aufnahmen je Faktor gehört wurden.
    proben: int = 0
    # Warum weniger geschah als vorgesehen.
    hinweis: str = ""

    def als_dict(self) -> dict[str, Any]:
        return {
            "faktor": self.faktor,
            "art": self.art,
            "ton_s": self.ton_s,
            "text_s": self.text_s,
            "roh": self.roh,
            "versuche": [list(paar) for paar in self.versuche],
            "proben": self.proben,
            "hinweis": self.hinweis,
        }


# Luftholen und Stille an den Rändern - grob, verschiebt aber weniger als eine Viertelstufe.
ZUSCHLAG_S = 1.0

# Auf welches Raster der geschätzte Faktor gerundet wird.
STUFE = 0.25


def auf_stufe(faktor: float) -> float:
    """Auf die nächste Viertelstufe, innerhalb der erlaubten Spanne."""
    gerundet = round(float(faktor) / STUFE) * STUFE
    return round(tempo.in_spanne(gerundet), 2)


def aus_dauern(zeilen: list[dict[str, Any]], bericht) -> Ergebnis:
    """Den Faktor aus Textlänge und Aufnahmedauer rechnen - ohne eine Erkennung.

    Aufnahmedauer durch geschätzte Sprechdauer (`chunker.dauer`) ist das
    Tempo. Über die Summen der Faltung, damit Pausen einzelner Sätze und kurze
    Aufnahmen nicht überwiegen. Misst die Abweichung von der Norm, nicht das
    Verstehen - das sucht `optimal`.

    Kostet nichts: keine Erkennung, kein Modell, keine Karte. Nur Arithmetik
    über Zeilen, die ohnehin gelesen sind.
    """
    original = [zeile for zeile in zeilen if str(zeile.get("variante")) == ORIGINAL]
    ton = sum(float(zeile.get("dauer_s") or 0.0) for zeile in original)
    text = sum(
        chunker.dauer(str(zeile.get("text") or "")) + ZUSCHLAG_S for zeile in original
    )
    if not original or ton <= 0 or text <= 0:
        return Ergebnis(
            faktor=tempo.VORGABE,
            art="geschaetzt",
            hinweis="Keine brauchbaren Dauern - 1,0 gilt.",
        )

    roh = ton / text
    faktor = auf_stufe(roh)
    bericht.sage(
        f"  Tempo geschätzt: {ton:.0f} s Ton auf {text:.0f} s Text "
        f"({len(original)} Aufnahmen) → {roh:.2f} → {faktor:g}"
    )
    return Ergebnis(
        faktor=faktor,
        art="geschaetzt",
        proben=len(original),
        ton_s=round(ton, 1),
        text_s=round(text, 1),
        roh=round(roh, 4),
    )


def zusammengelegt(faltungen: list[dict[str, Any]]) -> tuple[float | None, list[dict[str, Any]]]:
    """Aus den Kurven aller Faltungen **eine** machen - und daraus den Faktor.

    Der Sieger einer Faltung über zwei Dutzend Aufnahmen ist weitgehend
    Zufall, und ein Median der Sieger kann ein nie gemessener Wert sein. Die
    gemittelte Kurve ist glatter. `unklar` ist jeder Faktor innerhalb eines
    Standardfehlers des besten - von ihm nicht zu unterscheiden.
    """
    kurven: list[dict[float, float]] = []
    for faltung in faltungen:
        versuche = (faltung.get("tempowahl") or {}).get("versuche") or []
        if versuche:
            kurven.append({float(a): float(b) for a, b in versuche})
    if not kurven:
        return None, []

    # Nur Stützstellen jeder Kurve - die Erweiterung fehlt manchen.
    gemeinsam = sorted(set.intersection(*(set(kurve) for kurve in kurven)))
    if not gemeinsam:
        return None, []

    punkte = []
    for faktor in gemeinsam:
        werte = [kurve[faktor] for kurve in kurven]
        mittel = sum(werte) / len(werte)
        if len(werte) > 1:
            streuung = statistics.stdev(werte) / math.sqrt(len(werte))
        else:
            streuung = 0.0
        punkte.append({"faktor": faktor, "wer": round(mittel, 5), "fehler": round(streuung, 5)})

    bester = min(punkte, key=lambda punkt: punkt["wer"])
    grenze = bester["wer"] + bester["fehler"]
    for punkt in punkte:
        punkt["unklar"] = punkt["wer"] <= grenze and punkt["faktor"] != bester["faktor"]
    return float(bester["faktor"]), punkte


def stichprobe(zeilen: list[dict[str, Any]], faltung: int | None) -> list[dict[str, Any]]:
    """Ein paar Lernzeilen dieser Faltung - im Original und gewürfelt, aber fest.

    Nur Originale - Abwandlungen fragen etwas anderes.
    """
    original = [zeile for zeile in zeilen if str(zeile.get("variante")) == ORIGINAL]
    if len(original) <= PROBEN:
        return original
    wuerfel = random.Random(KEIM + (faltung or 0))
    return wuerfel.sample(original, PROBEN)


def waehle(
    zeilen: list[dict[str, Any]],
    korpuswurzel: Path,
    modell: str,
    sprache: str,
    bericht,
    faltung: int | None = None,
) -> Ergebnis:
    """Den Faktor mit dem kleinsten WER am Grundmodell; `1.0`, wenn nichts geht.

    `modell` ist, was faster-whisper laden soll: der kurze Name des
    Grundmodells oder das Verzeichnis eines Ausgangsstands
    (`ausgangsstand.erkenner`).

    Scheitert die Suche, gilt 1,0 und der Hinweis sagt warum - der Lauf geht weiter.
    """
    from wortlaut.whisper.local import LokalerTranskriptor

    from .finetune import raeume_karte

    proben = stichprobe(zeilen, faltung)
    if not proben:
        return Ergebnis(faktor=tempo.VORGABE, hinweis="Keine Originalaufnahmen zur Wahl.")

    from apps.lernen.backend.config import einstellungen

    geraet, rechenart = einstellungen().rechenwerk()
    # Das Modell am Anfang des Feintunings: Grundmodell oder Ausgangsstand.
    erkenner = LokalerTranskriptor(modell, geraet=geraet, rechenart=rechenart)

    # Eine eigene Stufe, damit die Übersicht sagt, was die Minute füllt.
    bericht.stufe("tempowahl")
    bericht.sage(f"  Tempowahl: {len(proben)} Aufnahmen × {len(RASTER)} Faktoren")
    versuche: list[tuple[float, float]] = []

    def miss(faktor: float) -> float:
        werte = [
            metriken.bewerte(
                str(zeile["text"]),
                _erkenne(erkenner, korpuswurzel / str(zeile["audio"]), faktor, sprache),
            ).wer
            for zeile in proben
        ]
        mittel = sum(werte) / len(werte)
        versuche.append((faktor, round(mittel, 5)))
        bericht.sage(f"    Faktor {faktor:4.2f} · WER {mittel:.4f}")
        return mittel

    try:
        offen = [*RASTER]
        erledigt = 0
        while offen:
            faktor = offen.pop(0)
            erledigt += 1
            # Gezählt, damit der Balken nicht hängend aussieht.
            bericht.schritt(erledigt, erledigt + len(offen))
            miss(faktor)
            # Nachlegen, solange der Rand gewinnt (`ERWEITERUNG`).
            if not offen and versuche:
                bester = min(versuche, key=lambda paar: paar[1])[0]
                gemessen = {paar[0] for paar in versuche}
                weiter = [
                    kandidat
                    for kandidat in ERWEITERUNG
                    if kandidat not in gemessen and kandidat <= tempo.SPANNE[1]
                ]
                if weiter and bester >= max(gemessen):
                    bericht.sage(f"    Sieger am Rand ({bester:g}) - lege {weiter[0]:g} nach")
                    offen.append(weiter[0])
    except Exception as ursache:  # noqa: BLE001 - eine Wahl darf scheitern
        erkenner.entlade()
        raeume_karte(bericht)
        return Ergebnis(
            faktor=tempo.VORGABE,
            versuche=tuple(versuche),
            proben=len(proben),
            hinweis=f"Tempowahl abgebrochen ({type(ursache).__name__}: {ursache}); 1,0 gilt.",
        )
    finally:
        erkenner.entlade()

    raeume_karte(bericht)
    bester = min(versuche, key=lambda paar: paar[1])[0]
    bericht.sage(f"  Gewählt: Faktor {bester:g}")
    return Ergebnis(faktor=bester, versuche=tuple(versuche), proben=len(proben))


def _erkenne(erkenner, wav: Path, faktor: float, sprache: str) -> str:
    """Eine Aufnahme bei diesem Faktor durch das Grundmodell schicken."""
    if not tempo.vorspulen_noetig(faktor):
        return erkenner.transkribiere(wav, sprache=sprache).text
    with tempfile.TemporaryDirectory() as verzeichnis:
        schnell = Path(verzeichnis) / "vorgespult.wav"
        tempo.spule_vor(wav, schnell, faktor)
        return erkenner.transkribiere(schnell, sprache=sprache).text
