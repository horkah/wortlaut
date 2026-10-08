"""Die Auswertung: Wie gut hören verschiedene Modelle diesem Sprecher zu?

Zu jeder Aufnahme steht die Vorlage daneben; jede ist damit eine Prüfaufgabe.
Diese Datei schickt jede brauchbare Aufnahme durch jedes Modell und misst
gegen die Vorlage.

* **Im Hintergrund**, denn ein Lauf dauert Minuten bis Stunden; die
  Oberfläche fragt den Stand ab.
* **Von Hand angestoßen**, nie beim Hochfahren - ein Neustart bände sonst
  ungefragt Rechenzeit.
* **Modellweise.** Ein Modell rechnet alles, was für es offen ist, dann
  kommt das nächste (`offene_posten`); auf der Karte liegt nur eines
  (`transkriptor_fuer`). Ein Modell zu laden kostet bis zu einer halben
  Minute, und neben einem großen Stand ist für ein zweites kein Platz.
* **Danach ist die Karte frei.** Endet ein Lauf, nimmt `gib_karte_frei` alle
  Erkenner herunter - der Trainer will die ganze Karte und fragt nicht, wer
  sie hält.
* **Wiederholbar.** Fertig ist, was in `erkennungen` steht; ein zweiter Lauf
  rechnet nur, was fehlt.

**Wer antritt:** die Grundmodelle aus der Konfiguration und jeder trainierte
Stand dieses Sprechers mit Gewichten. Ein Stand misst nie, was er gelernt hat
- das wäre eine Zahl über sein Gedächtnis. Für diese Aufnahmen gilt die
Messung seiner Kreuzvalidierung (`uebernimm_faltungen`, `herkunft =
'faltung'`); alles andere rechnet der ausgelieferte Stand selbst, wie ein
Grundmodell. Beide Male misst die Zeile, wie gut er etwas hört, das er nicht
kannte. Übernommene Zeilen tragen das Rechenwerk des Trainers und gelten nie
als offen (`_erledigt`).
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session
from wortlaut import einstellungen, ids, laeufe, metriken, rechenwerk, registry, storage, tempo
from wortlaut.whisper import Transkriptor

from ..db.models import GUELTIG, Aufnahme, Erkennung, Vorlage, jetzt
from . import zuschnitt

_log = logging.getLogger(__name__)


@dataclass
class Stand:
    """Was die Oberfläche über den Lauf wissen will."""

    laeuft: bool = False
    sprecher_id: str = ""
    erledigt: int = 0
    gesamt: int = 0
    uebersprungen: int = 0
    # Woran gerade gerechnet wird - das Modell, damit sichtbar ist,
    # dass es vorangeht, auch wenn eine Aufnahme lange braucht.
    aktuell: str = ""
    fehler: str | None = None


@dataclass
class _Lauf:
    sprecher_id: str
    aufgabe: asyncio.Task[None]
    stand: Stand
    # Was in diesem Lauf nicht ging - nur im Speicher, beim nächsten Lauf
    # wird es neu versucht.
    uebersprungen: set[tuple[str, str]] = field(default_factory=set)


# Ein Lauf zur Zeit, über alle Sprecher - zwei wären zusammen langsamer.
_lauf: _Lauf | None = None

# Der Erkenner des Modells, das gerade rechnet - höchstens einer
# (`transkriptor_fuer`); nach dem Lauf frei (`gib_karte_frei`).
_transkriptoren: dict[str, Transkriptor] = {}


# Woher eine Zeile stammt.
GEMESSEN = "gemessen"
FALTUNG = "faltung"


def staende(datenverzeichnis: Path, sprecher_id: str) -> list[str]:
    """Die trainierten Stände dieses Sprechers, jüngster zuletzt.

    Nur mit Gewichten: Ohne `ct2` hörte er keine neue Aufnahme, und seine
    Reihe hörte nach dem halben Korpus auf.
    """
    return [
        ref
        for manifest in registry.alle_staende(datenverzeichnis, sprecher_id)
        if (ref := str(manifest.get("id", "")))
        and registry.ct2_verzeichnis(datenverzeichnis, ref).is_dir()
    ]


def noch_da(datenverzeichnis: Path, namen: list[str]) -> list[str]:
    """Von einer Modellreihe das, was in diesem Augenblick zu rechnen ist.

    Während eines Laufs kann ein Stand verschwinden; er fällt dann heraus,
    statt je Posten in denselben Fehler zu laufen. Ein Grundmodell bleibt.
    """
    return [
        name
        for name in namen
        if not registry.ist_stand(name)
        or registry.ct2_verzeichnis(datenverzeichnis, name).is_dir()
    ]


def messbare_modelle(datenverzeichnis: Path, sprecher_id: str, liste: str) -> list[str]:
    """Alles, was in dieser Auswertung gegeneinander antritt.

    Die Grundmodelle aus der Konfiguration und die Stände dieses Menschen.
    """
    return einstellungen.liste(liste) + staende(datenverzeichnis, sprecher_id)


def gewichte(datenverzeichnis: Path, modell: str) -> Path:
    """Das Verzeichnis, aus dem faster-whisper einen Stand lädt.

    Fehlt es, sagt es das hier - faster-whisper hielte den Pfad sonst für einen
    Namen auf dem Hub und meldete etwas Unverständliches.
    """
    verzeichnis = registry.ct2_verzeichnis(datenverzeichnis, modell)
    if not verzeichnis.is_dir():
        raise FileNotFoundError(
            f"Die Gewichte von {registry.beschriftung(modell)} liegen nicht mehr da."
        )
    return verzeichnis


def transkriptor_fuer(
    modell: str, geraet: str, rechenart: str, datenverzeichnis: Path | None = None
) -> Transkriptor:
    """Der Erkenner zu einem Namen - oder zu einem Stand.

    Ein Grundmodell über seinen Namen, ein Stand über seine Gewichte.

    Auf der Karte liegt nur einer: Kommt ein anderes Modell an die Reihe, geht
    das vorige erst herunter. Mehrere nebeneinander ließen einem großen Stand
    keinen Platz - er wiche auf den Prozessor aus und rechnete ein Vielfaches
    länger -, und einem Training daneben ebenso wenig. Weil ein Modell alles
    rechnet, bevor das nächste drankommt (`offene_posten`), lädt jedes einmal.
    """
    if modell not in _transkriptoren:
        from wortlaut.whisper.local import LokalerTranskriptor

        gib_karte_frei()

        quelle: str | Path = modell
        if registry.ist_stand(modell) and datenverzeichnis is not None:
            quelle = gewichte(datenverzeichnis, modell)
        _transkriptoren[modell] = LokalerTranskriptor(
            quelle, geraet=geraet, rechenart=rechenart
        )
    return _transkriptoren[modell]


def gib_karte_frei() -> None:
    """Alle Erkenner der Auswertung herunternehmen - die Karte wird wieder frei.

    Ein entfernter Erkenner hält nichts und kennt `entlade` nicht.
    """
    for erkenner in _transkriptoren.values():
        entlade = getattr(erkenner, "entlade", None)
        if entlade is not None:
            entlade()
    _transkriptoren.clear()


@dataclass(frozen=True)
class Posten:
    """Eine offene Rechenaufgabe: diese Aufnahme durch dieses Modell."""

    aufnahme_id: str
    blob: str
    referenz: str
    modell: str

    @property
    def marke(self) -> tuple[str, str]:
        """Was diesen Posten eindeutig macht - der Schlüssel für „schon gerechnet"."""
        return (self.aufnahme_id, self.modell)


