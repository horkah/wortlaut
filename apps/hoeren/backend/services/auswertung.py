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
wäre, erst alle Aufnahmen durch `small` zu schicken, dann durch `medium`, dann
durch `large-v3`. Sie wäre auch sparsamer: je Modell einmal laden. Nur zeigt die
Kurve dann lange Zeit eine einzige Reihe, und verglichen werden soll gerade.
Also andersherum: Aufnahme für Aufnahme durch alle Modelle, damit die ersten
Punkte sofort vollständig sind. Bezahlt wird das damit, dass alle Erkenner
gleichzeitig im Speicher liegen (`_transkriptoren`) - bei small, medium und
large-v3 in `int8` gut zweieinhalb Gigabyte.

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

**Wer antritt.** Die Grundmodelle aus der Konfiguration - und seit September
2026 jeder trainierte Stand dieses Sprechers, dessen Gewichte dastehen. Damit
steht in dieser Ansicht dasselbe Feld wie in „lernen", nur über den ganzen
Korpus statt über einen Lauf.

Ein Stand wird dabei nicht durchweg gerechnet. Die Aufnahmen, die es zur Zeit
seines Trainings schon gab, hat er gehört; ihn darauf loszulassen ergäbe eine
Zahl über sein Gedächtnis und keine über sein Können. Für genau sie liegt die
Messung der Kreuzvalidierung vor - dort war jede Aufnahme einmal in der
Prüffalte, also von einem Modell gehört, das sie nicht kannte. Diese Zeilen
werden übernommen (`uebernimm_faltungen`, `herkunft = 'faltung'`, siehe
`014_erkennungen_aus_faltungen.sql`). Was danach dazugekommen ist, rechnet der
ausgelieferte Stand selbst - für ihn ist eine neue Aufnahme dasselbe
unbekannte Prüfstück wie für ein Grundmodell.

Dass eine Zeile eines Standes damit aus zwei Quellen stammen kann, ist die
Absicht und nicht die Unsauberkeit: Beide Male misst sie denselben Satz, wie
gut dieser Stand etwas hört, das er nie gelernt hat. Der Preis ist, dass
`rechenzeit_s` einer übernommenen Zeile von der Trainingsmaschine kommt; die
Auswertung behandelt sie deshalb nie als offen (siehe `_fertig`).
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session
from wortlaut import ids, laeufe, metriken, rechenwerk, registry, storage, tempo
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


# Woher eine Zeile stammt (siehe `014_erkennungen_aus_faltungen.sql`).
GEMESSEN = "gemessen"
FALTUNG = "faltung"


def modelle(liste: str) -> list[str]:
    """Die konfigurierte Modellreihe als Liste, leere Einträge weggelassen."""
    return [name.strip() for name in liste.split(",") if name.strip()]


def staende(datenverzeichnis: Path, sprecher_id: str) -> list[str]:
    """Die trainierten Stände dieses Sprechers, jüngster zuletzt.

    Nur die, deren Gewichte wirklich dastehen: Ein Stand ohne `ct2` ließe sich
    zwar aus seinen Faltungen übernehmen, aber nicht auf neuere Aufnahmen
    anwenden - und eine Zeile, die nach dem halben Korpus aufhört, ist keine
    Zeile, die man neben die übrigen stellen kann.
    """
    return [
        ref
        for manifest in registry.alle_staende(datenverzeichnis, sprecher_id)
        if (ref := str(manifest.get("id", "")))
        and registry.ct2_verzeichnis(datenverzeichnis, ref).is_dir()
    ]


def messbare_modelle(datenverzeichnis: Path, sprecher_id: str, liste: str) -> list[str]:
    """Alles, was in dieser Auswertung gegeneinander antritt.

    Die Grundmodelle aus der Konfiguration **und** die trainierten Stände
    dieses Menschen. Dass beide in derselben Spalte stehen, war von Anfang an
    vorgesehen (`005_auswertung.sql`); erst seit den Faltungen ist es auch
    ehrlich möglich.
    """
    return modelle(liste) + staende(datenverzeichnis, sprecher_id)


