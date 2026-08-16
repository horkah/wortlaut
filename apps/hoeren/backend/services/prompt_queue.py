"""Reihenfolge und Wiederaufnahme der Warteschlange.

Die Position in der Warteschlange wird nirgends gespeichert, sondern
abgeleitet: offen ist jede Vorlage ohne gültige Aufnahme, die nächste ist die
mit der kleinsten Position. Damit ist eine unterbrochene Sitzung ohne
Zusatzlogik fortsetzbar, und eine verworfene Aufnahme macht ihre Vorlage
automatisch wieder offen.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Aufnahme, Vorlage


@dataclass(frozen=True)
class Ausschnitt:
    """Eine Einheit groß, davor und dahinter je eine blass."""

    vorher: Vorlage | None
    aktuell: Vorlage | None  # None heißt: Warteschlange abgearbeitet
    nachher: Vorlage | None
    erledigt: int
    gesamt: int


def naechste(db: Session, sprecher_id: str) -> Ausschnitt:
    erledigte_vorlagen = select(Aufnahme.prompt_id).where(Aufnahme.status == "ok")

    aktuell = db.scalars(
        select(Vorlage)
        .where(Vorlage.speaker_id == sprecher_id, Vorlage.id.not_in(erledigte_vorlagen))
        .order_by(Vorlage.position)
        .limit(1)
    ).first()

    gesamt = db.scalar(
        select(func.count()).select_from(Vorlage).where(Vorlage.speaker_id == sprecher_id)
    )
    erledigt = db.scalar(
        select(func.count(func.distinct(Aufnahme.prompt_id))).where(
            Aufnahme.speaker_id == sprecher_id, Aufnahme.status == "ok"
        )
    )

    if aktuell is None:
        return Ausschnitt(None, None, None, erledigt or 0, gesamt or 0)

    return Ausschnitt(
        vorher=_nachbar(db, sprecher_id, aktuell.position, vorwaerts=False),
        aktuell=aktuell,
        nachher=_nachbar(db, sprecher_id, aktuell.position, vorwaerts=True),
        erledigt=erledigt or 0,
        gesamt=gesamt or 0,
    )


def _nachbar(db: Session, sprecher_id: str, position: int, *, vorwaerts: bool) -> Vorlage | None:
    """Nachbar im Text — unabhängig davon, ob er schon aufgenommen wurde."""
    abfrage = select(Vorlage).where(Vorlage.speaker_id == sprecher_id)
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
