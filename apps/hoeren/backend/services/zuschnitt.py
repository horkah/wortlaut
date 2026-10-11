"""Der Zuschnitt einer Aufnahme: die Datei auf das kürzen, was zählt.

Zwischen Knopfdruck und Stimme liegt Stille, die mittrainiert und mitgemessen
würde. Was geschnitten wird, entscheidet ein Mensch (`api/zuschnitt.py`); hier
steht, was mit der Datei geschieht.

**Ein Zuschnitt überschreibt die Aufnahme.** `recordings.blob` zeigt danach
auf die gekürzte Datei, und die Zeile beschreibt sie - Dauer, Pegel, Stille,
Hinweise. Eine zweite Fassung daneben gibt es nicht, also auch keine Frage,
welche gilt, und kein Zurück. Geschnitten wird verlustfrei: In 16 kHz mono PCM
ist ein Schnitt das Kopieren eines Byte-Bereichs, nach außen gerundet
(`audio.schneide_ausschnitt`, `nach_aussen=True`), ohne Blenden - geschnitten
wird in der Stille.

**Teilen ersetzt die Aufnahme.** Die Teile tragen die Kennungen aller
Vorfahren (`vorfahren`), das Original geht ganz (`entferne`).
"""

from __future__ import annotations

import json
import tempfile
import wave
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from wortlaut import audio as klang
from wortlaut import storage

from ..db.models import GUELTIG, Aufnahme, Erkennung, Vorlage
from . import quality


def schneide(
    ablage: storage.Ablage, aufnahme: Aufnahme, vorlage: Vorlage, start_s: float, ende_s: float
) -> klang.Befund:
    """Die Aufnahme auf [start, ende) kürzen und die Zeile nachführen.

    Die Datei wird ersetzt; Dauer, Pegel, Stille und Hinweise kommen aus der
    neuen. Die Messwerte am alten Ton räumt der Aufrufer weg.
    """
    quelle = _quelle(ablage, aufnahme, start_s, ende_s)
    befund = _schneide_ab(ablage, quelle, aufnahme.blob, start_s, ende_s)
    for feld, wert in asdict(befund).items():
        setattr(aufnahme, feld, wert)
    aufnahme.hinweise = json.dumps(
        quality.pruefe(befund, vorlage.dauer_geschaetzt_s), ensure_ascii=False
    )
    return befund


def reihenfolge() -> tuple:
    """Wie Aufnahmen der Reihe nach stehen: nach Datum, und bei gleichem Datum
    das Original vor seinen Teilen (`017_teilen.sql`).

    Für `order_by(*zuschnitt.reihenfolge())`; absteigend stehen die Teile vor
    dem Original, aber beieinander.
    """
    return (Aufnahme.erstellt, func.coalesce(Aufnahme.sortierschluessel, Aufnahme.id))


def stamm(aufnahme: Aufnahme) -> str:
    """Die Aufnahme, aus der diese zuerst hervorging - bei einer gewöhnlichen sie selbst.

    Die Klammer für die Faltungen: Teile liegen in der Faltung ihres
    Originals. Abzulesen am Sortierschlüssel: `rec_A.1.2` stammt aus `rec_A`,
    auch wenn `rec_A` gelöscht ist. Wer an wem nicht gemessen werden darf,
    sagen dagegen die `vorfahren`.
    """
    return (aufnahme.sortierschluessel or aufnahme.id).split(".", 1)[0]


def vorfahren(aufnahme: Aufnahme) -> list[str]:
    """Die Kennungen aller Aufnahmen, aus denen diese hervorging, älteste zuerst.

    Steht an der Aufnahme selbst und bleibt, wenn die Vorfahren längst
    gelöscht sind (`023_vorfahren.sql`).
    """
    return list(json.loads(aufnahme.vorfahren or "[]"))


def nachfahren_von(aufnahme: Aufnahme) -> str:
    """Die `vorfahren` eines Teils dieser Aufnahme, als JSON für die Spalte."""
    return json.dumps([*vorfahren(aufnahme), aufnahme.id])


def entferne(db: Session, aufnahme: Aufnahme) -> str:
    """Eine Aufnahme aus dem Bestand nehmen, samt Messwerten und - wenn sonst
    keine gültige Aufnahme an ihr hängt - ihrer Vorlage.

    Verworfene Zeilen derselben Vorlage gehen mit: Sie hielten die Vorlage
    fest, und die stünde dann wieder in der Warteschlange. Gibt den Pfad der
    Datei zurück; die löscht der Aufrufer nach dem Commit, damit keine Zeile
    ohne Datei zurückbleibt, wenn das Commit scheitert.
    """
    vorlage_id, blob = aufnahme.prompt_id, aufnahme.blob
    db.execute(delete(Erkennung).where(Erkennung.recording_id == aufnahme.id))
    db.delete(aufnahme)
    db.flush()
    an_der_vorlage = db.scalars(select(Aufnahme).where(Aufnahme.prompt_id == vorlage_id)).all()
    if not any(andere.status == GUELTIG for andere in an_der_vorlage):
        for andere in an_der_vorlage:
            db.execute(delete(Erkennung).where(Erkennung.recording_id == andere.id))
            db.delete(andere)
        if (vorlage := db.get(Vorlage, vorlage_id)) is not None:
            db.delete(vorlage)
    return blob


