"""Gemeinsame Abhängigkeiten der Endpunkte: Datenbank, Ablage, Transkription.

Kein Token und kein Sprecherparameter: Eine Instanz gehört zu genau einer
Person und einem Modellstand (Grundentscheidung 7). Was in „hören" der
Abfrageparameter `sprecher` ist, steht hier in der Konfiguration.

Alle drei Bausteine sind absichtlich Abhängigkeiten und keine Importe: So kann
ein Test die Transkription ersetzen, ohne faster-whisper zu installieren.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from wortlaut import db, storage
from wortlaut.whisper import Transkriptor

from .config import Einstellungen, einstellungen


@lru_cache
def engine() -> Engine:
    """Die eine Datenbank dieser Instanz; legt sie beim ersten Zugriff an.

    „hören" wendet seine Migrationen beim Anlegen eines Sprechers an — diesen
    Zeitpunkt gibt es hier nicht, also geschieht es beim ersten Zugriff.
    """
    konfiguration = einstellungen()
    db.wende_migrationen_an(konfiguration.datenbank, konfiguration.migrationsverzeichnis)
    return db.verbinde(konfiguration.datenbank)


@lru_cache
def transkriptor() -> Transkriptor:
    """Die konfigurierte Whisper-Umsetzung — einmal gebaut, oft benutzt.

    Das Modell selbst lädt erst beim ersten Transkribieren und bleibt dann im
    Speicher; ein Neuladen je Anfrage würde jede Antwort um Sekunden verzögern.
    """
    konfiguration = einstellungen()

    if konfiguration.asr == "remote":
        from wortlaut.whisper.remote import EntfernterTranskriptor

        return EntfernterTranskriptor(
            konfiguration.asr_endpoint,
            konfiguration.asr_api_key,
            modell=konfiguration.asr_modell,
        )

    from wortlaut.whisper.local import LokalerTranskriptor

    return LokalerTranskriptor(modellpfad(konfiguration))


def modellpfad(konfiguration: Einstellungen) -> Path | str:
    """Was faster-whisper geladen bekommt: Registry-Verzeichnis oder Modellname.

    Mit `WORTLAUT_MODELL_REF` ist es der `ct2/`-Ordner eines Modellstands aus
    „lernen". Ohne ihn ist es der bloße Name aus `WORTLAUT_ASR_MODELL` — das
    unveränderte Whisper-Modell, mit dem eine Installation anfängt.
    """
    from wortlaut import registry

    if not konfiguration.modell_ref:
        return konfiguration.asr_modell
    sprecher_id, version = konfiguration.modell_ref.split("/", 1)
    return registry.stand_verzeichnis(konfiguration.data_dir, sprecher_id, version) / "ct2"


def zwischenspeicher_leeren() -> None:
    """Nach einer Konfigurationsänderung — in erster Linie für Tests."""
    if engine.cache_info().currsize:
        engine().dispose()
    engine.cache_clear()
    transkriptor.cache_clear()


def _sitzung() -> Iterator[Session]:
    with Session(engine()) as sitzung:
        yield sitzung


def _ablage() -> storage.Ablage:
    return storage.oeffne_ablage(einstellungen().storage, einstellungen().data_dir)


# Kurzschreibweisen für die Signaturen der Endpunkte.
Datenbank = Annotated[Session, Depends(_sitzung)]
Ablage = Annotated[storage.Ablage, Depends(_ablage)]
Whisper = Annotated[Transkriptor, Depends(transkriptor)]