# Der Ton, auf dem ein Lauf eine Aufnahme kannte: Pfad und Dauer aus dem
# Manifest. `None`, wenn das Manifest fehlt.
Ton = tuple[str, float] | None

# Je Laufverzeichnis das Gelesene samt dem Stand der Dateien - gefragt wird
# bei jedem Posten und jeder Abfrage des Fortschritts.
_gehoert_zwischen: dict[Path, tuple[tuple[float, float], dict[str, Ton]]] = {}


def _mtime(pfad: Path) -> float:
    try:
        return pfad.stat().st_mtime
    except OSError:
        return 0.0


def _gehoert_im_lauf(verzeichnis: Path) -> dict[str, Ton]:
    """Welche Aufnahmen ein Lauf kannte - und auf welchem Ton.

    Was im Manifest steht und was seine Faltungen gemessen haben - Letzteres,
    weil die Bewertung übernommen wird, auch wenn das Manifest fehlt.

    Ein Kernlauf kannte nur seinen Kern (`wortlaut/laeufe.py`, „Die Auswahl");
    die übrigen Aufnahmen rechnet der ausgelieferte Stand hier selbst.
    """
    manifest, bewertung = verzeichnis / laeufe.MANIFEST, verzeichnis / laeufe.BEWERTUNG
    auswahl = verzeichnis / laeufe.KERNAUSWAHL
    stempel = (_mtime(manifest), _mtime(bewertung), _mtime(auswahl))
    zwischen = _gehoert_zwischen.get(verzeichnis)
    if zwischen is not None and zwischen[0] == stempel:
        return zwischen[1]

    try:
        kern = laeufe.kern_aus(verzeichnis, laeufe.lies_json(verzeichnis / laeufe.AUFTRAG) or {})
    except RuntimeError:
        # Ohne gewählten Kern gibt es keinen Stand; vorsichtig gilt alles als gehört.
        kern = None

    gehoert: dict[str, Ton] = {}
    for zeile in laeufe.bewertungszeilen(verzeichnis):
        if kennung := str(zeile.get("recording_id") or ""):
            gehoert.setdefault(kennung, None)
    for zeile in laeufe.manifestzeilen(verzeichnis):
        kennung = str(zeile.get("recording_id") or "")
        if not kennung:
            continue
        if kern is not None and kennung not in kern:
            continue
        gehoert[kennung] = (str(zeile.get("audio") or ""), float(zeile.get("dauer_s") or 0.0))
    _gehoert_zwischen[verzeichnis] = (stempel, gehoert)
    return gehoert


