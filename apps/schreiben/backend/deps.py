"""Gemeinsame Abhängigkeiten der Endpunkte: Zugang, Datenbank, Ablage, Whisper.

Hier hängt die Bindung zwischen Aufrufer und Verzeichnis - dieselbe Aufgabe
wie in `apps/hoeren/backend/deps.py` und aus demselben Grund: Der Sprecher wird
aus dem vorgelegten Zugang **abgeleitet** und nirgends behauptet. Wer diktiert,
legt denselben Zugang vor, den „hören" für ihn ausgegeben hat
(`<sprecher_id>.<geheimnis>`, siehe `wortlaut.zugang`); geprüft wird er lesend
gegen den Korpus.

Dass diese App überhaupt einen Sprecher führt, ist neu. Sie war einmal auf
genau eine Person konfiguriert. Zwei Dinge haben das aufgehoben: Jeder Sprecher
bekommt aus „lernen" sein eigenes Modell, und was er hier diktiert, fließt als
Korrektur in *seinen* Korpus zurück. Beides braucht die Kennung zur Laufzeit -
eine Instanz je Person wäre eine Instanz je Modell und je Korpus gewesen.

Ohne gültigen Zugang gibt es hier nichts: keine Sitzung, kein Diktat, keine
Ablage. Das ist kein Anmeldeformular vor der Tür - der Zugang kommt über
denselben persönlichen Link wie bei „hören" und liegt danach im Browser
(beide Apps teilen sich eine Domain und damit den `localStorage`). Wer schlecht
liest, muss also weiterhin nichts tippen.

Alle Bausteine sind absichtlich Abhängigkeiten und keine Importe: So kann ein
Test die Transkription ersetzen, ohne faster-whisper zu installieren.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from wortlaut import db, registry, storage, tempo
from wortlaut import zugang as zugangsdienst
from wortlaut.whisper import Transkriptor

from .config import Einstellungen, einstellungen

# Engines und Transkriptoren sind teuer im Aufbau und wiederverwendbar. Ein
# Modell bleibt nach dem ersten Diktat im Speicher; ein Neuladen je Anfrage
# würde jede Antwort um Sekunden verzögern - auf der Karte kämen dabei noch
# das Belegen und Freigeben ihres Speichers dazu.
#
# Der Schlüssel der Transkriptoren ist das **Modell** und nicht der Sprecher:
# Seit sich das Modell zur Laufzeit freigeben lässt (`wortlaut/registry.py`),
# gäbe ein Zwischenspeicher je Sprecher nach einem Wechsel weiter das alte
# Modell heraus - ein Fehler, den niemand als Fehler erkennte, weil einfach
# der gewohnte Text herauskäme.
_engines: dict[str, Engine] = {}
_transkriptoren: dict[str, Transkriptor] = {}


def engine_fuer(sprecher_id: str) -> Engine:
    """Die Diktatdatenbank eines Sprechers; legt sie beim ersten Zugriff an.

    „hören" wendet seine Migrationen beim Anlegen eines Sprechers an - diesen
    Zeitpunkt gibt es hier nicht, also geschieht es beim ersten Zugriff. Anlegen
    ist hier unbedenklich: Es ist die eigene Ablage dieser App und nicht der
    Korpus, den allein „hören" schreibt (Grundentscheidung 6).
    """
    if sprecher_id not in _engines:
        konfiguration = einstellungen()
        pfad = konfiguration.datenbank(sprecher_id)
        db.wende_migrationen_an(pfad, konfiguration.migrationsverzeichnis)
        _engines[sprecher_id] = db.verbinde(pfad)
    return _engines[sprecher_id]


def transkriptor_fuer(sprecher_id: str) -> Transkriptor:
    """Die Whisper-Umsetzung für das Modell, das dieser Mensch benutzt.

    Zwischengespeichert wird nach dem, was tatsächlich geladen wird - zwei
    Sprecher auf demselben Grundmodell teilen es sich, und eine neue Freigabe
    lädt wirklich ein anderes.
    """
    konfiguration = einstellungen()
    schluessel = str(modellpfad(konfiguration, sprecher_id))

    if schluessel not in _transkriptoren:
        if konfiguration.asr == "remote":
            from wortlaut.whisper.remote import EntfernterTranskriptor

            _transkriptoren[schluessel] = EntfernterTranskriptor(
                konfiguration.asr_endpoint,
                konfiguration.asr_api_key,
                modell=konfiguration.asr_modell,
            )
        else:
            from wortlaut.whisper.local import LokalerTranskriptor

            # Gerät und Rechenart kommen aus der Konfiguration und damit aus
            # derselben Quelle wie bei der Auswertung in „hören" und beim
            # Trainer (`wortlaut/rechenwerk.py`). Das ist nicht nur Ordnung:
            # Nur so misst die Modellübersicht Rechenzeiten, die zu dem passen,
            # was hier tatsächlich geschieht.
            _transkriptoren[schluessel] = LokalerTranskriptor(
                schluessel,
                geraet=konfiguration.geraet,
                rechenart=konfiguration.rechenart,
            )
    return _transkriptoren[schluessel]


def aktive_ref(konfiguration: Einstellungen, sprecher_id: str) -> str:
    """Was für diesen Menschen gilt - eine Standkennung oder ein Grundmodellname.

    Die Rangfolge steht in `api/model.py`; hier wird sie ausgeführt:

    1. `WORTLAUT_MODELL_REF` - der eine Stand für alle, zum Erproben.
    2. Die Freigabe *dieses* Sprechers (`wortlaut/registry.py`). Sie entsteht
       in der Modellübersicht von „lernen" und kann seit deren Zusammenlegung
       auch ein unverändertes Grundmodell benennen.

    Leer heißt: nichts freigegeben - dann gilt `WORTLAUT_ASR_MODELL`.
    """
    if konfiguration.modell_ref:
        return konfiguration.modell_ref
    return registry.freigegeben(konfiguration.data_dir, sprecher_id)


def modellstand(
    konfiguration: Einstellungen, sprecher_id: str
) -> tuple[str, dict] | None:
    """Der Stand, der gerade gilt: `(ref, manifest)` - oder None für ein Grundmodell."""
    ref = aktive_ref(konfiguration, sprecher_id)
    if not ref or not registry.ist_stand(ref):
        return None

    ref_sprecher, version = ref.split("/", 1)
    try:
        return ref, registry.lies_stand(konfiguration.data_dir, ref_sprecher, version)
    except (OSError, ValueError):
        # Ein Stand, den es nicht gibt - falsch gesetzte Umgebung oder ein
        # gelöschter Stand, der noch freigegeben ist. Sehen soll man das, nicht
        # raten müssen: Die Auskunft in `api/model.py` sagt es ausdrücklich.
        return ref, {}


def tempo_fuer(konfiguration: Einstellungen, sprecher_id: str) -> float:
    """Mit welchem Faktor vorgespult wird, bevor das Modell zuhört.

    **Mit einem Stand: der Faktor, auf dem er gelernt hat.** Ein Modell, das
    nur vorgespulte Sprache gehört hat, muss sie auch hier bekommen. Bekäme es
    ungespulte, träfe ein Modell für schnelle Sprache auf einen langsamen
    Sprecher - und das Ergebnis wäre schlechter als ganz ohne Training, ohne
    dass irgendwo ein Fehler stünde. Der Faktor steht im Manifest des Standes
    (`apps/lernen/training/bewerten.py`), also wird er dort gelesen und nicht
    geraten.

    **Ohne Stand: gar nicht.** Dann rechnet ein unverändertes Grundmodell, und
    das ist genau das, was die Auswertung in „hören" als Baseline misst - dort
    wird seit `012_ohne_profiltempo.sql` ebenfalls nicht mehr vorgespult.

    Hier stand einmal ein Rückgriff auf einen Tempofaktor am Sprecherprofil.
    Den gibt es nicht mehr: Was das Vorspulen bringt, sucht der Trainer selbst
    und trägt es im Stand mit sich.
    """
    stand = modellstand(konfiguration, sprecher_id)
    if stand is None:
        return tempo.VORGABE
    return float(stand[1].get("tempo", tempo.VORGABE))


def modellpfad(konfiguration: Einstellungen, sprecher_id: str) -> Path | str:
    """Was faster-whisper geladen bekommt: Registry-Verzeichnis oder Modellname.

    Mit einem Stand ist es dessen `ct2/`-Ordner. Ohne ihn ist es ein bloßer
    Name - das freigegebene Grundmodell oder `WORTLAUT_ASR_MODELL`, mit dem
    eine Installation anfängt, solange „lernen" nichts freigegeben hat.
    """
    stand = modellstand(konfiguration, sprecher_id)
    if stand is None:
        return aktive_ref(konfiguration, sprecher_id) or konfiguration.asr_modell
    # Auch dann das Verzeichnis, wenn das Manifest nicht zu lesen war: Was
    # verlangt wurde, soll versucht werden. Still auf das Grundmodell
    # auszuweichen hieße, einen Fehlgriff in der Konfiguration als gutes
    # Ergebnis auszugeben - die Kopfzeile sagt stattdessen, dass der Stand
    # fehlt (siehe `api/model.py`).
    ref_sprecher, version = stand[0].split("/", 1)
    return registry.stand_verzeichnis(konfiguration.data_dir, ref_sprecher, version) / "ct2"


def zwischenspeicher_leeren() -> None:
    """Nach einer Konfigurationsänderung - in erster Linie für Tests."""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()
    _transkriptoren.clear()


def _vorgelegt(authorization: Annotated[str | None, Header()] = None) -> str:
    """Der rohe Zugang aus dem Kopf der Anfrage.

    Er wird durchgereicht bis in den Postausgang: Was an „hören" geht, geht mit
    dem Zugang dessen, der es bestätigt hat (siehe `services/outbox.py`).
    """
    return (authorization or "").removeprefix("Bearer ")


def _wer_ruft(vorgelegt: Annotated[str, Depends(_vorgelegt)]) -> zugangsdienst.Sprecherzugang:
    """Die Kennung aus dem Vorgelegten ableiten - die einzige Stelle, die das tut.

    Ein Verwalter- oder Aufsichtstoken kommt hier bewusst nicht durch: Diese App
    hat nichts zu verwalten, sie spricht für einen Menschen. Wer keinen
    Sprecherzugang hat, hat hier auch keine Diktate.
    """
    wer = zugangsdienst.pruefe(einstellungen().data_dir, vorgelegt)
    if wer is None:
        raise HTTPException(
            status_code=401,
            detail="Dieser Zugang gilt nicht. Diktieren kann, wer den persönlichen Link geöffnet hat.",
        )
    return wer


def _sprecher_id(wer: Annotated[zugangsdienst.Sprecherzugang, Depends(_wer_ruft)]) -> str:
    return wer.sprecher_id


def _sitzung(sprecher_id: Annotated[str, Depends(_sprecher_id)]) -> Iterator[Session]:
    with Session(engine_fuer(sprecher_id)) as sitzung:
        yield sitzung


def _ablage() -> storage.Ablage:
    return storage.oeffne_ablage(einstellungen().storage, einstellungen().data_dir)


def _transkriptor(sprecher_id: Annotated[str, Depends(_sprecher_id)]) -> Transkriptor:
    """Der Erkenner mit dem Modell, das für diesen Menschen freigegeben ist.

    Gelesen wird die Freigabe bei jeder Anfrage und nicht beim Start: Das ist
    der Preis dafür, dass eine neue Freigabe in „lernen" sofort gilt, ohne
    einen Container neu zu starten.
    """
    return transkriptor_fuer(sprecher_id)


# Kurzschreibweisen für die Signaturen der Endpunkte.
Wer = Annotated[zugangsdienst.Sprecherzugang, Depends(_wer_ruft)]
SprecherId = Annotated[str, Depends(_sprecher_id)]
Zugangstoken = Annotated[str, Depends(_vorgelegt)]
Datenbank = Annotated[Session, Depends(_sitzung)]
Ablage = Annotated[storage.Ablage, Depends(_ablage)]
Whisper = Annotated[Transkriptor, Depends(_transkriptor)]
