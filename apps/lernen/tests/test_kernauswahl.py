"""Die Kernauswahl: gelernt nur auf den Aufnahmen, die das freigegebene Modell am besten verstand.

Der Trainer läuft hier nicht. Geprüft wird, was davor liegt: dass der Server
den Kern nach den richtigen Werten wählt, ihn neben den Auftrag schreibt und
abweist, wo er nichts Ehrliches wählen könnte. Die Werte eines trainierten
Standes werden nachgestellt wie in `test_vergleich.py` - als `bewertung.jsonl`
seines Laufs.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from wortlaut import laeufe, registry
from wortlaut.whisper import Transkript

from apps.hoeren.backend.db.models import Aufnahme
from apps.hoeren.backend.services import auswertung
from apps.lernen.backend.deps import korpus_engine
from apps.lernen.backend.services import kernauswahl
from apps.lernen.backend.services.aufteilung import Probe

KERN = {"methode": "lora", "daten": "original", "auswahl": "kern"}


class PlatzhalterErkenner:
    def transkribiere(self, wav: Path, sprache: str) -> Transkript:
        return Transkript(text="völlig daneben gehört", abschnitte=[])


@pytest.fixture(autouse=True)
def _auswertung(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("WORTLAUT_AUSWERTUNG_MODELLE", "small")
    monkeypatch.setattr(
        auswertung,
        "transkriptor_fuer",
        lambda modell, geraet, rechenart, datenverzeichnis=None: PlatzhalterErkenner(),
    )
    auswertung.vergiss_lauf()
    yield
    auswertung.vergiss_lauf()


@pytest.fixture
def aufnahmen(quelle: str, sprich) -> list[str]:
    return sprich(9)


def _stand_mit_werten(
    klient: TestClient, datenverzeichnis: Path, sprecher: str, wer: dict[str, float]
) -> str:
    """Einen fertigen Lauf nachstellen, dessen Faltungen diese WER gemessen haben."""
    lauf = klient.post("/lernen/api/laeufe", json={"methode": "lora", "daten": "original"})
    assert lauf.status_code == 201, lauf.text
    job_id = lauf.json()["job_id"]
    verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, job_id)
    for zeile in laeufe.manifestzeilen(verzeichnis):
        kennung = zeile["recording_id"]
        if kennung not in wer:
            continue
        laeufe.haenge_an(
            verzeichnis / laeufe.BEWERTUNG,
            {
                "recording_id": kennung,
                "variante": zeile["variante"],
                "faltung": zeile["faltung"],
                "wer": wer[kennung],
                "cer": 0.0,
                "mer": 0.0,
                "wil": 0.0,
                "genauigkeit": 100.0 * (1 - wer[kennung]),
                "rechenzeit_s": 0.1,
            },
        )
    version = "20260927T1200-lora-original"
    registry.schreibe_stand(
        datenverzeichnis,
        {
            "id": f"{sprecher}/{version}",
            "sprecher_id": sprecher,
            "basismodell": "openai/whisper-small",
            "methode": "lora",
            "daten": "original",
            "job_id": job_id,
            "status": "fertig",
        },
    )
    laeufe.schreibe_json(
        verzeichnis / laeufe.ZUSTAND,
        {"status": laeufe.FERTIG, "beendet": laeufe.jetzt(), "version": version},
    )
    ref = f"{sprecher}/{version}"
    registry.gib_frei(datenverzeichnis, sprecher, ref)
    return ref


def _kernauswahl(datenverzeichnis: Path, job_id: str) -> dict:
    datei = laeufe.lauf_verzeichnis(datenverzeichnis, job_id) / laeufe.KERNAUSWAHL
    return json.loads(datei.read_text(encoding="utf-8"))


class TestWahl:
    def test_der_kern_sind_die_besten_nach_dem_freigegebenen_stand(
        self, klient: TestClient, aufnahmen: list[str], datenverzeichnis: Path, sprecher: str
    ) -> None:
        # Die erste Aufnahme am besten verstanden, die letzte am schlechtesten.
        wer = {kennung: stelle / 10 for stelle, kennung in enumerate(aufnahmen)}
        ref = _stand_mit_werten(klient, datenverzeichnis, sprecher, wer)

        antwort = klient.post("/lernen/api/laeufe", json=KERN)
        assert antwort.status_code == 201, antwort.text
        lauf = antwort.json()

        auswahl = _kernauswahl(datenverzeichnis, lauf["job_id"])
        anzahl = math.ceil(len(aufnahmen) * laeufe.KERN_ANTEIL)
        assert auswahl["kern"] == aufnahmen[:anzahl]
        assert auswahl["modell"] == ref
        assert auswahl["schwelle"] == pytest.approx(wer[aufnahmen[anzahl - 1]])
        # Jede Aufnahme steht mit ihrem Wert da, auch die außerhalb des Kerns.
        assert set(auswahl["wer"]) == set(aufnahmen)

        assert lauf["auswahl"] == "kern"
        assert lauf["code"].startswith("SL-K")
        auftrag = laeufe.lies_json(
            laeufe.lauf_verzeichnis(datenverzeichnis, lauf["job_id"]) / laeufe.AUFTRAG
        )
        assert auftrag["auswahl"] == "kern"
        assert laeufe.kern_aus(
            laeufe.lauf_verzeichnis(datenverzeichnis, lauf["job_id"]), auftrag
        ) == set(aufnahmen[:anzahl])

    def test_gemessen_wird_weiter_an_allen(
        self, klient: TestClient, aufnahmen: list[str], datenverzeichnis: Path, sprecher: str
    ) -> None:
        # Das Manifest ist derselbe Schnappschuss wie ohne Kern: Welche Zeilen
        # gelernt werden, entscheidet erst der Trainer (`daten.zeilen_fuer_faltung`).
        _stand_mit_werten(
            klient, datenverzeichnis, sprecher, {kennung: 0.1 for kennung in aufnahmen}
        )
        lauf = klient.post("/lernen/api/laeufe", json=KERN).json()
        zeilen = laeufe.manifestzeilen(laeufe.lauf_verzeichnis(datenverzeichnis, lauf["job_id"]))
        assert {zeile["recording_id"] for zeile in zeilen} == set(aufnahmen)

    def test_der_steckbrief_nennt_den_kern(
        self, klient: TestClient, aufnahmen: list[str], datenverzeichnis: Path, sprecher: str
    ) -> None:
        _stand_mit_werten(
            klient, datenverzeichnis, sprecher, {kennung: 0.25 for kennung in aufnahmen}
        )
        lauf = klient.post("/lernen/api/laeufe", json=KERN).json()
        steckbrief = klient.get(f"/lernen/api/laeufe/{lauf['job_id']}").json()["steckbrief"]
        zeile = next(zeile for zeile in steckbrief if zeile["begriff"] == "Auswahl")
        anzahl = math.ceil(len(aufnahmen) * laeufe.KERN_ANTEIL)
        assert zeile["wert"] == "Kernauswahl"
        assert f"{anzahl} von {len(aufnahmen)} Aufnahmen" in zeile["hinweis"]
        assert "WER bis 0,25" in zeile["hinweis"]

    def test_ohne_kern_bleibt_alles_wie_es_war(
        self, klient: TestClient, aufnahmen: list[str], datenverzeichnis: Path
    ) -> None:
        lauf = klient.post("/lernen/api/laeufe", json={"methode": "lora", "daten": "original"})
        assert lauf.status_code == 201
        assert lauf.json()["auswahl"] == "alle"
        assert lauf.json()["code"] == f"SL/{len(aufnahmen)}"
        verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, lauf.json()["job_id"])
        assert not (verzeichnis / laeufe.KERNAUSWAHL).exists()


class TestAbgewiesen:
    def test_ohne_freigabe_kein_kern(self, klient: TestClient, aufnahmen: list[str]) -> None:
        antwort = klient.post("/lernen/api/laeufe", json=KERN)
        assert antwort.status_code == 409
        assert "freigegeben" in antwort.json()["detail"]

    def test_eine_ungehoerte_aufnahme_haelt_den_kern_auf(
        self, klient: TestClient, aufnahmen: list[str], datenverzeichnis: Path, sprecher: str
    ) -> None:
        # Die letzte Aufnahme kennt der Stand nicht: Ob sie in den Kern gehört,
        # lässt sich nicht sagen.
        _stand_mit_werten(
            klient, datenverzeichnis, sprecher, {kennung: 0.1 for kennung in aufnahmen[:-1]}
        )
        antwort = klient.post("/lernen/api/laeufe", json=KERN)
        assert antwort.status_code == 409
        assert f"1 von {len(aufnahmen)} Aufnahmen" in antwort.json()["detail"]
        assert "Auswertung" in antwort.json()["detail"]

    def test_eine_unbekannte_auswahl(self, klient: TestClient, aufnahmen: list[str]) -> None:
        antwort = klient.post("/lernen/api/laeufe", json={**KERN, "auswahl": "irgendwas"})
        assert antwort.status_code == 400


class TestGrundmodell:
    def test_ein_freigegebenes_grundmodell_waehlt_nach_hoeren(
        self,
        klient: TestClient,
        hoeren: TestClient,
        aufnahmen: list[str],
        datenverzeichnis: Path,
        sprecher: str,
    ) -> None:
        registry.gib_frei(datenverzeichnis, sprecher, "small")
        assert klient.post("/lernen/api/laeufe", json=KERN).status_code == 409

        assert hoeren.post("/api/auswertung/start").status_code == 200
        ende = time.monotonic() + 20.0
        while hoeren.get("/api/auswertung").json()["stand"]["laeuft"]:
            assert time.monotonic() < ende, "Die Auswertung wurde nicht fertig."

        antwort = klient.post("/lernen/api/laeufe", json=KERN)
        assert antwort.status_code == 201, antwort.text
        auswahl = _kernauswahl(datenverzeichnis, antwort.json()["job_id"])
        assert auswahl["modell"] == "small"
        # Alle gleich schlecht verstanden: Die Kennung entscheidet, damit
        # derselbe Korpus immer denselben Kern ergibt.
        assert auswahl["kern"] == sorted(aufnahmen)[: len(auswahl["kern"])]
        assert len(auswahl["kern"]) == math.ceil(len(aufnahmen) * laeufe.KERN_ANTEIL)


class TestVerwandte:
    def test_ein_teil_erbt_den_wert_seines_originals(
        self, klient: TestClient, aufnahmen: list[str], datenverzeichnis: Path, sprecher: str
    ) -> None:
        """Ein Teil ist derselbe Ton - der Stand misst ihn nicht, sein Original schon."""
        wer = {kennung: stelle / 10 for stelle, kennung in enumerate(aufnahmen)}
        _stand_mit_werten(klient, datenverzeichnis, sprecher, wer)

        original = aufnahmen[-1]
        teil = Aufnahme(id="rec_TEIL", sortierschluessel=f"{original}.1")
        with Session(korpus_engine(sprecher)) as korpus:
            proben = [
                Probe(aufnahme=korpus.get(Aufnahme, kennung), vorlage=None, faltung=0, nummer=0)
                for kennung in aufnahmen
            ] + [Probe(aufnahme=teil, vorlage=None, faltung=0, nummer=0)]
            auswahl = kernauswahl.waehle(datenverzeichnis, korpus, sprecher, proben)

        assert auswahl.wer["rec_TEIL"] == pytest.approx(wer[original])
        assert auswahl.geerbt == ["rec_TEIL"]
        # Das Original war das schlechteste - sein Teil gehört mit ihm nicht dazu.
        assert "rec_TEIL" not in auswahl.kern