def gehoert(datenverzeichnis: Path, namen: list[str]) -> dict[str, dict[str, Ton]]:
    """Je trainiertem Stand unter `namen` die Aufnahmen, die er im Training hatte.

    Auf sie wird ein Stand nie selbst angesetzt; für sie gilt die Messung
    seiner Faltungen oder keine (`derselbe_ton`).
    """
    ergebnis: dict[str, dict[str, Ton]] = {}
    for name in namen:
        if not registry.ist_stand(name):
            continue
        if job := str(registry.lies_ref(datenverzeichnis, name).get("job_id") or ""):
            ergebnis[name] = _gehoert_im_lauf(laeufe.lauf_verzeichnis(datenverzeichnis, job))
    return ergebnis


def verwandte(db: Session, bekannt: dict[str, dict[str, Ton]]) -> dict[str, set[str]]:
    """Je Stand alle Aufnahmen, die er kennt - die gehörten **und** ihre Verwandten.

    Teile und Kopien aus „Editieren" sind derselbe Ton (`zuschnitt.stamm`):
    Wer das Original kannte, kennt den Teil, und umgekehrt. Ein Verwandter
    bringt keine Faltung mit; die Stelle bleibt leer, bis ein Lauf ihn misst.
    """
    if not bekannt:
        return {}
    staemme = {aufnahme.id: zuschnitt.stamm(aufnahme) for aufnahme in db.scalars(select(Aufnahme))}
    ergebnis: dict[str, set[str]] = {}
    for modell, gehoerte in bekannt.items():
        # Eine gelöschte gehörte Aufnahme ist ihr eigener Stamm.
        gehoerte_staemme = {staemme.get(kennung, kennung) for kennung in gehoerte}
        ergebnis[modell] = set(gehoerte) | {
            kennung for kennung, stamm in staemme.items() if stamm in gehoerte_staemme
        }
    return ergebnis


def derselbe_ton(aufnahme: Aufnahme, damals: Ton) -> bool:
    """Ob ein Lauf diese Aufnahme so kannte, wie sie heute ist.

    Ein Zuschnitt überschreibt die Datei unter demselben Pfad
    (`services/zuschnitt.py`), also wird nach der Dauer gefragt. Ohne Manifest
    lässt sich nichts vergleichen; dann gilt die Faltung.
    """
    if damals is None:
        return True
    _, dauer = damals
    return abs(dauer - aufnahme.dauer_s) < 1e-3


