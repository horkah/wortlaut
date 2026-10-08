"""Die Faltung jedes Stamms - mit seiner ersten Aufnahme vergeben, danach fest.

Die Kreuzvalidierung in „lernen" teilt den Korpus in `laeufe.FALTUNGEN`
Faltungen, je Stamm: Teile und Kopien aus „Editieren" liegen bei ihrem
Original. **Ein neuer Stamm kommt in die Faltung mit der wenigsten Sprache**
(`vergib`). So bleiben die Faltungen gleich schwer, und keine Aufnahme
wechselt je ihre Faltung - Löschen und Wiederherstellen verschieben nichts.

Ein Stamm ohne Zeile liegt in der Faltung nach dem Hash seiner Kennung
(`laeufe.verteile`, über alle Stämme ohne Zeile).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import laeufe

from ..db.models import GUELTIG, Aufnahme, Faltung, jetzt
from . import zuschnitt


def zuordnung(db: Session, staemme: list[str]) -> dict[str, int]:
    """Die Faltung (ab 0) jedes der `staemme`."""
    gespeichert = {
        stamm: faltung
        for stamm, faltung in db.execute(select(Faltung.stamm, Faltung.faltung)).tuples()
    }
    ohne = [stamm for stamm in staemme if stamm not in gespeichert]
    nach_hash = dict(zip(ohne, laeufe.verteile(ohne), strict=True))
    return {
        stamm: gespeichert[stamm] if stamm in gespeichert else nach_hash[stamm]
        for stamm in staemme
    }


def vergib(db: Session, aufnahme: Aufnahme) -> None:
    """Gibt dem Stamm einer neuen Aufnahme seine Faltung - die mit der wenigsten Sprache.

    Ein Stamm, der schon eine hat, behält sie. Gezählt wird die Dauer der
    brauchbaren Aufnahmen; bei Gleichstand die kleinste Nummer.
    """
    stamm = zuschnitt.stamm(aufnahme)
    if db.get(Faltung, stamm) is not None:
        return
    vorhanden = [
        (zuschnitt.stamm(andere), andere.dauer_s)
        for andere in db.scalars(select(Aufnahme).where(Aufnahme.status == GUELTIG))
        if andere.id != aufnahme.id
    ]
    faltungen = zuordnung(db, list(dict.fromkeys(s for s, _ in vorhanden)))
    sekunden = [0.0] * laeufe.FALTUNGEN
    for anderer, dauer_s in vorhanden:
        if anderer != stamm:
            sekunden[faltungen[anderer]] += dauer_s
    leichteste = min(range(laeufe.FALTUNGEN), key=lambda faltung: (sekunden[faltung], faltung))
    db.add(Faltung(stamm=stamm, faltung=leichteste, erstellt=jetzt()))