def geteilte_originale(db: Session) -> list[Aufnahme]:
    """Gültige Aufnahmen, die neben ihren eigenen Teilen stehen.

    Erkannt am Sortierschlüssel: Ein Teil von `rec_A` trägt `rec_A.1`, ein
    Teil von diesem `rec_A.1.1`. `teilen` lässt keine zurück; für ältere
    Bestände räumt `scripts/alte_originale.py` sie weg.
    """
    alle = db.scalars(select(Aufnahme)).all()
    schluessel = {aufnahme.sortierschluessel or aufnahme.id for aufnahme in alle}
    return [
        aufnahme
        for aufnahme in alle
        if aufnahme.status == GUELTIG
        and any(
            anderer.startswith(f"{aufnahme.sortierschluessel or aufnahme.id}.")
            for anderer in schluessel
        )
    ]


def teile(
    ablage: storage.Ablage,
    aufnahme: Aufnahme,
    start_s: float,
    teilung_s: float,
    ende_s: float,
    ziel_vorn: str,
    ziel_hinten: str,
) -> tuple[klang.Befund, klang.Befund]:
    """Aus dem Original zwei Dateien schneiden: [start, teilung) und [teilung, ende).

    Außen wird nach außen gerundet, die Teilung sitzt auf genau einem Rahmen -
    aneinandergelegt ergeben die Teile Byte für Byte den Bereich des Originals.

    Gibt die Befunde beider Teile zurück; abgelegt ist danach beides.
    """
    quelle = _quelle(ablage, aufnahme, start_s, ende_s)
    if not start_s < teilung_s < ende_s:
        raise klang.AudioFehler(
            "Die Teilung muss zwischen Anfang und Ende liegen "
            f"({start_s:.2f} < {teilung_s:.2f} < {ende_s:.2f} s)."
        )
    with wave.open(str(quelle), "rb") as datei:
        rate = datei.getframerate()
    # Ein Viertelrahmen hinter der Grenze: `int` und `floor` landen beide auf
    # demselben Rahmen, keine Gleitkommazahl kippt einen auf den Nachbarn.
    innen = (round(teilung_s * rate) + 0.25) / rate
    return (
        _schneide_ab(ablage, quelle, ziel_vorn, start_s, innen, nach_aussen=False),
        _schneide_ab(ablage, quelle, ziel_hinten, innen, ende_s),
    )


def kopiere(
    ablage: storage.Ablage, aufnahme: Aufnahme, start_s: float, ende_s: float, ziel: str
) -> klang.Befund:
    """Einen Ausschnitt des Originals als eigene Datei ablegen - ein Teil allein.

    Für „Editieren", wenn die Teilung auf Anfang oder Ende liegt.
    """
    return _schneide_ab(ablage, _quelle(ablage, aufnahme, start_s, ende_s), ziel, start_s, ende_s)


def _quelle(ablage: storage.Ablage, aufnahme: Aufnahme, start_s: float, ende_s: float) -> Path:
    """Die Datei der Aufnahme - wenn sie da ist und der Bereich eine Länge hat."""
    quelle = ablage.pfad(aufnahme.blob)
    if not quelle.is_file():
        raise klang.AudioFehler(f"Audio fehlt: {aufnahme.blob}")
    if not ende_s > start_s:
        raise klang.AudioFehler(
            f"Das Ende muss hinter dem Anfang liegen ({start_s:.2f} bis {ende_s:.2f} s)."
        )
    return quelle


def _schneide_ab(
    ablage: storage.Ablage,
    quelle: Path,
    ziel: str,
    start_s: float,
    ende_s: float,
    nach_aussen: bool = True,
) -> klang.Befund:
    """Den Bereich als Datei unter `ziel` ablegen und vermessen.

    Erst daneben schreiben, dann an die Stelle - auch über das Original.
    """
    with tempfile.TemporaryDirectory() as verzeichnis:
        entwurf = Path(verzeichnis) / "schnitt.wav"
        klang.schneide_ausschnitt(quelle, entwurf, start_s, ende_s, nach_aussen=nach_aussen)
        befund = klang.untersuche(entwurf)
        ablage.lege_ab(ziel, entwurf)
    return befund
