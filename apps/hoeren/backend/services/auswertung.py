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
gleichzeitig im Speicher liegen (`_transkriptoren`) - bei base, small, medium
und large-v3 in `int8` gut zweieinhalb Gigabyte.

**Warum mehrfach je Aufnahme und Modell.** Eine Aufnahme ist ein einzelner
Fall: dieser Pegel, dieses Mikrofon, dieser Raum. Ein Modell, das damit
zurechtkommt, muss den Sprecher noch nicht verstanden haben. Gemessen wird
deshalb nicht die Aufnahme allein, sondern die Aufnahme und ihre Abwandlungen
(`wortlaut/augmentierung.py`) - seit September 2026 ist das eine: Rauschen.
Zwei Zahlen je Modell und Aufnahme, und erst ihr Zusammenhang sagt, ob ein
Ergebnis hielt oder an der Aufnahmesituation hing.

Die fehlenden Fassungen entstehen dabei von selbst, kurz bevor sie gebraucht
werden - so kommt auch jede Aufnahme, die vor dieser Änderung im Korpus lag,
zu ihren Dateien, ohne dass jemand ein Skript anstoßen muss
(`services/augmentierung.py`).

**Was wiederholbar ist.** Fertig ist, was in `erkennungen` steht (siehe
`005_auswertung.sql`, `007_varianten.sql`). Ein zweiter Lauf rechnet deshalb
nur, was fehlt: nach einem Neustart, nach neuen Aufnahmen, nach einem
hinzugefügten Modell - und nach einer hinzugefügten Fassung. Nichts wird
doppelt gerechnet, und nichts geht verloren, wenn der Lauf mitten darin
abbricht.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session
from wortlaut import ids, metriken, storage
from wortlaut import rechenwerk
from wortlaut.whisper import Transkriptor

from ..db.models import Aufnahme, Erkennung, Vorlage, jetzt
from . import augmentierung

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
    # Woran gerade gerechnet wird - Modell und Fassung, damit sichtbar ist,
    # dass es vorangeht, auch wenn eine Aufnahme lange braucht.
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
    uebersprungen: set[tuple[str, str, str]] = field(default_factory=set)


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
    """Eine offene Rechenaufgabe: diese Fassung dieser Aufnahme durch dieses Modell."""

    aufnahme_id: str
    # Das Original, so wie es in der Zeile steht.
    blob: str
    # Die Datei, die dieses Mal durch das Modell geht - beim Original dieselbe,
    # sonst die abgewandelte Fassung daneben. Hier ausgerechnet und nicht im
    # Lauf: Dafür braucht es die Aufnahme mit ihrem Sprecher, und die steht nur
    # hier, solange die Sitzung offen ist.
    variante_blob: str
    referenz: str
    modell: str
    variante: str

    @property
    def marke(self) -> tuple[str, str, str]:
        """Was diesen Posten eindeutig macht - der Schlüssel für „schon gerechnet"."""
        return (self.aufnahme_id, self.modell, self.variante)


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


def _fertig(db: Session, werk: str) -> set[tuple[str, str, str]]:
    """Was schon gemessen ist - **auf dem Rechenwerk, das gerade gilt**.

    Die Einschränkung ist neu und sie ist der Preis der Vergleichbarkeit. Eine
    Zeile, die auf dem Prozessor entstand, während jetzt die Karte rechnet,
    trägt eine Rechenzeit, die mit den übrigen nichts zu tun hat - und das
    zehnfach. Sie stehen zu lassen hieße, in einer Spalte zwei Maßstäbe zu
    mischen; genau das war der Fehler, gegen den diese Änderung antritt.

    Neu gerechnet wird deshalb, was aus einem anderen Rechenwerk stammt oder
    aus keinem bekannten (die Zeilen von vor `008_rechenwerk.sql`). Das kostet
    einmal einen vollen Lauf - auf der Karte sind das Minuten statt Stunden.
    """
    return {
        (zeile.recording_id, zeile.modell, zeile.variante)
        for zeile in db.execute(
            select(Erkennung.recording_id, Erkennung.modell, Erkennung.variante).where(
                Erkennung.rechenwerk == werk
            )
        ).all()
    }