def vergiss_ueberholte_faltungen(db: Session, datenverzeichnis: Path, sprecher_id: str) -> int:
    """Die Zeilen eines Standes wegräumen, die nicht mehr den geltenden Ton messen.

    Der Zuschnitt löscht die Messungen einer Aufnahme (`api/zuschnitt.py`),
    der Abgleich übernähme die Faltung aber wieder - also wird sie hier
    weggeräumt und nicht übernommen. Ebenso jede selbst gerechnete Zeile
    eines Standes über etwas, das er kannte (`verwandte`).
    """
    namen = [
        str(manifest.get("id", ""))
        for manifest in registry.alle_staende(datenverzeichnis, sprecher_id)
    ]
    bekannt = gehoert(datenverzeichnis, namen)
    if not bekannt:
        return 0
    aufnahmen = {aufnahme.id: aufnahme for aufnahme, _ in gueltige_aufnahmen(db)}
    gesperrt = verwandte(db, bekannt)
    weg = [
        zeile.id
        for zeile in db.scalars(select(Erkennung).where(Erkennung.modell.in_(list(bekannt))))
        if zeile.recording_id in gesperrt[zeile.modell]
        and (
            zeile.recording_id not in bekannt[zeile.modell]
            or zeile.herkunft != FALTUNG
            or (aufnahme := aufnahmen.get(zeile.recording_id)) is None
            or not derselbe_ton(aufnahme, bekannt[zeile.modell][zeile.recording_id])
        )
    ]
    if not weg:
        return 0
    db.execute(delete(Erkennung).where(Erkennung.id.in_(weg)))
    db.commit()
    return len(weg)


def uebernimm_faltungen(db: Session, datenverzeichnis: Path, sprecher_id: str) -> int:
    """Die Kreuzvalidierung jedes Standes in `erkennungen` übernehmen.

    Für die Aufnahmen, die ein Stand gelernt hat, liegt die ehrliche Messung
    vor: Jede wurde von der Faltung gehört, die sie zurückhielt
    (`apps/lernen/training/bewerten.py`). Übernommen bei jedem Abgleich,
    wiederholbar - was steht, wird nicht noch einmal geschrieben.

    Gibt zurück, wie viele Zeilen neu dazukamen.
    """
    vorhanden = {
        (zeile.recording_id, zeile.modell)
        for zeile in db.execute(
            select(Erkennung.recording_id, Erkennung.modell).where(Erkennung.herkunft == FALTUNG)
        ).all()
    }
    gueltig = {aufnahme.id: aufnahme for aufnahme, _ in gueltige_aufnahmen(db)}

    neu = 0
    for manifest in registry.alle_staende(datenverzeichnis, sprecher_id):
        ref = str(manifest.get("id", ""))
        job = str(manifest.get("job_id", ""))
        if not ref or not job:
            continue
        verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, job)
        faktor = float(manifest.get("tempo", tempo.VORGABE))
        damals = _gehoert_im_lauf(verzeichnis)
        for zeile in laeufe.bewertungszeilen(verzeichnis):
            kennung = str(zeile.get("recording_id") or "")
            # Nur was heute gilt - gelöschte und verworfene Aufnahmen nicht.
            if not kennung or kennung not in gueltig:
                continue
            # Nur auf dem Ton, der heute gilt (`derselbe_ton`).
            if not derselbe_ton(gueltig[kennung], damals.get(kennung)):
                continue
            if (kennung, ref) in vorhanden:
                continue
            if any(zeile.get(mass) is None for mass in metriken.GUETEFELDER):
                continue
            db.add(
                Erkennung(
                    id=ids.neue_id("erk"),
                    recording_id=kennung,
                    modell=ref,
                    text=str(zeile.get("text") or ""),
                    **{mass: float(zeile[mass]) for mass in metriken.GUETEFELDER},
                    rechenzeit_s=float(zeile.get("rechenzeit_s") or 0.0),
                    # Das Rechenwerk des Trainers - die Rechenzeit ist dann nicht
                    # vergleichbar (`zeit_vergleichbar` in „lernen").
                    rechenwerk=str(zeile.get("rechenwerk") or ""),
                    tempo=faktor,
                    herkunft=FALTUNG,
                    erstellt=jetzt(),
                )
            )
            vorhanden.add((kennung, ref))
            neu += 1
    if neu:
        db.commit()
    return neu