def tempo_fuer(datenverzeichnis: Path, modell: str) -> float:
    """Mit welchem Faktor vorgespult wird, bevor dieses Modell zuhört.

    **Für ein Grundmodell nie.** Die Auswertung ist die Baseline und misst den
    Ausgangszustand (`012_ohne_profiltempo.sql`).

    **Für einen Stand der Faktor, auf dem er gelernt hat.** Er steht in seinem
    Manifest, „schreiben" spult beim Diktieren genauso vor
    (`apps/schreiben/backend/deps.py`), und seine Faltungen wurden ebenso
    gemessen (`apps/lernen/training/bewerten.py`). Ein Modell für schnelle
    Sprache an langsamer zu messen, ergäbe eine Zahl über eine Lage, die es
    nie gibt.
    """
    if not registry.ist_stand(modell):
        return tempo.VORGABE
    sprecher_id, version = modell.split(registry.TRENNER, 1)
    try:
        manifest = registry.lies_stand(datenverzeichnis, sprecher_id, version)
    except (OSError, ValueError):
        return tempo.VORGABE
    return float(manifest.get("tempo", tempo.VORGABE))


def transkriptor_fuer(
    modell: str, geraet: str, rechenart: str, datenverzeichnis: Path | None = None
) -> Transkriptor:
    """Der Erkenner zu einem Namen - oder zu einem Stand.

    Ein Grundmodell lädt faster-whisper über seinen Namen, einen Stand über
    das Verzeichnis seiner Gewichte. Denselben Unterschied macht „schreiben"
    an derselben Stelle; hier steht er, weil die Auswertung seit den
    Faltungen beide misst.
    """
    if modell not in _transkriptoren:
        from wortlaut.whisper.local import LokalerTranskriptor

        quelle: str | Path = modell
        if registry.ist_stand(modell) and datenverzeichnis is not None:
            quelle = registry.ct2_verzeichnis(datenverzeichnis, modell)
        _transkriptoren[modell] = LokalerTranskriptor(
            quelle, geraet=geraet, rechenart=rechenart
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


# Die Maße, die eine übernommene Faltungszeile mitbringen muss. Fehlt eines,
# ist die Zeile unbrauchbar - eine halbe Messung ist keine.
_MASSE = ("wer", "cer", "mer", "wil", "genauigkeit")


def uebernimm_faltungen(db: Session, datenverzeichnis: Path, sprecher_id: str) -> int:
    """Die Kreuzvalidierung jedes Standes in `erkennungen` übernehmen.

    **Warum übernehmen und nicht rechnen.** Ein trainierter Stand hat die
    meisten Aufnahmen dieses Korpus im Training gehört. Ihn darauf loszulassen
    ergäbe eine Zahl über sein Gedächtnis und nicht über sein Hörvermögen. Für
    genau diese Aufnahmen liegt die ehrliche Messung längst vor: Jede von ihnen
    wurde in einer der sechs Faltungen von einem Modell gehört, das sie
    zurückgehalten bekommen hatte (`apps/lernen/training/bewerten.py`).

    **Warum hier und nicht am Ende des Trainings.** Weil es dann einmal
    geschähe und für die Läufe von gestern nie. So geschieht es vor jedem
    Auswertungslauf, ist in sich wiederholbar - was schon steht, wird nicht
    noch einmal geschrieben - und holt alte Läufe von selbst nach.

    Gibt zurück, wie viele Zeilen neu dazukamen.
    """
    vorhanden = {
        (zeile.recording_id, zeile.modell, zeile.variante)
        for zeile in db.execute(
            select(Erkennung.recording_id, Erkennung.modell, Erkennung.variante).where(
                Erkennung.herkunft == FALTUNG
            )
        ).all()
    }
    gueltig = {aufnahme.id for aufnahme, _ in gueltige_aufnahmen(db)}

    neu = 0
    for manifest in registry.alle_staende(datenverzeichnis, sprecher_id):
        ref = str(manifest.get("id", ""))
        job = str(manifest.get("job_id", ""))
        if not ref or not job:
            continue
        verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, job)
        faktor = float(manifest.get("tempo", tempo.VORGABE))
        for zeile in laeufe.lies_zeilen(verzeichnis / laeufe.BEWERTUNG):
            kennung = str(zeile.get("recording_id") or "")
            fassung = str(zeile.get("variante") or augmentierung.ORIGINAL)
            # Eine Aufnahme, die es nicht mehr gibt oder die verworfen wurde,
            # ist kein Prüfstück mehr - der gemeinsame Boden ist der Korpus von
            # heute und nicht der von damals.
            if not kennung or kennung not in gueltig:
                continue
            if (kennung, ref, fassung) in vorhanden:
                continue
            if any(zeile.get(mass) is None for mass in _MASSE):
                continue
            db.add(
                Erkennung(
                    id=ids.neue_id("erk"),
                    recording_id=kennung,
                    modell=ref,
                    variante=fassung,
                    text=str(zeile.get("text") or ""),
                    **{mass: float(zeile[mass]) for mass in _MASSE},
                    rechenzeit_s=float(zeile.get("rechenzeit_s") or 0.0),
                    # Das Rechenwerk des Trainers, nicht das dieser Maschine.
                    # Es steht da, damit die Ansicht die Rechenzeit **nicht**
                    # neben die übrigen stellt (siehe `zeit_vergleichbar` in
                    # `apps/lernen/backend/api/modelle.py`).
                    rechenwerk=str(zeile.get("rechenwerk") or ""),
                    tempo=faktor,
                    herkunft=FALTUNG,
                    erstellt=jetzt(),
                )
            )
            vorhanden.add((kennung, ref, fassung))
            neu += 1
    if neu:
        db.commit()
    return neu


