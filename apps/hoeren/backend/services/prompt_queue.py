"""Reihenfolge und Wiederaufnahme der Warteschlange.

Die Position in der Warteschlange wird nirgends gespeichert, sondern
abgeleitet: offen ist jede Vorlage ohne gültige Aufnahme, die nächste ist die
mit der kleinsten Position. Damit ist eine unterbrochene Sitzung ohne
Zusatzlogik fortsetzbar, und eine verworfene Aufnahme macht ihre Vorlage
automatisch wieder offen.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Aufnahme, Textquelle, Vorlage


@dataclass(frozen=True)
class Ausschnitt:
    """Eine Einheit groß, davor und dahinter je eine blass."""

    vorher: Vorlage | None
    aktuell: Vorlage | None  # None heißt: Warteschlange abgearbeitet
    nachher: Vorlage | None
    erledigt: int
    gesamt: int


def _aus_aktiven_quellen(sprecher_id: str):
    """Vorlagen eines Sprechers, deren Quelle nicht stillgelegt ist.

    Eine stillgelegte Quelle verschwindet damit aus der Warteschlange, ohne
    dass an ihren Einheiten etwas geändert würde: Wird sie wieder aufgenommen,
    stehen sie an derselben Stelle wie zuvor.
    """
    return select(Vorlage.id).join(Textquelle, Textquelle.id == Vorlage.source_id).where(
        Vorlage.speaker_id == sprecher_id, Textquelle.aktiv.is_(True)
    )


def naechste(
    db: Session, sprecher_id: str, *, zufall: bool = False, streuung: str = ""
) -> Ausschnitt:
    """Die nächste offene Einheit — der Reihe nach oder gestreut.

    `zufall` mischt die Einheiten aller aktiven Quellen durcheinander. Gedacht
    ist das gegen den Gewöhnungseffekt: Wer einen Text der Reihe nach spricht,
    liest ihn nach ein paar Sätzen mit der Melodie des Zusammenhangs statt der
    des einzelnen Satzes — für das Training ist das die schwächere Aufnahme.

    `streuung` ist der Startwert des Mischens. Er muss über die Sitzung gleich
    bleiben: Sonst zeigte jeder Aufruf eine andere Einheit, und ein Neuladen
    mitten im Ablesen risse einem den Satz weg.
    """
    erledigte_vorlagen = select(Aufnahme.prompt_id).where(Aufnahme.status == "ok")
    offene = _aus_aktiven_quellen(sprecher_id)

    # Zähler und Warteschlange müssen dieselbe Menge meinen, sonst steht dort
    # „12 von 30", während nur 20 erreichbar sind.
    gesamt = db.scalar(select(func.count()).select_from(offene.subquery()))
    erledigt = db.scalar(
        select(func.count(func.distinct(Aufnahme.prompt_id))).where(
            Aufnahme.speaker_id == sprecher_id,
            Aufnahme.status == "ok",
            Aufnahme.prompt_id.in_(offene),
        )
    )
    zaehler = (erledigt or 0, gesamt or 0)

    if zufall:
        return _gestreut(db, sprecher_id, streuung, zaehler)

    aktuell = db.scalars(
        select(Vorlage)
        .where(Vorlage.id.in_(offene), Vorlage.id.not_in(erledigte_vorlagen))
        .order_by(Vorlage.position)
        .limit(1)
    ).first()

    if aktuell is None:
        return Ausschnitt(None, None, None, *zaehler)

    return Ausschnitt(
        vorher=_nachbar(db, sprecher_id, aktuell.position, vorwaerts=False),
        aktuell=aktuell,
        nachher=_nachbar(db, sprecher_id, aktuell.position, vorwaerts=True),
        erledigt=zaehler[0],
        gesamt=zaehler[1],
    )


def _gestreut(
    db: Session, sprecher_id: str, streuung: str, zaehler: tuple[int, int]
) -> Ausschnitt:
    """Dieselbe Auswahl, nur in gemischter statt gewachsener Reihenfolge.

    Gemischt wird hier und nicht in SQL: `ORDER BY random()` würfelte bei jedem
    Aufruf neu. Mit festem Startwert ist die Reihenfolge dagegen für die ganze
    Sitzung dieselbe — sie wird nur nach und nach abgearbeitet, genau wie die
    gewachsene.
    """
    reihenfolge = list(
        db.scalars(
            select(Vorlage.id)
            .join(Textquelle, Textquelle.id == Vorlage.source_id)
            .where(Vorlage.speaker_id == sprecher_id, Textquelle.aktiv.is_(True))
            # Erst eine feste Ordnung, dann mischen: Sonst hinge das Ergebnis
            # daran, in welcher Reihenfolge die Datenbank die Zeilen liefert.
            .order_by(Vorlage.position)
        ).all()
    )
    random.Random(streuung).shuffle(reihenfolge)

    erledigte = set(
        db.scalars(
            select(Aufnahme.prompt_id).where(
                Aufnahme.speaker_id == sprecher_id, Aufnahme.status == "ok"
            )
        ).all()
    )
    stelle = next((i for i, kennung in enumerate(reihenfolge) if kennung not in erledigte), None)
    if stelle is None:
        return Ausschnitt(None, None, None, *zaehler)

    def an(index: int) -> Vorlage | None:
        if not 0 <= index < len(reihenfolge):
            return None
        return db.get(Vorlage, reihenfolge[index])

    # Nachbarn sind hier die im gemischten Ablauf — was zuletzt dran war und
    # was als Nächstes kommt. Der Nachbar im Text wäre in dieser Betriebsart
    # eine Vorschau auf etwas, das nie folgt.
    return Ausschnitt(
        vorher=an(stelle - 1),
        aktuell=an(stelle),
        nachher=an(stelle + 1),
        erledigt=zaehler[0],
        gesamt=zaehler[1],
    )


def _nachbar(db: Session, sprecher_id: str, position: int, *, vorwaerts: bool) -> Vorlage | None:
    """Nachbar im Text — unabhängig davon, ob er schon aufgenommen wurde.

    Aus stillgelegten Quellen kommt auch hier nichts: Sonst stünde als Ausblick
    ein Satz, der nie an die Reihe kommt.
    """
    abfrage = select(Vorlage).where(Vorlage.id.in_(_aus_aktiven_quellen(sprecher_id)))
    abfrage = (
        abfrage.where(Vorlage.position > position).order_by(Vorlage.position)
        if vorwaerts
        else abfrage.where(Vorlage.position < position).order_by(Vorlage.position.desc())
    )
    return db.scalars(abfrage.limit(1)).first()


def naechste_position(db: Session, sprecher_id: str) -> int:
    """Erste freie Position — neue Quellen hängen hinten an."""
    hoechste = db.scalar(
        select(func.max(Vorlage.position)).where(Vorlage.speaker_id == sprecher_id)
    )
    return (hoechste or 0) + 1