def vergiss_verschwundene_staende(db: Session, datenverzeichnis: Path, sprecher_id: str) -> int:
    """Zeilen von Ständen wegräumen, die es nicht mehr gibt.

    Ein gelöschter Lauf nimmt seinen Stand mit, dessen Zeilen stehen aber
    hier - aufgeräumt von „hören", dem einzigen Schreiber (Grundentscheidung
    6). Gemessen am Manifest, nicht an den Gewichten: Die Faltungen eines
    Standes ohne `ct2` beschreiben weiter, was er konnte.
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

    Die Reihenfolge ist die Nummerierung der Kurve.
    """
    return list(
        db.execute(
            select(Aufnahme, Vorlage)
            .join(Vorlage, Vorlage.id == Aufnahme.prompt_id)
            .where(Aufnahme.status == GUELTIG)
            .order_by(*zuschnitt.reihenfolge())
        ).all()
    )


def _erledigt(werk: str) -> tuple:
    """Wann eine Zeile als gemessen zählt - für `where(*_erledigt(werk))`.

    Nur an einer brauchbaren Aufnahme, damit nie Zeilen verworfener
    mitzählen, unabhängig davon, dass das Verwerfen sie wegräumt. Und nur **auf
    dem Rechenwerk, das gerade gilt**: Eine Zeile aus einem anderen oder
    unbekannten gilt als offen, ihre Rechenzeit passte nicht neben die
    übrigen. Ausgenommen sind übernommene Faltungen - die Faltungsmodelle gibt
    es nicht mehr, und der Stand kennt diese Aufnahmen.
    """
    return (
        Erkennung.recording_id.in_(select(Aufnahme.id).where(Aufnahme.status == GUELTIG)),
        (Erkennung.rechenwerk == werk) | (Erkennung.herkunft == FALTUNG),
    )


def _fertig(db: Session, werk: str) -> set[tuple[str, str]]:
    """Was schon gemessen ist (`_erledigt`)."""
    return {
        (zeile.recording_id, zeile.modell)
        for zeile in db.execute(
            select(Erkennung.recording_id, Erkennung.modell).where(*_erledigt(werk))
        ).all()
    }


def offene_posten(
    db: Session,
    namen: list[str],
    werk: str,
    bekannt: dict[str, dict[str, Ton]] | None = None,
) -> list[Posten]:
    """Was noch zu rechnen ist, in der Reihenfolge, in der gerechnet wird.

    Modell, dann Aufnahme: Ein Modell rechnet alles, was für es
    offen ist, bevor das nächste drankommt - in der Reihenfolge von `namen`.
    Ein Modell zu laden kostet bis zu einer halben Minute; je Aufnahme
    gewechselt, käme jedes in jeder Runde wieder an die Reihe.

    Kein Stand über eine Aufnahme, die er kannte (`bekannt`, `verwandte`);
    fehlt dort die Faltung, bleibt die Stelle leer.
    """
    erledigt = _fertig(db, werk)
    gesperrt = verwandte(db, bekannt or {})
    aufnahmen = gueltige_aufnahmen(db)
    return [
        Posten(aufnahme_id=aufnahme.id, blob=aufnahme.blob, referenz=vorlage.text, modell=modell)
        for modell in namen
        for aufnahme, vorlage in aufnahmen
        if aufnahme.id not in gesperrt.get(modell, ())
        and (aufnahme.id, modell) not in erledigt
    ]


