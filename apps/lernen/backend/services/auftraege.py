"""Einen Trainingslauf beauftragen - und nachsehen, was daraus geworden ist.

Ein Auftrag ist ein Verzeichnis (`wortlaut/laeufe.py`), kein Funktionsaufruf.
Diese Datei schreibt es und liest es wieder; gerechnet wird anderswo, in einem
Container mit Karte.

**Was im Verzeichnis steht, bevor der Trainer es anfasst.** Der Auftrag - wer,
womit, wie - und das Manifest: jede Probe mit ihrem Pfad, ihrem Text, ihrer
Herkunft und ihrem Teil der Aufteilung. Das Manifest ist der Schnappschuss:
Ab hier steht fest, womit trainiert wird, auch wenn derselbe Mensch in der
nächsten Stunde zwanzig weitere Aufnahmen macht. Ohne diesen Schnitt wäre
hinterher nicht mehr zu sagen, worauf ein Modell eigentlich gelernt hat.

**Warum die Testaufnahmen mit im Manifest stehen.** Sie werden nicht
trainiert - ihr `split` sagt es, und der Trainer hält sich daran. Sie stehen
darin, weil der Lauf sie am Ende braucht: Das fertige Modell hört sie noch
einmal, und was dabei herauskommt, ist die Zahl, die den Lauf beurteilt. Sie
zweimal zusammenzustellen - einmal zum Trainieren, einmal zum Prüfen - hieße,
zwei Stellen zu haben, an denen sich die Auswahl unterscheiden kann.

**Warum je Fassung eine Zeile.** „hören" legt neben jede Aufnahme drei
abgewandelte Fassungen (`wortlaut/augmentierung.py`). Ob sie mittrainiert
werden, ist die zweite Frage dieser App und steht im Auftrag (`daten`).
Geprüft wird dagegen **immer** auf allen vier - dieselben vier, die in der
Auswertung von „hören" schon gemessen wurden. Nur so ist die Grundlinie eine
Grundlinie und kein anderer Versuch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session
from wortlaut import augmentierung, corpus, ids, laeufe

from apps.hoeren.backend.db.models import Textquelle
from apps.lernen.backend.services.aufteilung import Probe

# Womit eine Probe zählt. Korrekturen stammen aus „schreiben": Ihr Text ist
# keine Vorgabe, sondern eine vom Menschen abgenickte Maschinenausgabe. Wer sie
# gleichrangig einspeist, trainiert dem Modell seine eigenen Fehler an.
GEWICHTE = {"vorlage": 1.0, "korrektur": 0.5}


@dataclass(frozen=True)
class Auftrag:
    """Was bestellt wurde - die Felder, die `auftrag.json` trägt."""

    sprecher_id: str
    methode: str
    daten: str
    basismodell: str


def _quelle_von(korpus: Session, probe: Probe) -> str:
    """`vorlage` oder `korrektur` - woher der Text stammt, nicht die Aufnahme."""
    quelle = korpus.get(Textquelle, probe.vorlage.source_id)
    return "korrektur" if quelle is not None and quelle.art == "korrektur" else "vorlage"


def _fassungen(teil: str, daten: str) -> tuple[str, ...]:
    """Welche Fassungen einer Aufnahme in den Lauf gehören.

    Geprüft wird immer auf allen vieren, trainiert je nach Auftrag. Das ist
    kein Versehen, sondern der Punkt: Die zu vergleichenden Modelle
    unterscheiden sich in ihren Trainingsdaten und in nichts sonst - schon gar
    nicht in dem, woran sie gemessen werden.
    """
    if teil == laeufe.TEST or daten == laeufe.MIT_VARIANTEN:
        return augmentierung.VARIANTEN
    return (augmentierung.ORIGINAL,)


def _manifestzeile(
    probe: Probe, variante: str, quelle: str, sprecher_id: str
) -> dict[str, Any]:
    # Der Pfad steht relativ zum Korpus dieses Sprechers und nicht absolut:
    # Ein Schnappschuss soll sich auf eine andere Maschine kopieren lassen,
    # ohne dass jemand Pfade darin ersetzt.
    innerhalb = corpus.sprecher_relpfad(sprecher_id)
    voll = (
        probe.aufnahme.blob
        if variante == augmentierung.ORIGINAL
        else corpus.variante_relpfad(sprecher_id, probe.aufnahme.id, variante)
    )
    return {
        "audio": voll.removeprefix(f"{innerhalb}/"),
        "text": probe.vorlage.text,
        "quelle": quelle,
        "modus": probe.aufnahme.modus,
        "variante": variante,
        "dauer_s": probe.aufnahme.dauer_s,
        "gewicht": GEWICHTE.get(quelle, 1.0),
        "split": probe.teil,
        "recording_id": probe.aufnahme.id,
    }


def schreibe_manifest(
    ziel: Path, korpus: Session, proben: list[Probe], sprecher_id: str, daten: str
) -> dict[str, int]:
    """Das Manifest schreiben; gibt zurück, wie viele Zeilen je Teil entstanden."""
    gezaehlt = dict.fromkeys(laeufe.TEILE, 0)
    with ziel.open("w", encoding="utf-8") as datei:
        for probe in proben:
            quelle = _quelle_von(korpus, probe)
            for variante in _fassungen(probe.teil, daten):
                zeile = _manifestzeile(probe, variante, quelle, sprecher_id)
                datei.write(json.dumps(zeile, ensure_ascii=False) + "\n")
                gezaehlt[probe.teil] += 1
    return gezaehlt


def beauftrage(
    datenverzeichnis: Path,
    korpus: Session,
    proben: list[Probe],
    auftrag: Auftrag,
) -> laeufe.Lauf:
    """Einen Lauf anlegen: Verzeichnis, Marke, Manifest, Auftrag - in dieser Reihenfolge.

    Der Auftrag zuletzt, und das ist die ganze Verriegelung: Der Trainer
    erkennt einen offenen Lauf an `auftrag.json`. Läge die Datei zuerst da,
    könnte er ein halbes Manifest erwischen.
    """
    job_id = ids.neue_id("job")
    verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, job_id)
    verzeichnis.mkdir(parents=True, exist_ok=True)

    # Die Zusage an die Löschung - ohne sie findet `scripts/purge_speaker.py`
    # diesen Schnappschuss nicht und meldet ihn zur Prüfung von Hand.
    (verzeichnis / laeufe.SPRECHER_MARKE).write_text(
        f"{auftrag.sprecher_id}\n", encoding="utf-8"
    )

    gezaehlt = schreibe_manifest(
        verzeichnis / laeufe.MANIFEST, korpus, proben, auftrag.sprecher_id, auftrag.daten
    )

    laeufe.schreibe_json(
        verzeichnis / laeufe.AUFTRAG,
        {
            "job_id": job_id,
            "sprecher_id": auftrag.sprecher_id,
            "methode": auftrag.methode,
            "daten": auftrag.daten,
            "basismodell": auftrag.basismodell,
            "erstellt": laeufe.jetzt(),
            "zeilen": gezaehlt,
            "aufnahmen": len(proben),
        },
    )

    lauf = laeufe.lies_lauf(datenverzeichnis, job_id)
    assert lauf is not None  # gerade selbst geschrieben
    return lauf


def brich_ab(datenverzeichnis: Path, job_id: str) -> bool:
    """Einen wartenden Lauf zurücknehmen. Ein laufender bleibt, was er ist.

    Einen laufenden abzubrechen hieße, in einen fremden Container hineinzugreifen
    - das kann diese App nicht, und so zu tun als ob wäre schlimmer als der
    fehlende Knopf. Wer einen laufenden stoppen will, stoppt den Trainer.
    """
    lauf = laeufe.lies_lauf(datenverzeichnis, job_id)
    if lauf is None or not lauf.offen:
        return False
    laeufe.schreibe_json(
        lauf.verzeichnis / laeufe.ZUSTAND,
        {"status": laeufe.ABGEBROCHEN, "beendet": laeufe.jetzt()},
    )
    return True


def lernkurve(lauf: laeufe.Lauf) -> dict[str, list[dict[str, float]]]:
    """Was die Kurven zeigen: der Verlust je Schritt, die Prüfung je Durchgang.

    Zwei Reihen und nicht eine. Der Trainingsverlust sagt, ob überhaupt etwas
    passiert; er fällt auch dann weiter, wenn das Modell nur noch auswendig
    lernt. Erst die Validierung daneben zeigt, wann das anfängt - sie ist die
    Reihe, die wieder steigt, während die andere sinkt.
    """
    schritte = []
    pruefungen = []
    for zeile in laeufe.lies_zeilen(lauf.verzeichnis / laeufe.FORTSCHRITT):
        art = zeile.get("art")
        if art == "schritt":
            schritte.append(zeile)
        elif art == "validierung":
            pruefungen.append(zeile)
    return {"training": schritte, "validierung": pruefungen}
