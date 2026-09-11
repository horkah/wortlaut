"""Die Auswertung: Wie gut hören verschiedene Modelle diesem Sprecher zu?

Der Korpus weiß, was gesprochen wurde, und er weiß, was gesprochen werden
sollte - die Vorlage steht daneben. Damit ist jede Aufnahme eine fertige
Prüfaufgabe: Man schickt sie durch einen Erkenner und vergleicht, was
herauskommt, mit dem, was dastand. Genau das tut diese Datei, für jedes
konfigurierte Modell und jede brauchbare Aufnahme.

**Warum im Hintergrund.** Ein Modell über hundert Aufnahmen laufen zu lassen
dauert Minuten bis Stunden, je nach Modell und Maschine. Eine Anfrage, die so
lange offen steht, ist keine Anfrage mehr. Der Lauf hängt deshalb an keiner:
Er wird angestoßen, arbeitet weiter, wenn die Seite längst geschlossen ist,
und die Oberfläche fragt den Stand ab.

**Warum von Hand angestoßen.** Der Lauf startet nicht beim Hochfahren des
Servers. Whisper rechnet, und zwar auf derselben Maschine, auf der jemand
gerade aufnimmt (Grundentscheidung 5 gilt für das Training, nicht für dieses
Messen - aber die CPU ist dieselbe). Ein Neustart des Containers würde sonst
jedes Mal ungefragt Stunden Rechenzeit binden. Wer messen will, sagt es.

**Warum aufnahmeweise und nicht modellweise.** Die naheliegende Reihenfolge
wäre, erst alle Aufnahmen durch `base` zu schicken, dann durch `small`, dann
durch `medium`. Sie wäre auch sparsamer: je Modell einmal laden. Nur zeigt die
Kurve dann lange Zeit eine einzige Reihe, und verglichen werden soll gerade.
Also andersherum: Aufnahme für Aufnahme durch alle Modelle, damit die ersten
Punkte sofort vollständig sind. Bezahlt wird das damit, dass alle Erkenner
gleichzeitig im Speicher liegen (`_transkriptoren`) - bei base, small und
medium in `int8` gut ein Gigabyte.

**Was wiederholbar ist.** Fertig ist, was in `erkennungen` steht (siehe
`005_auswertung.sql`). Ein zweiter Lauf rechnet deshalb nur, was fehlt: nach
einem Neustart, nach neuen Aufnahmen oder nach einem hinzugefügten Modell.
Nichts wird doppelt gerechnet, und nichts geht verloren, wenn der Lauf mitten
darin abbricht.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session
from wortlaut import ids, metriken, storage
from wortlaut.whisper import Transkriptor

from ..db.models import Aufnahme, Erkennung, Vorlage, jetzt

# Nur brauchbare Aufnahmen: Was verworfen wurde, ist kein Prüfstück, sondern
# ein Fehlversuch - und ginge als schlechte Note eines Modells durch, obwohl
# der Sprecher selbst gesagt hat, dass es so nicht zählen soll.
GUELTIG = "ok"


@dataclass
class Stand:
    """Was die Oberfläche über den Lauf wissen will."""

    laeuft: bool = False
    sprecher_id: str = ""
    erledigt: int = 0
    gesamt: int = 0
    uebersprungen: int = 0
    # Woran gerade gerechnet wird - Modellname, damit sichtbar ist, dass es
    # vorangeht, auch wenn eine Aufnahme lange braucht.
    aktuell: str = ""
    fehler: str | None = None


@dataclass
class _Lauf:
    sprecher_id: str
    aufgabe: asyncio.Task[None]
    stand: Stand
    # Was in diesem Lauf nicht ging, damit es nicht endlos wiederholt wird.
    # Bewusst nur im Speicher: Ein fehlendes Audio kann beim nächsten Anlauf
    # wieder da sein, und ein Fehlschlag ist kein Ergebnis, das in den Korpus
    # gehört.
    uebersprungen: set[tuple[str, str]] = field(default_factory=set)


# Ein Lauf zur Zeit, über alle Sprecher. Nicht aus Bequemlichkeit: Zwei Läufe
# teilten sich eine CPU und dieselben Modelle im Speicher und wären zusammen
# langsamer als nacheinander.
_lauf: _Lauf | None = None

# Einmal geladen, dann wiederverwendet - das Laden eines Modells kostet
# Sekunden, das Erkennen eines Satzes ebenso. Siehe Kopfkommentar.
_transkriptoren: dict[str, Transkriptor] = {}


def modelle(liste: str) -> list[str]:
    """Die konfigurierte Modellreihe als Liste, leere Einträge weggelassen."""
    return [name.strip() for name in liste.split(",") if name.strip()]


def transkriptor_fuer(modell: str, geraet: str, rechenart: str) -> Transkriptor:
    if modell not in _transkriptoren:
        from wortlaut.whisper.local import LokalerTranskriptor

        _transkriptoren[modell] = LokalerTranskriptor(
            modell, geraet=geraet, rechenart=rechenart
        )
    return _transkriptoren[modell]


@dataclass(frozen=True)
class Posten:
    """Eine offene Rechenaufgabe: diese Aufnahme durch dieses Modell."""

    aufnahme_id: str
    blob: str
    referenz: str
    modell: str


def gueltige_aufnahmen(db: Session) -> list[tuple[Aufnahme, Vorlage]]:
    """Alle brauchbaren Aufnahmen mit ihrer Vorlage, älteste zuerst.

    Die Reihenfolge ist zugleich die Nummerierung der Kurve: Aufnahme 1 ist
    die erste, die dieser Sprecher gemacht hat. Ohne Lücken und stabil, denn
    sie hängt am Zeitpunkt und nicht an einer Kennung.
    """
    return list(
        db.execute(
            select(Aufnahme, Vorlage)
            .join(Vorlage, Vorlage.id == Aufnahme.prompt_id)
            .where(Aufnahme.status == GUELTIG)
            .order_by(Aufnahme.erstellt, Aufnahme.id)
        ).all()
    )


def _fertig(db: Session) -> set[tuple[str, str]]:
    return {
        (zeile.recording_id, zeile.modell)
        for zeile in db.execute(select(Erkennung.recording_id, Erkennung.modell)).all()
    }


def offene_posten(db: Session, namen: list[str]) -> list[Posten]:
    """Was noch zu rechnen ist, in der Reihenfolge, in der gerechnet wird."""
    erledigt = _fertig(db)
    return [
        Posten(
            aufnahme_id=aufnahme.id, blob=aufnahme.blob, referenz=vorlage.text, modell=modell
        )
        for aufnahme, vorlage in gueltige_aufnahmen(db)
        for modell in namen
        if (aufnahme.id, modell) not in erledigt
    ]


def zaehle(db: Session, namen: list[str]) -> tuple[int, int]:
    """(erledigt, gesamt) - beides aus der Datenbank, nie aus einem Zähler.

    Ein mitlaufender Zähler wäre nach jedem Neustart falsch, und genau ein
    Neustart mitten im Lauf ist der Fall, für den diese Auswertung
    wiederaufnehmbar gebaut ist.
    """
    aufnahmen = (
        db.scalar(
            select(func.count()).select_from(Aufnahme).where(Aufnahme.status == GUELTIG)
        )
        or 0
    )
    # Gezählt wird nur, was zu den derzeit konfigurierten Modellen gehört:
    # Wer ein Modell aus der Liste nimmt, soll nicht plötzlich über 100 %
    # stehen.
    erledigt = (
        db.scalar(
            select(func.count()).select_from(Erkennung).where(Erkennung.modell.in_(namen))
        )
        or 0
    )
    return erledigt, aufnahmen * len(namen)


def _rechne(posten: Posten, wav: Path, sprache: str, transkriptor: Transkriptor) -> Erkennung:
    """Erkennen und messen - der Teil, der rechnet und keine Datenbank anfasst."""
    begonnen = time.monotonic()
    transkript = transkriptor.transkribiere(wav, sprache=sprache)
    dauer = time.monotonic() - begonnen

    guete = metriken.bewerte(posten.referenz, transkript.text)
    return Erkennung(
        id=ids.neue_id("erk"),
        recording_id=posten.aufnahme_id,
        modell=posten.modell,
        text=transkript.text,
        wer=guete.wer,
        cer=guete.cer,
        mer=guete.mer,
        wil=guete.wil,
        genauigkeit=guete.genauigkeit,
        rechenzeit_s=dauer,
        erstellt=jetzt(),
    )


async def _arbeite(
    engine: Engine,
    ablage: storage.Ablage,
    namen: list[str],
    sprache: str,
    geraet: str,
    rechenart: str,
    zustand: Stand,
    uebersprungen: set[tuple[str, str]],
) -> None:
    """Der Lauf selbst: einen Posten nach dem anderen, bis nichts mehr offen ist.

    Zustand und Merkliste kommen als Argument und nicht aus `_lauf`: Diese
    Aufgabe wird angelegt, bevor `_lauf` steht, und eine Reihenfolge, auf die
    man sich verlassen muss, ist eine Reihenfolge, die irgendwann jemand
    umstellt.

    Je Posten eine eigene Sitzung. Eine über den ganzen Lauf offene hielte eine
    Schreibsperre über Stunden - und währenddessen nimmt derselbe Sprecher
    womöglich weiter auf.
    """
    while True:
        with Session(engine) as db:
            offen = [
                posten
                for posten in offene_posten(db, namen)
                if (posten.aufnahme_id, posten.modell) not in uebersprungen
            ]
            zustand.erledigt, zustand.gesamt = zaehle(db, namen)
            zustand.uebersprungen = len(uebersprungen)

        if not offen:
            return

        posten = offen[0]
        zustand.aktuell = posten.modell
        wav = ablage.pfad(posten.blob)

        if not wav.is_file():
            # Kein Grund, den ganzen Lauf hinzuwerfen: Die übrigen Aufnahmen
            # sind davon unberührt.
            uebersprungen.add((posten.aufnahme_id, posten.modell))
            zustand.fehler = f"Audio fehlt: {posten.blob}"
            continue

        try:
            # In einem Arbeitsfaden: Whisper rechnet sekunden- bis minutenlang
            # und blockierte sonst die Ereignisschleife - der Server nähme in
            # dieser Zeit keine einzige Anfrage mehr an, auch nicht die nach
            # dem Fortschritt.
            erkennung = await asyncio.to_thread(
                _rechne,
                posten,
                wav,
                sprache,
                transkriptor_fuer(posten.modell, geraet, rechenart),
            )
        except asyncio.CancelledError:
            raise
        except Exception as ursache:  # noqa: BLE001 - was immer das Modell wirft
            uebersprungen.add((posten.aufnahme_id, posten.modell))
            zustand.fehler = f"{posten.modell}: {ursache}"
            continue

        with Session(engine) as db:
            db.add(erkennung)
            db.commit()


def stand(db: Session, namen: list[str]) -> Stand:
    """Der Stand für die Oberfläche - auch dann, wenn gerade kein Lauf läuft."""
    erledigt, gesamt = zaehle(db, namen)
    if _lauf is None:
        return Stand(laeuft=False, erledigt=erledigt, gesamt=gesamt)

    _lauf.stand.erledigt, _lauf.stand.gesamt = erledigt, gesamt
    _lauf.stand.laeuft = not _lauf.aufgabe.done()
    return _lauf.stand


def laeuft_fuer() -> str:
    """Für welchen Sprecher gerade gerechnet wird; leer, wenn niemand rechnet."""
    if _lauf is None or _lauf.aufgabe.done():
        return ""
    return _lauf.sprecher_id


def starte(
    sprecher_id: str,
    engine: Engine,
    ablage: storage.Ablage,
    namen: list[str],
    sprache: str,
    geraet: str = "auto",
    rechenart: str = "int8",
) -> Stand:
    """Einen Lauf anstoßen. Läuft schon einer, bleibt es bei ihm."""
    global _lauf

    if _lauf is not None and not _lauf.aufgabe.done():
        return _lauf.stand

    stand_neu = Stand(laeuft=True, sprecher_id=sprecher_id)
    uebersprungen: set[tuple[str, str]] = set()
    aufgabe = asyncio.create_task(
        _arbeite(
            engine, ablage, namen, sprache, geraet, rechenart, stand_neu, uebersprungen
        )
    )
    _lauf = _Lauf(
        sprecher_id=sprecher_id,
        aufgabe=aufgabe,
        stand=stand_neu,
        uebersprungen=uebersprungen,
    )

    def _fertig_gemeldet(beendet: asyncio.Task[None]) -> None:
        stand_neu.laeuft = False
        stand_neu.aktuell = ""
        if beendet.cancelled():
            return
        ursache = beendet.exception()
        if ursache is not None:
            stand_neu.fehler = str(ursache)

    aufgabe.add_done_callback(_fertig_gemeldet)
    return stand_neu


def stoppe() -> None:
    """Den laufenden Lauf abbrechen. Fertig Gerechnetes bleibt stehen."""
    if _lauf is not None and not _lauf.aufgabe.done():
        _lauf.aufgabe.cancel()


def vergiss_lauf() -> None:
    """Nur für Tests: den Zustand zwischen zwei Fällen zurücksetzen."""
    global _lauf
    _lauf = None
    _transkriptoren.clear()
