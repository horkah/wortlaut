"""Die Textquelle „LLM" — Auswahl des Anbieters und der Weg nach draußen.

Ohne Netz: Der einzige Punkt, an dem diese Datei die Maschine verlässt, ist
`httpx.post`, und der wird hier ersetzt. Geprüft wird, was der Adapter
verschickt und was er aus einer Antwort macht — besonders aus einer kaputten.
Ein Modell, das nicht antwortet, ist im Betrieb der Normalfall (Container aus,
Modell nicht geladen), und die Meldung muss dann sagen, wo man nachsehen soll.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from wortlaut.text import llm

AUFTRAG = llm.Auftrag(thema="Ein Tag am Meer", altersspanne="Erwachsene", umfang=60)


class FakeAntwort:
    """So viel von `httpx.Response`, wie der Adapter anfasst."""

    def __init__(self, status_code: int = 200, daten: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._daten = daten
        self.text = text

    def json(self) -> Any:
        return self._daten


def antwort_mit(inhalt: str) -> FakeAntwort:
    return FakeAntwort(daten={"choices": [{"message": {"content": inhalt}}]})


class TestAnbieterwahl:
    def test_ohne_anbieter_nennt_die_variable(self) -> None:
        # Die Meldung landet als 400 im Frontend; sie muss sagen, was fehlt.
        with pytest.raises(ValueError, match="WORTLAUT_LLM_PROVIDER"):
            llm.erzeuge_text(AUFTRAG, anbieter="", api_schluessel="k", modell="m")

    def test_unbekannter_anbieter(self) -> None:
        with pytest.raises(ValueError, match="Unbekannter LLM-Anbieter"):
            llm.erzeuge_text(AUFTRAG, anbieter="gibtsnicht", api_schluessel="k", modell="m")

    def test_anthropic_verlangt_einen_schluessel(self) -> None:
        with pytest.raises(ValueError, match="WORTLAUT_LLM_API_KEY"):
            llm.erzeuge_text(AUFTRAG, anbieter="anthropic", api_schluessel="", modell="m")

    def test_openai_kommt_ohne_schluessel_aus(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Der ganze Sinn des lokalen Ollama: kein Schlüssel, keine Rechnung.
        monkeypatch.setattr(httpx, "post", lambda *a, **k: antwort_mit("Ein Satz."))
        text = llm.erzeuge_text(
            AUFTRAG,
            anbieter="openai",
            api_schluessel="",
            modell="gemma2:9b",
            basis_url="http://ollama:11434/v1",
        )
        assert text == "Ein Satz."

    def test_openai_ohne_adresse(self) -> None:
        with pytest.raises(ValueError, match="WORTLAUT_LLM_BASE_URL"):
            llm.erzeuge_text(AUFTRAG, anbieter="openai", api_schluessel="", modell="m")


class TestOpenAiAdapter:
    def test_schickt_auftrag_und_systemanweisung(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gesehen: dict[str, Any] = {}

        def fake_post(url: str, **kwargs: Any) -> FakeAntwort:
            gesehen["url"] = url
            gesehen.update(kwargs)
            return antwort_mit("Text.")

        monkeypatch.setattr(httpx, "post", fake_post)
        llm.erzeuge_text(
            AUFTRAG,
            anbieter="openai",
            api_schluessel="",
            modell="gemma2:9b",
            basis_url="http://ollama:11434/v1/",  # mit Schrägstrich am Ende
        )

        # Der Schrägstrich darf sich nicht verdoppeln.
        assert gesehen["url"] == "http://ollama:11434/v1/chat/completions"
        rumpf = gesehen["json"]
        assert rumpf["model"] == "gemma2:9b"
        assert rumpf["messages"][0]["role"] == "system"
        assert rumpf["messages"][0]["content"] == llm.SYSTEMANWEISUNG
        # Thema, Zielgruppe und Umfang müssen beim Modell ankommen.
        nutzer = rumpf["messages"][1]["content"]
        assert "Ein Tag am Meer" in nutzer
        assert "Erwachsene" in nutzer
        assert "60" in nutzer

    def test_ohne_schluessel_keine_leere_kopfzeile(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gesehen: dict[str, Any] = {}
        monkeypatch.setattr(
            httpx, "post", lambda url, **k: (gesehen.update(k), antwort_mit("T."))[1]
        )
        llm.erzeuge_text(
            AUFTRAG, anbieter="openai", api_schluessel="", modell="m", basis_url="http://x/v1"
        )
        # Ein „Authorization: Bearer " ohne Wert weisen manche Anbieter ab.
        assert gesehen["headers"] == {}

    def test_mit_schluessel_wird_er_mitgeschickt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gesehen: dict[str, Any] = {}
        monkeypatch.setattr(
            httpx, "post", lambda url, **k: (gesehen.update(k), antwort_mit("T."))[1]
        )
        llm.erzeuge_text(
            AUFTRAG, anbieter="openai", api_schluessel="geheim", modell="m", basis_url="http://x/v1"
        )
        assert gesehen["headers"] == {"Authorization": "Bearer geheim"}

    def test_raum_am_rand_faellt_weg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(httpx, "post", lambda *a, **k: antwort_mit("\n\n  Ein Satz.  \n"))
        text = llm.erzeuge_text(
            AUFTRAG, anbieter="openai", api_schluessel="", modell="m", basis_url="http://x/v1"
        )
        assert text == "Ein Satz."


class TestWennEsKlemmt:
    def test_nicht_erreichbar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Der häufigste Fall im Betrieb: Ollama läuft nicht.
        def wirft(*args: Any, **kwargs: Any) -> None:
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx, "post", wirft)
        with pytest.raises(ValueError, match="nicht erreichbar"):
            llm.erzeuge_text(
                AUFTRAG, anbieter="openai", api_schluessel="", modell="m", basis_url="http://x/v1"
            )

    def test_fehlerstatus_nennt_code_und_rumpf(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 404 heißt bei Ollama fast immer: Modell nicht geladen.
        monkeypatch.setattr(
            httpx,
            "post",
            lambda *a, **k: FakeAntwort(status_code=404, text='{"error":"model not found"}'),
        )
        with pytest.raises(ValueError, match="404") as fehler:
            llm.erzeuge_text(
                AUFTRAG, anbieter="openai", api_schluessel="", modell="m", basis_url="http://x/v1"
            )
        assert "model not found" in str(fehler.value)

    def test_unerwartete_antwort(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeAntwort(daten={"kein": "choices"}))
        with pytest.raises(ValueError, match="Unerwartete Antwort"):
            llm.erzeuge_text(
                AUFTRAG, anbieter="openai", api_schluessel="", modell="m", basis_url="http://x/v1"
            )

    def test_leere_auswahl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeAntwort(daten={"choices": []}))
        with pytest.raises(ValueError, match="Unerwartete Antwort"):
            llm.erzeuge_text(
                AUFTRAG, anbieter="openai", api_schluessel="", modell="m", basis_url="http://x/v1"
            )