def zaehle(
    db: Session,
    namen: list[str],
    werk: str,
    bekannt: dict[str, dict[str, Ton]] | None = None,
) -> tuple[int, int]:
    """(erledigt, gesamt) - beides aus der Datenbank, nie aus einem Zähler.

    Ein mitlaufender Zähler wäre nach einem Neustart falsch. `gesamt` ist
    erledigt plus offen, nicht Aufnahmen mal Modelle - leere
    Stellen eines Standes zählen weder als das eine noch als das andere.
    """
    # Nur konfigurierte Modelle, sonst stünde der Balken über 100 %.
    erledigt = (
        db.scalar(
            select(func.count())
            .select_from(Erkennung)
            .where(Erkennung.modell.in_(namen), *_erledigt(werk))
        )
        or 0
    )
    return erledigt, erledigt + len(offene_posten(db, namen, werk, bekannt))


def _rechne(
    posten: Posten,
    wav: Path,
    sprache: str,
    transkriptor: Transkriptor,
    werk: str,
    faktor: float = tempo.VORGABE,
) -> Erkennung:
    """Erkennen und messen - der Teil, der rechnet und keine Datenbank anfasst.

    Vorgespult mit dem Faktor des Modells (`registry.tempo_von`).
    """
    with tempfile.TemporaryDirectory() as zwischen:
        if tempo.vorspulen_noetig(faktor):
            schnell = Path(zwischen) / "vorgespult.wav"
            tempo.spule_vor(wav, schnell, faktor)
            wav = schnell
        begonnen = time.monotonic()
        transkript = transkriptor.transkribiere(wav, sprache=sprache)
        dauer = time.monotonic() - begonnen
    # Nach dem Erkennen gefragt: Ob die Karte den Platz hergab, zeigt sich
    # beim Laden. Wer nichts meldet (entfernt, Test), bekommt das Rechenwerk
    # des Laufs - leer gälte die Zeile immer wieder als offen.
    werk = getattr(transkriptor, "marke", "") or werk

    guete = metriken.bewerte(posten.referenz, transkript.text)
    return Erkennung(
        id=ids.neue_id("erk"),
        recording_id=posten.aufnahme_id,
        modell=posten.modell,
        text=transkript.text,
        **guete.als_dict(),
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
    uebersprungen: set[tuple[str, str]],
    datenverzeichnis: Path,
) -> None:
    """Der Lauf selbst: einen Posten nach dem anderen, bis nichts mehr offen ist.

    Zustand und Merkliste kommen als Argument, denn die Aufgabe entsteht vor
    `_lauf`. Je Posten eine eigene Sitzung - eine offene hielte stundenlang
    eine Schreibsperre, während womöglich aufgenommen wird.
    """
    # Einmal aufgelöst und fest - der Maßstab für „erledigt" (`_erledigt`).
    werk = rechenwerk.marke(*rechenwerk.waehle(geraet, rechenart))

    while True:
        # Je Durchgang neu (`noch_da`).
        antretende = noch_da(datenverzeichnis, namen)
        with Session(engine) as db:
            bekannt = gehoert(datenverzeichnis, antretende)
            offen = [
                posten
                for posten in offene_posten(db, antretende, werk, bekannt)
                if posten.marke not in uebersprungen
            ]
            zustand.erledigt, zustand.gesamt = zaehle(db, antretende, werk, bekannt)
            zustand.uebersprungen = len(uebersprungen)

        if not offen:
            return

        posten = offen[0]
        zustand.aktuell = registry.beschriftung(posten.modell)

        if not ablage.pfad(posten.blob).is_file():
            # Die übrigen Aufnahmen sind davon unberührt.
            uebersprungen.add(posten.marke)
            zustand.fehler = f"Audio fehlt: {posten.blob}"
            _log.warning("Auswertung: %s", zustand.fehler)
            continue

        try:
            # Im Arbeitsfaden, sonst stünde die Ereignisschleife.
            erkennung = await asyncio.to_thread(
                _rechne,
                posten,
                ablage.pfad(posten.blob),
                sprache,
                transkriptor_fuer(posten.modell, geraet, rechenart, datenverzeichnis),
                werk,
                registry.tempo_von(datenverzeichnis, posten.modell),
            )
        except asyncio.CancelledError:
            raise
        except Exception as ursache:  # noqa: BLE001 - was immer das Modell wirft
            uebersprungen.add(posten.marke)
            zustand.fehler = f"{registry.beschriftung(posten.modell)}: {ursache}"
            # Ins Fehlerprotokoll, samt Ablauf - die Ansicht zeigt nur den Satz.
            _log.error(
                "Auswertung: %s an Aufnahme %s", zustand.fehler, posten.aufnahme_id, exc_info=True
            )
            continue

        with Session(engine) as db:
            # Eine Zeile aus einem anderen Rechenwerk weicht - je Aufnahme
            # und Modell steht genau eine da.
            db.execute(
                delete(Erkennung).where(
                    Erkennung.recording_id == posten.aufnahme_id,
                    Erkennung.modell == posten.modell,
                )
            )
            db.add(erkennung)
            db.commit()


