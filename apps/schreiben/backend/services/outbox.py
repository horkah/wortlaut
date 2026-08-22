"""Der Postausgang: bestätigte Abschnitte zurück an „hören".

Bestätigt die Person ihren Text, wird jeder Abschnitt zu einem Korrekturpaar
(Audio + Text) und geht an `POST /api/korpus/intake` von „hören". Dass diese
App und „hören" beide erreichbar sind, ist nicht garantiert — deshalb liegt
zwischen beiden eine Tabelle und kein direkter Aufruf.

Zwei Zusagen halten das einfach:

* **Wiederholen ist gefahrlos.** Jede Lieferung nennt die Abschnittskennung
  als `externe_id`; „hören" erkennt daran eine Wiederholung und legt nichts
  doppelt an. Der Postausgang darf also beliebig oft senden.
* **Nichts wird stillschweigend verworfen.** Ein Fehlschlag erhöht den Zähler
  und schreibt den Grund in die Zeile; der Eintrag bleibt offen, bis er
  wirklich angekommen ist.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import ids, storage

from ..config import Einstellungen
from ..db.models import Abschnitt, Postausgang, jetzt


@dataclass(frozen=True)
class Bericht:
    """Ergebnis eines Sendelaufs — Zahlen für die Oberfläche, kein Protokoll."""

    gesendet: int
    offen: int
    fehler: str | None = None


def stelle_ein(db: Session, abschnitte: list[Abschnitt]) -> int:
    """Legt für jeden Abschnitt einen offenen Eintrag an. Gibt die Zahl zurück.

    Ein zweiter Aufruf für dieselben Abschnitte legt nichts nach — bestätigen
    darf man auch zweimal.
    """
    vorhanden = set(
        db.scalars(
            select(Postausgang.segment_id).where(
                Postausgang.segment_id.in_([a.id for a in abschnitte])
            )
        )
    )
    neu = [a for a in abschnitte if a.id not in vorhanden]
    db.add_all(
        Postausgang(
            id=ids.neue_id("out"),
            segment_id=abschnitt.id,
            status="offen",
            versuche=0,
            letzter_fehler=None,
            erstellt=jetzt(),
            zuletzt=None,
        )
        for abschnitt in neu
    )
    return len(neu)


def sende_offene(db: Session, ablage: storage.Ablage, konfiguration: Einstellungen) -> Bericht:
    """Versucht, alle offenen Einträge zuzustellen.

    Ohne `WORTLAUT_INTAKE_URL` wird nichts gesendet und nichts als gescheitert
    gezählt: Der Postausgang ist dann ein Puffer, der auf seine Adresse wartet.
    """
    offene = list(
        db.scalars(
            select(Postausgang).where(Postausgang.status == "offen").order_by(Postausgang.erstellt)
        )
    )
    if not konfiguration.intake_url:
        return Bericht(gesendet=0, offen=len(offene), fehler="Keine Intake-Adresse konfiguriert.")

    gesendet = 0
    letzter_fehler: str | None = None
    for eintrag in offene:
        abschnitt = db.get(Abschnitt, eintrag.segment_id)
        eintrag.versuche += 1
        eintrag.zuletzt = jetzt()
        try:
            if abschnitt is None or abschnitt.blob is None:
                # Kann nur eintreten, wenn die Audiodatei fehlt — dann ist die
                # Korrektur wertlos, aber der Eintrag darf nicht ewig hängen.
                raise FileNotFoundError("Aufnahme des Abschnitts ist nicht mehr vorhanden.")
            liefere_ein(
                konfiguration,
                wav=ablage.pfad(abschnitt.blob),
                text=abschnitt.text,
                externe_id=abschnitt.id,
            )
        except Exception as fehler:  # Netz, Server, fehlende Datei — alles gleich
            eintrag.letzter_fehler = f"{type(fehler).__name__}: {fehler}"[:500]
            letzter_fehler = eintrag.letzter_fehler
            continue

        eintrag.status = "gesendet"
        eintrag.letzter_fehler = None
        gesendet += 1
        # Angekommen heißt: die Aufnahme liegt jetzt im Korpus von „hören".
        # Eine zweite Kopie an dieser Stelle wäre nur mehr Gesundheitsdaten.
        ablage.loesche(abschnitt.blob)
        abschnitt.blob = None

    db.commit()
    return Bericht(gesendet=gesendet, offen=len(offene) - gesendet, fehler=letzter_fehler)


def liefere_ein(konfiguration: Einstellungen, *, wav: Path, text: str, externe_id: str) -> None:
    """Eine Korrektur an „hören" übergeben. Wirft, wenn es nicht geklappt hat.

    Eigene Funktion, damit der Weg nach draußen an genau einer Stelle steht —
    und damit ein Test ihn ersetzen kann, ohne einen Server zu starten.

    `WORTLAUT_INTAKE_TOKEN` ist der Zugang **des** Sprechers bei „hören"; er
    bestimmt dort, in welchen Korpus geschrieben wird. `sprecher` geht trotzdem
    mit: nicht mehr als Wahl, sondern als Behauptung, die „hören" gegen den
    Zugang hält. Passen die beiden nicht zusammen — hier der eine Sprecher
    konfiguriert, dort der Zugang eines anderen —, kommt ein 403 zurück und der
    Eintrag bleibt offen, statt dass Korrekturen still im fremden Korpus
    landen.
    """
    import httpx

    kopf = (
        {"Authorization": f"Bearer {konfiguration.intake_token}"}
        if konfiguration.intake_token
        else {}
    )
    with wav.open("rb") as datei:
        antwort = httpx.post(
            konfiguration.intake_url,
            params={"sprecher": konfiguration.sprecher_id},
            headers=kopf,
            files={"audio": (wav.name, datei, "audio/wav")},
            data={"text": text, "externe_id": externe_id},
            timeout=60,
        )
    antwort.raise_for_status()
