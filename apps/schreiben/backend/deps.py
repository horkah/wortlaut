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
from wortlaut import db, registry, storage
from wortlaut import zugang as zugangsdienst
from wortlaut.whisper import Transkriptor

from .config import Einstellungen, einstellungen

# Engines und Transkriptoren sind teuer im Aufbau und je Sprecher
# wiederverwendbar. Ein Modell bleibt nach dem ersten Diktat im Speicher; ein
# Neuladen je Anfrage würde jede Antwort um Sekunden verzögern.
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
    """Die konfigurierte Whisper-Umsetzung - je Sprecher, denn je Sprecher ein Modell."""
    if sprecher_id not in _transkriptoren:
        konfiguration = einstellungen()

        if konfiguration.asr == "remote":
            from wortlaut.whisper.remote import EntfernterTranskriptor

            _transkriptoren[sprecher_id] = EntfernterTranskriptor(
                konfiguration.asr_endpoint,
                konfiguration.asr_api_key,
                modell=konfiguration.asr_modell,
            )
        else:
            from wortlaut.whisper.local import LokalerTranskriptor

            _transkriptoren[sprecher_id] = LokalerTranskriptor(
                modellpfad(konfiguration, sprecher_id)
            )
    return _transkriptoren[sprecher_id]


def modellstand(konfiguration: Einstellungen, sprecher_id: str) -> tuple[str, dict] | None:
    """Der Stand, der für diesen Sprecher gilt: `(ref, manifest)` - oder None.

    Der Normalfall ist der freigegebene Stand *dieses* Sprechers: Ein Modell
    gehört zu genau einem Menschen (Grundentscheidung 3), und wer hier
    diktiert, soll auf seiner eigenen Stimme laufen. `WORTLAUT_MODELL_REF`
    überschreibt das für alle - zum Erproben eines Standes, nicht für den
    Betrieb.
    """
    if konfiguration.modell_ref:
        ref_sprecher, version = konfiguration.modell_ref.split("/", 1)
        try:
            return konfiguration.modell_ref, registry.lies_stand(
                konfiguration.data_dir, ref_sprecher, version
            )
        except (OSError, ValueError):
            # Falsch gesetzte Umgebung soll man sehen, nicht raten müssen -
            # die Auskunft in `api/model.py` sagt es dann ausdrücklich.
            return konfiguration.modell_ref, {}

    stand = registry.aktiver_stand(konfiguration.data_dir, sprecher_id)
    return (str(stand["id"]), stand) if stand else None


def modellpfad(konfiguration: Einstellungen, sprecher_id: str) -> Path | str:
    """Was faster-whisper geladen bekommt: Registry-Verzeichnis oder Modellname.

    Mit einem Stand ist es dessen `ct2/`-Ordner. Ohne ihn ist es der bloße Name
    aus `WORTLAUT_ASR_MODELL` - das unveränderte Whisper-Modell, mit dem eine
    Installation anfängt, solange „lernen" für diesen Sprecher nichts
    freigegeben hat.
    """
    stand = modellstand(konfiguration, sprecher_id)
    if stand is None:
        return konfiguration.asr_modell
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
    return transkriptor_fuer(sprecher_id)


# Kurzschreibweisen für die Signaturen der Endpunkte.
Wer = Annotated[zugangsdienst.Sprecherzugang, Depends(_wer_ruft)]
SprecherId = Annotated[str, Depends(_sprecher_id)]
Zugangstoken = Annotated[str, Depends(_vorgelegt)]
Datenbank = Annotated[Session, Depends(_sitzung)]
Ablage = Annotated[storage.Ablage, Depends(_ablage)]
Whisper = Annotated[Transkriptor, Depends(_transkriptor)]