async def _mit_freier_karte_danach(*argumente) -> None:
    """`_arbeite`, und danach die Karte frei - auch bei Abbruch und Fehler.

    In der Aufgabe, nicht im Rückruf - sonst gälte der Lauf als beendet,
    während er die Karte noch hält.
    """
    try:
        await _arbeite(*argumente)
    finally:
        gib_karte_frei()


def gleiche_ab(db: Session, datenverzeichnis: Path, sprecher_id: str) -> None:
    """Die Tabelle mit dem in Einklang bringen, was an Ständen dasteht.

    Beim Öffnen der Ansicht, nicht erst beim Start: Die Faltungen zu
    übernehmen kostet nichts, und erst danach stimmen Vergleich und offene
    Posten.
    """
    vergiss_verschwundene_staende(db, datenverzeichnis, sprecher_id)
    vergiss_ueberholte_faltungen(db, datenverzeichnis, sprecher_id)
    uebernimm_faltungen(db, datenverzeichnis, sprecher_id)


def stand(db: Session, namen: list[str], werk: str, datenverzeichnis: Path | None = None) -> Stand:
    """Der Stand für die Oberfläche - auch dann, wenn gerade kein Lauf läuft."""
    # Erst fragen, ob der Lauf fertig ist, dann zählen: Wird er fertig,
    # während gezählt wird, fehlte sonst sein letzter Posten, und der Stand
    # sagte „fertig" bei 7 von 8.
    lauf = _lauf
    fertig = lauf is None or lauf.aufgabe.done()
    bekannt = gehoert(datenverzeichnis, namen) if datenverzeichnis is not None else None
    erledigt, gesamt = zaehle(db, namen, werk, bekannt)
    if lauf is None:
        return Stand(laeuft=False, erledigt=erledigt, gesamt=gesamt)

    # Eine Abschrift: Den Stand des Laufs ändert auch die Ereignisschleife
    # (`starte`, `_fertig_gemeldet`), und die Antwort soll zu ihrer Zählung passen.
    return replace(lauf.stand, laeuft=not fertig, erledigt=erledigt, gesamt=gesamt)


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

    Zuerst werden die Faltungen übernommen; erst dann steht fest, was offen
    ist. Ist nichts offen, entsteht keine Aufgabe - sie sagte sonst kurz
    `laeuft`, ohne zu laufen. Zurück kommt der Stand mit `laeuft = False`, und
    die Ansicht sagt, dass es nichts zu rechnen gab.
    """
    global _lauf

    if _lauf is not None and not _lauf.aufgabe.done():
        return _lauf.stand

    werk = rechenwerk.marke(*rechenwerk.waehle(geraet, rechenart))
    with Session(engine) as db:
        gleiche_ab(db, datenverzeichnis, sprecher_id)
        bekannt = gehoert(datenverzeichnis, namen)
        if not offene_posten(db, namen, werk, bekannt):
            erledigt, gesamt = zaehle(db, namen, werk, bekannt)
            return Stand(
                laeuft=False, sprecher_id=sprecher_id, erledigt=erledigt, gesamt=gesamt
            )

    stand_neu = Stand(laeuft=True, sprecher_id=sprecher_id)
    uebersprungen: set[tuple[str, str]] = set()
    aufgabe = asyncio.create_task(
        _mit_freier_karte_danach(
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
            _log.error("Auswertung abgebrochen: %s", ursache, exc_info=ursache)

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