def offene_posten(db: Session, namen: list[str], werk: str) -> list[Posten]:
    """Was noch zu rechnen ist, in der Reihenfolge, in der gerechnet wird.

    Die Schachtelung ist die Reihenfolge des Laufs: Aufnahme, dann Modell,
    dann Fassung. Die vier Fassungen eines Modells liegen damit nebeneinander,
    und genau nebeneinander werden sie später gelesen - eine halb gerechnete
    Aufnahme zeigt lieber ein vollständiges Modell als vier angefangene.
    """
    erledigt = _fertig(db, werk)
    return [
        posten
        for aufnahme, vorlage in gueltige_aufnahmen(db)
        for modell in namen
        for variante in augmentierung.VARIANTEN
        if (
            posten := Posten(
                aufnahme_id=aufnahme.id,
                blob=aufnahme.blob,
                variante_blob=augmentierung.relpfad(aufnahme, variante),
                referenz=vorlage.text,
                modell=modell,
                variante=variante,
            )
        ).marke
        not in erledigt
    ]


def zaehle(db: Session, namen: list[str], werk: str) -> tuple[int, int]:
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
    # Gezählt wird nur, was zu den derzeit konfigurierten Modellen und
    # Fassungen gehört: Wer ein Modell aus der Liste nimmt, soll nicht
    # plötzlich über 100 % stehen - und die Zeilen einer abgeschafften Fassung
    # sollen den Balken nicht vollmachen, ohne dass es etwas zu sehen gäbe.
    erledigt = (
        db.scalar(
            select(func.count())
            .select_from(Erkennung)
            .where(
                Erkennung.modell.in_(namen),
                Erkennung.variante.in_(augmentierung.VARIANTEN),
                # Dieselbe Einschränkung wie in `_fertig`: Was auf einem
                # anderen Rechenwerk entstand, ist offen und nicht erledigt -
                # sonst stünde der Balken bei 100 %, während der Lauf noch
                # rechnet.
                Erkennung.rechenwerk == werk,
            )
        )
        or 0
    )
    return erledigt, aufnahmen * len(namen) * len(augmentierung.VARIANTEN)


