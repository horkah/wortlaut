"""Die Geschwindigkeit suchen, bei der dieser Sprecher am besten verstanden wird.

**Woher die Frage kommt.** Dysarthrische Sprache ist oft stark verlangsamt.
Vorgespult versteht Whisper sie messbar besser - gemessen an einem echten
Korpus im September 2026, deutlich, wenn auch nicht dramatisch. Nur ist „2,0"
dabei kein Naturgesetz, sondern der erste Wert, den jemand ausprobiert hat.
Das Optimum hängt am Sprecher, und es zu raten wäre schade um die Messung.

**Warum nicht einfach je Faktor einmal trainieren.** Das wäre die ehrliche
Antwort und die teuerste: Bei acht Faktoren und sechs Faltungen sind es
achtundvierzig Trainings statt sechs. Ein Lauf von einer Stunde würde zu acht.

**Was stattdessen gemessen wird.** Das unveränderte Grundmodell, auf einer
Stichprobe der Lernzeilen dieser Faltung, bei jedem Faktor des Rasters. Das
kostet je Faktor einen Dekodierdurchgang über wenige Dutzend Aufnahmen - auf
der Karte zusammen etwa eine Minute je Faltung.

**Und was das ist: ein Stellvertreter, kein Beweis.** Gemessen wird, wie gut
das Grundmodell diesen Sprecher bei Tempo x versteht; gesucht ist, bei welchem
Tempo das *feingetunte* Modell ihn am besten versteht. Das ist nicht
dasselbe. Die Annahme dahinter ist, dass ein besserer Ausgangspunkt auch nach
dem Feintuning besser bleibt - plausibel, weil das Feintuning an denselben
Gewichten ansetzt, aber nicht bewiesen. Wer es genau wissen will, beauftragt
zwei Läufe mit festen Faktoren und vergleicht sie in der Tafel; dafür ist die
Tafel da.

**Warum je Faltung und nicht einmal für den ganzen Lauf.** Weil die Wahl sonst
Daten sähe, an denen später gemessen wird. Ein einziger Zahlenwert aus acht
Möglichkeiten ist wenig Leck, aber „wenig Leck" ist keine Kategorie, die
dieses Projekt führt. Je Faltung gewählt, auf deren eigenen Lernzeilen, ist es
gar keins - und das Endmodell nimmt den Median der sechs mit, genau wie bei
den Durchgängen und beim α (`finetune.kreuzvalidiere`).

**Warum ein grobes Raster und keine feine Suche.** Über zwei Dutzend Aufnahmen
ist der WER selbst eine Zufallsgröße. Eine Suche, die auf 0,05 genau optimiert,
optimiert das Rauschen - sie fände bei einer zweiten Stichprobe einen anderen
Wert und sähe dabei genauso überzeugt aus. Acht Stützstellen sagen, in welcher
Gegend das Optimum liegt, und mehr ist ehrlicherweise nicht drin.
"""

from __future__ import annotations

import math
import random
import statistics
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wortlaut import laeufe, metriken, tempo
from wortlaut.augmentierung import ORIGINAL

# Die Stützstellen. Unten dicht, oben weit: Zwischen 1,0 und 2,0 entscheidet
# sich erfahrungsgemäß alles, darüber wird es schnell schlechter, und dort
# genügt es zu wissen, *dass* es schlechter wird.
RASTER = (0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)

# Was dazukommt, **wenn** der Sieger ganz oben steht.
#
# Ein Optimum am Rand des Rasters ist keines - es ist die Auskunft, dass zu
# kurz gesucht wurde. Genau das war im September 2026 der Fall: Die Kurve fiel
# über alle acht Stützstellen bis 3,0 durch und hörte dort auf, weil das
# Raster aufhörte. Nachgelegt wird deshalb, solange der Rand gewinnt - und
# höchstens bis zur Grenze, die `wortlaut/tempo.py` zieht.
#
# Das kostet im Regelfall nichts: Nur wer wirklich am Rand landet, zahlt zwei
# weitere Dekodierdurchgänge.
ERWEITERUNG = (3.5, 4.0)

# Wie viele Aufnahmen je Faktor gehört werden. Zwei Dutzend sind genug, um
# eine Gegend zu erkennen, und wenig genug, dass acht Faktoren zusammen unter
# einer Minute bleiben. Sind weniger da, werden eben alle genommen.
PROBEN = 24

# Der Würfel ist fest: Dieselbe Faltung zieht auf jeder Maschine dieselbe
# Stichprobe. Ohne das wäre ein wiederholter Lauf keine Wiederholung.
KEIM = 8_1_2026


@dataclass(frozen=True)
class Ergebnis:
    """Was die Suche gefunden hat - für Protokoll, Stand und Vergleichstafel."""

    faktor: float
    # Je Faktor sein WER - die Kurve hinter der Wahl. Ohne sie ist die Zahl
    # oben nicht zu beurteilen: Ein Optimum, das sich vom Nachbarn um ein
    # Promille unterscheidet, ist keines.
    versuche: tuple[tuple[float, float], ...] = ()
    # Wie viele Aufnahmen je Faktor gehört wurden.
    proben: int = 0
    # Warum weniger passiert ist als vorgesehen. Leer heißt: alles wie geplant.
    hinweis: str = ""

    def als_dict(self) -> dict[str, Any]:
        return {
            "faktor": self.faktor,
            "versuche": [list(paar) for paar in self.versuche],
            "proben": self.proben,
            "hinweis": self.hinweis,
        }