def vergiss_verschwundene_staende(db: Session, datenverzeichnis: Path, sprecher_id: str) -> int:
    """Zeilen von Ständen wegräumen, die es nicht mehr gibt.

    Wer einen Lauf löscht, löscht alles, was aus ihm hervorging
    (`apps/lernen/backend/services/auftraege.py`). Seine Messungen stehen aber
    hier, in der Tabelle von „hören" - und bis September 2026 gab es in dieser
    Tabelle nichts, was ein Lauf hinterlassen konnte.

    Aufgeräumt wird hier und nicht dort, weil diese Tabelle hierher gehört: Ein
    Löschvorgang in „lernen", der in den Korpus greift, wäre ein zweiter
    Schreiber darauf (Grundentscheidung 6).

    Gemessen wird am **Manifest** und nicht an den Gewichten: Ein Stand, dessen
    `ct2` fehlt, kann keine neue Aufnahme mehr hören, aber seine Faltungen
    beschreiben nach wie vor, was er konnte. Sie wegzuwerfen hieße, eine
    Messung zu verlieren, die niemand wiederherstellen kann.
    """
    vorhanden = {
        str(manifest.get("id", ""))
        for manifest in registry.alle_staende(datenverzeichnis, sprecher_id)
    }
    verwaist = [
        modell
        for modell in db.scalars(select(Erkennung.modell).distinct())
        if registry.ist_stand(modell) and modell not in vorhanden
    ]
    if not verwaist:
        return 0
    anzahl = (
        db.scalar(
            select(func.count()).select_from(Erkennung).where(Erkennung.modell.in_(verwaist))
        )
        or 0
    )
    db.execute(delete(Erkennung).where(Erkennung.modell.in_(verwaist)))
    db.commit()
    return anzahl


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

    **Ausgenommen sind die übernommenen Faltungszeilen.** Sie lassen sich nicht
    neu rechnen: Die sechs Modelle, die sie gemessen haben, sind nach ihrem
    Lauf gelöscht, und der siebte kennt diese Aufnahmen auswendig. Sie bei
    einem Wechsel der Karte für offen zu erklären hieße, sie durch eine
    Messung zu ersetzen, die schlechter ist - oder die Zeile ganz zu verlieren
    (siehe `014_erkennungen_aus_faltungen.sql`).
    """
    return {
        (zeile.recording_id, zeile.modell, zeile.variante)
        for zeile in db.execute(
            select(Erkennung.recording_id, Erkennung.modell, Erkennung.variante).where(
                (Erkennung.rechenwerk == werk) | (Erkennung.herkunft == FALTUNG)
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
                # Dieselbe Einschränkung wie in `_fertig`, samt derselben
                # Ausnahme: Was auf einem anderen Rechenwerk entstand, ist
                # offen und nicht erledigt - sonst stünde der Balken bei 100 %,
                # während der Lauf noch rechnet. Eine übernommene
                # Faltungsmessung zählt dagegen immer als erledigt, denn sie
                # kann gar nicht neu entstehen.
                (Erkennung.rechenwerk == werk) | (Erkennung.herkunft == FALTUNG),
            )
        )
        or 0
    )
    return erledigt, aufnahmen * len(namen) * len(augmentierung.VARIANTEN)


def _rechne(
    posten: Posten,
    wav: Path,
    sprache: str,
    transkriptor: Transkriptor,
    werk: str,
    faktor: float = tempo.VORGABE,
) -> Erkennung:
    """Erkennen und messen - der Teil, der rechnet und keine Datenbank anfasst.

    **Ein Grundmodell hört bei einfacher Geschwindigkeit.** Hier stand einmal
    ein Vorspulen nach dem Profilfaktor des Sprechers; er ist im September 2026
    gefallen (`012_ohne_profiltempo.sql`). Die Auswertung ist die Baseline und
    misst den Ausgangszustand.

    **Ein trainierter Stand hört so, wie er gelernt hat.** Sein Faktor steht in
    seinem Manifest; die Faltungen desselben Laufs wurden damit gemessen, und
    „schreiben" spult beim Diktieren ebenso vor. Ein Modell für schnelle
    Sprache an langsamer zu messen, ergäbe eine Zahl über eine Lage, die es
    nie gibt (`tempo_fuer`).
    """
    with tempfile.TemporaryDirectory() as zwischen:
        if tempo.vorspulen_noetig(faktor):
            schnell = Path(zwischen) / "vorgespult.wav"
            tempo.spule_vor(wav, schnell, faktor)
            wav = schnell
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
        tempo=faktor,
        herkunft=GEMESSEN,
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
    datenverzeichnis: Path,
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
                transkriptor_fuer(posten.modell, geraet, rechenart, datenverzeichnis),
                werk,
                tempo_fuer(datenverzeichnis, posten.modell),
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


def gleiche_ab(db: Session, datenverzeichnis: Path, sprecher_id: str) -> None:
    """Die Tabelle mit dem in Einklang bringen, was an Ständen dasteht.

    **Nicht erst beim Anstoßen eines Laufs.** Die Messungen der
    Kreuzvalidierung liegen fertig da; sie zu übernehmen kostet keine
    Rechenzeit, sondern ein paar Zeilen aus einer Datei. Erst danach stimmt,
    was die Ansicht zeigt: der Vergleich, den es schon gibt, und die Zahl
    dessen, was wirklich noch zu rechnen ist. Wer das an den Startknopf
    hängte, zeigte bis zum ersten Druck zu wenige fertige und zu viele offene
    Posten - und verlangte eine Rechnung für etwas, das längst gemessen ist.
    """
    vergiss_verschwundene_staende(db, datenverzeichnis, sprecher_id)
    uebernimm_faltungen(db, datenverzeichnis, sprecher_id)


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
    datenverzeichnis: Path,
    geraet: str = rechenwerk.AUTO,
    rechenart: str = rechenwerk.AUTO,
) -> Stand:
    """Einen Lauf anstoßen. Läuft schon einer, bleibt es bei ihm.

    **Zuerst werden die Faltungen übernommen.** Erst danach steht fest, was
    wirklich offen ist: Ein trainierter Stand bringt für die meisten Aufnahmen
    schon eine Messung mit, und nur die Aufnahmen, die es beim Training noch
    nicht gab, muss er selbst hören (`uebernimm_faltungen`).

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
        gleiche_ab(db, datenverzeichnis, sprecher_id)
        if not offene_posten(db, namen, werk):
            erledigt, gesamt = zaehle(db, namen, werk)
            return Stand(
                laeuft=False, sprecher_id=sprecher_id, erledigt=erledigt, gesamt=gesamt
            )

    stand_neu = Stand(laeuft=True, sprecher_id=sprecher_id)
    uebersprungen: set[tuple[str, str, str]] = set()
    aufgabe = asyncio.create_task(
        _arbeite(
            engine,
            ablage,
            namen,
            sprache,
            geraet,
            rechenart,
            stand_neu,
            uebersprungen,
            datenverzeichnis,
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