def _rechne(
    posten: Posten, wav: Path, sprache: str, transkriptor: Transkriptor, werk: str
) -> Erkennung:
    """Erkennen und messen - der Teil, der rechnet und keine Datenbank anfasst."""
    begonnen = time.monotonic()
    transkript = transkriptor.transkribiere(wav, sprache=sprache)
    dauer = time.monotonic() - begonnen
    # **Nach** dem Erkennen gefragt und nicht davor: Ob die Karte den Platz
    # hergab, zeigt sich beim Laden. Wich der Transkriptor auf den Prozessor
    # aus, steht das hier - und die Zeile daneben ist als das lesbar, was sie
    # ist, statt wie ein plötzlich langsam gewordenes Modell auszusehen.
    #
    # Wer nichts zu melden hat, bekommt das Rechenwerk des Laufs: Ein
    # entfernter Endpunkt weiß nicht, worauf er rechnet, und ein Ersatz im Test
    # erst recht nicht. Eine leere Angabe wäre schlimmer als eine
    # angenommene - sie ließe die Zeile bei jedem Lauf aufs Neue offen gelten.
    werk = getattr(transkriptor, "marke", "") or werk

    guete = metriken.bewerte(posten.referenz, transkript.text)
    return Erkennung(
        id=ids.neue_id("erk"),
        recording_id=posten.aufnahme_id,
        modell=posten.modell,
        variante=posten.variante,
        text=transkript.text,
        wer=guete.wer,
        cer=guete.cer,
        mer=guete.mer,
        wil=guete.wil,
        genauigkeit=guete.genauigkeit,
        rechenzeit_s=dauer,
        rechenwerk=werk,
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
    uebersprungen: set[tuple[str, str, str]],
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
    # Das Rechenwerk, unter dem dieser Lauf misst, und zugleich der Maßstab
    # dafür, was als erledigt gilt (siehe `_fertig`). Einmal aufgelöst und
    # danach fest: Ein Lauf, der auf halber Strecke die Maschine wechselte,
    # hinterließe eine Spalte mit zwei Maßstäben.
    werk = rechenwerk.marke(*rechenwerk.waehle(geraet, rechenart))

    while True:
        with Session(engine) as db:
            offen = [
                posten
                for posten in offene_posten(db, namen, werk)
                if posten.marke not in uebersprungen
            ]
            zustand.erledigt, zustand.gesamt = zaehle(db, namen, werk)
            zustand.uebersprungen = len(uebersprungen)

        if not offen:
            return

        posten = offen[0]
        zustand.aktuell = f"{posten.modell} · {posten.variante}"

        if not ablage.pfad(posten.blob).is_file():
            # Kein Grund, den ganzen Lauf hinzuwerfen: Die übrigen Aufnahmen
            # sind davon unberührt.
            uebersprungen.add(posten.marke)
            zustand.fehler = f"Audio fehlt: {posten.blob}"
            continue

        try:
            # Die abgewandelte Fassung entsteht hier, kurz bevor sie gebraucht
            # wird - und nur, wenn sie fehlt. Damit kommt auch jede Aufnahme,
            # die vor der Einführung der Fassungen im Korpus lag, zu ihren
            # Dateien, ohne dass jemand ein Skript anstoßen muss. Im
            # Arbeitsfaden wie das Erkennen selbst: Es liest und schreibt eine
            # Datei und rechnet über jeden Abtastwert.
            await asyncio.to_thread(
                augmentierung.stelle_her,
                ablage,
                quelle_blob=posten.blob,
                ziel_blob=posten.variante_blob,
                variante=posten.variante,
                keim=posten.aufnahme_id,
            )

            # In einem Arbeitsfaden: Whisper rechnet sekunden- bis minutenlang
            # und blockierte sonst die Ereignisschleife - der Server nähme in
            # dieser Zeit keine einzige Anfrage mehr an, auch nicht die nach
            # dem Fortschritt.
            erkennung = await asyncio.to_thread(
                _rechne,
                posten,
                ablage.pfad(posten.variante_blob),
                sprache,
                transkriptor_fuer(posten.modell, geraet, rechenart),
                werk,
            )
        except asyncio.CancelledError:
            raise
        except Exception as ursache:  # noqa: BLE001 - was immer das Modell wirft
            uebersprungen.add(posten.marke)
            zustand.fehler = f"{posten.modell} · {posten.variante}: {ursache}"
            continue

        with Session(engine) as db:
            # Die alte Zeile weicht, falls es eine gibt. Je Aufnahme, Modell
            # und Fassung darf genau eine dastehen (`007_varianten.sql`) - und
            # seit eine Messung aus einem anderen Rechenwerk als offen gilt,
            # kommt der Lauf an Stellen vorbei, an denen schon etwas steht. Ein
            # blindes Einfügen scheiterte dort am Index, der Posten landete
            # unter „übersprungen", und die veraltete Zeile bliebe für immer
            # stehen: Der Lauf käme nie zum Ende.
            db.execute(
                delete(Erkennung).where(
                    Erkennung.recording_id == posten.aufnahme_id,
                    Erkennung.modell == posten.modell,
                    Erkennung.variante == posten.variante,
                )
            )
            db.add(erkennung)
            db.commit()


def stand(db: Session, namen: list[str], werk: str) -> Stand:
    """Der Stand für die Oberfläche - auch dann, wenn gerade kein Lauf läuft."""
    erledigt, gesamt = zaehle(db, namen, werk)
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
    geraet: str = rechenwerk.AUTO,
    rechenart: str = rechenwerk.AUTO,
) -> Stand:
    """Einen Lauf anstoßen. Läuft schon einer, bleibt es bei ihm.

    **Ist nichts offen, läuft auch nichts.** Der Lauf rechnet, was fehlt, und
    nichts sonst - steht schon alles, wäre er fertig, bevor er anfängt. Eine
    Aufgabe dafür anzulegen kostet nichts, hinterließe aber für einen
    Augenblick einen Zustand, der `laeuft` sagt und nicht läuft. Die Oberfläche
    fragt genau in diesem Augenblick nach und bekäme eine Auskunft, auf die sie
    sich nicht verlassen kann: Sie könnte „rechnet gerade" anzeigen und im
    nächsten Takt wieder „alles gerechnet", ohne dass etwas geschehen wäre.

    Stattdessen kommt der unveränderte Stand zurück, und `laeuft` ist falsch.
    Daran erkennt die Ansicht, dass es nichts zu tun gab, und sagt es - sonst
    federt der Knopf zurück und sieht aus, als sei er kaputt.
    """
    global _lauf

    if _lauf is not None and not _lauf.aufgabe.done():
        return _lauf.stand

    werk = rechenwerk.marke(*rechenwerk.waehle(geraet, rechenart))
    with Session(engine) as db:
        if not offene_posten(db, namen, werk):
            erledigt, gesamt = zaehle(db, namen, werk)
            return Stand(
                laeuft=False, sprecher_id=sprecher_id, erledigt=erledigt, gesamt=gesamt
            )

    stand_neu = Stand(laeuft=True, sprecher_id=sprecher_id)
    uebersprungen: set[tuple[str, str, str]] = set()
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
