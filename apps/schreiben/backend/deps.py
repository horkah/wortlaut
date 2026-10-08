"""Gemeinsame Abhängigkeiten der Endpunkte: Zugang, Datenbank, Ablage, Whisper.

Der Sprecher wird aus dem Zugang abgeleitet, den „hören" ausgegeben hat
(`wortlaut.zugang`), geprüft lesend gegen den Korpus. Er bestimmt Modell und
Korpus, in den Korrekturen zurückfließen. Der Zugang liegt nach dem
persönlichen Link im Browser (gemeinsame Domain, gemeinsamer `localStorage`).

Abhängigkeiten statt Importe, damit Tests die Transkription ersetzen können.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from wortlaut import db, registry, storage, tempo
from wortlaut import zugang as zugangsdienst
from wortlaut.whisper import Transkriptor

from .config import Einstellungen, einstellungen

# Teuer im Aufbau, also zwischengespeichert. Transkriptoren nach Modell, nicht
# nach Sprecher - eine neue Freigabe (`wortlaut/registry.py`) lädt so wirklich
# ein anderes.
_engines: dict[str, Engine] = {}
_transkriptoren: dict[str, Transkriptor] = {}


def engine_fuer(sprecher_id: str) -> Engine:
    """Die Diktatdatenbank eines Sprechers; legt sie beim ersten Zugriff an.

    Die eigene Ablage, nicht der Korpus - anlegen ist unbedenklich.
    """
    if sprecher_id not in _engines:
        konfiguration = einstellungen()
        pfad = konfiguration.datenbank(sprecher_id)
        db.wende_migrationen_an(pfad, konfiguration.migrationsverzeichnis)
        _engines[sprecher_id] = db.verbinde(pfad)
    return _engines[sprecher_id]


def transkriptor_fuer(sprecher_id: str) -> Transkriptor:
    """Die Whisper-Umsetzung für das Modell, das dieser Mensch benutzt.

    Zwei Sprecher auf demselben Modell teilen sich den Erkenner.
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

            # Wie in Auswertung und Trainer (`wortlaut/rechenwerk.py`).
            _transkriptoren[schluessel] = LokalerTranskriptor(
                schluessel,
                geraet=konfiguration.geraet,
                rechenart=konfiguration.rechenart,
            )
    return _transkriptoren[schluessel]


def aktive_ref(konfiguration: Einstellungen, sprecher_id: str) -> str:
    """Was für diesen Menschen gilt - eine Standkennung oder ein Grundmodellname.

    1. `WORTLAUT_MODELL_REF` - der eine Stand für alle, zum Erproben.
    2. Die Freigabe dieses Sprechers aus „lernen" (`wortlaut/registry.py`),
       Stand oder Grundmodell.

    Leer: `WORTLAUT_ASR_MODELL`.
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
        # Fehlt der Stand, sagt `api/model.py` es ausdrücklich.
        return ref, {}


def tempo_fuer(konfiguration: Einstellungen, sprecher_id: str) -> float:
    """Mit welchem Faktor vorgespult wird, bevor das Modell zuhört.

    Mit einem Stand der Faktor aus seinem Manifest, auf dem er gelernt hat
    (`apps/lernen/training/bewerten.py`). Ohne Stand keiner - wie die Baseline
    in der Auswertung von „hören".
    """
    stand = modellstand(konfiguration, sprecher_id)
    if stand is None:
        return tempo.VORGABE
    return float(stand[1].get("tempo", tempo.VORGABE))


def modellpfad(konfiguration: Einstellungen, sprecher_id: str) -> Path | str:
    """Was faster-whisper geladen bekommt: Registry-Verzeichnis oder Modellname.

    Mit einem Stand dessen `ct2/`, sonst ein Modellname.
    """
    stand = modellstand(konfiguration, sprecher_id)
    if stand is None:
        return aktive_ref(konfiguration, sprecher_id) or konfiguration.asr_modell
    # Auch ohne lesbares Manifest: kein stilles Ausweichen aufs Grundmodell.
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

    Durchgereicht bis in den Postausgang (`services/outbox.py`).
    """
    return zugangsdienst.aus_kopf(authorization)


def _wer_ruft(
    authorization: Annotated[str | None, Header()] = None,
) -> zugangsdienst.Sprecherzugang:
    """Nur der Sprecherzugang - diese App spricht für einen Menschen."""
    return zugangsdienst.verlange_sprecher(einstellungen().data_dir, authorization)


def _sprecher_id(wer: Annotated[zugangsdienst.Sprecherzugang, Depends(_wer_ruft)]) -> str:
    return wer.sprecher_id


def _sprache(wer: Annotated[zugangsdienst.Sprecherzugang, Depends(_wer_ruft)]) -> str:
    """Die Sprache aus dem Profil (`wortlaut/sprachen.py`)."""
    return wer.sprache


def _sitzung(sprecher_id: Annotated[str, Depends(_sprecher_id)]) -> Iterator[Session]:
    with Session(engine_fuer(sprecher_id)) as sitzung:
        yield sitzung


def _ablage() -> storage.Ablage:
    return storage.LokaleAblage(einstellungen().data_dir)


def _transkriptor(sprecher_id: Annotated[str, Depends(_sprecher_id)]) -> Transkriptor:
    """Der Erkenner mit dem Modell, das für diesen Menschen freigegeben ist.

    Die Freigabe wird je Anfrage gelesen und gilt so sofort.
    """
    return transkriptor_fuer(sprecher_id)


# Kurzschreibweisen für die Signaturen der Endpunkte.
Wer = Annotated[zugangsdienst.Sprecherzugang, Depends(_wer_ruft)]
SprecherId = Annotated[str, Depends(_sprecher_id)]
Sprache = Annotated[str, Depends(_sprache)]
Zugangstoken = Annotated[str, Depends(_vorgelegt)]
Datenbank = Annotated[Session, Depends(_sitzung)]
Ablage = Annotated[storage.Ablage, Depends(_ablage)]
Whisper = Annotated[Transkriptor, Depends(_transkriptor)]