def zusammengelegt(faltungen: list[dict[str, Any]]) -> tuple[float | None, list[dict[str, Any]]]:
    """Aus den Kurven aller Faltungen **eine** machen - und daraus den Faktor.

    **Warum nicht der Median der Sieger.** So war es zuerst, und es verschenkte
    die Daten. Eine einzelne Faltung hört sechzehn bis zwei Dutzend Aufnahmen;
    ihr Sieger ist damit weitgehend Zufall. An einem echten Korpus im September
    2026 wählten die sechs Faltungen 2,0 · 3,0 · 3,0 · 3,0 · 2,5 · 3,0, Median
    also 2,75 - ein Wert, den keine Faltung je gemessen hatte. Legt man
    dieselben sechs Kurven übereinander, fällt die gemittelte Kurve glatt und
    ohne Ausreißer bis zum Rand durch, und das Minimum liegt eindeutig bei 3,0.

    Die Zahlen liegen ohnehin vor. Sie wurden nur falsch verdichtet.

    **Die Streuung steht dabei.** Der Abstand zwischen den beiden besten
    Faktoren betrug dort 4,8 %, die Streuung derselben Stützstelle zwischen den
    Faltungen 6,8 % - der Sieger war also von seinem Nachbarn nicht zu
    unterscheiden. Wer das nicht danebenstehen hat, hält eine Zufallszahl für
    ein Ergebnis. Als `unklar` markiert ist jeder Faktor, der innerhalb eines
    Standardfehlers des besten liegt.
    """
    kurven: list[dict[float, float]] = []
    for faltung in faltungen:
        versuche = (faltung.get("tempowahl") or {}).get("versuche") or []
        if versuche:
            kurven.append({float(a): float(b) for a, b in versuche})
    if not kurven:
        return None, []

    # Nur Stützstellen, die **jede** Kurve hat: Die Erweiterung wird nur dort
    # gemessen, wo der Rand gewann, und ein Mittel über verschieden viele
    # Faltungen wäre kein Mittel.
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

    **Nur das Original.** Die abgewandelten Fassungen beantworten eine andere
    Frage (verträgt das Modell Rauschen?) und würden hier nur die Stichprobe
    verdünnen.
    """
    original = [zeile for zeile in zeilen if str(zeile.get("variante")) == ORIGINAL]
    if len(original) <= PROBEN:
        return original
    wuerfel = random.Random(KEIM + (faltung or 0))
    return wuerfel.sample(original, PROBEN)


def waehle(
    zeilen: list[dict[str, Any]],
    korpuswurzel: Path,
    basismodell: str,
    sprache: str,
    bericht,
    faltung: int | None = None,
) -> Ergebnis:
    """Den Faktor mit dem kleinsten WER am Grundmodell; `1.0`, wenn nichts geht.

    Scheitert die Suche - kein Audio, kein Modell, keine Karte -, ist das kein
    Grund, den Lauf hinzuwerfen: Dann gilt 1,0, der Stand von immer, und der
    Hinweis sagt, warum. Ein Training, das an der Vorbereitung einer Wahl
    stirbt, die es auch ohne täte, wäre die schlechteste aller Antworten.
    """
    from wortlaut.whisper.local import LokalerTranskriptor

    from .finetune import raeume_karte

    proben = stichprobe(zeilen, faltung)
    if not proben:
        return Ergebnis(faktor=tempo.VORGABE, hinweis="Keine Originalaufnahmen zur Wahl.")

    from apps.lernen.backend.config import einstellungen

    geraet, rechenart = einstellungen().rechenwerk()
    # Das **unveränderte** Grundmodell unter seinem kurzen Namen - genau das,
    # was `hören` in der Auswertung misst und was am Anfang jedes Feintunings
    # steht.
    erkenner = LokalerTranskriptor(
        laeufe.kurzname(basismodell), geraet=geraet, rechenart=rechenart
    )

    # Eine eigene Stufe, und nicht mehr stillschweigend unter „laden".
    #
    # Die Suche dauert rund eine Minute je Faltung - acht Dekodierdurchgänge
    # über zwei Dutzend Aufnahmen. Solange stand in der Übersicht „Modell wird
    # geladen", und das war schlicht falsch: Das Modell war längst geladen, es
    # rechnete nur etwas anderes. Eine Stufe, die eine Minute lang das Falsche
    # behauptet, ist schlimmer als gar keine.
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
            # Der Balken bewegt sich auch hier. Acht Schritte sind wenige, aber
            # sie sind gezählt - und ein Balken, der eine Minute lang stillsteht,
            # sieht aus wie ein Lauf, der hängt (`laeufe.Lauf.haengt`).
            bericht.schritt(erledigt, erledigt + len(offen))
            miss(faktor)
            # Nachlegen, solange der Rand gewinnt: Ein Minimum an der obersten
            # Stützstelle sagt nichts über das Minimum, sondern über das Raster.
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
