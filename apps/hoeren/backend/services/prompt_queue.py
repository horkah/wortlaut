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


def naechste(db: Session, sprecher_id: str) -> Ausschnitt:
    erledigte_vorlagen = select(Aufnahme.prompt_id).where(Aufnahme.status == "ok")
    offene = _aus_aktiven_quellen(sprecher_id)

    aktuell = db.scalars(
        select(Vorlage)
        .where(Vorlage.id.in_(offene), Vorlage.id.not_in(erledigte_vorlagen))
        .order_by(Vorlage.position)
        .limit(1)
    ).first()

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
