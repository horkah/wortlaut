"""Cache-Regeln des ausgelieferten Frontends.

Der Fehler, gegen den diese Tests stehen, ist unsichtbar und teuer: Ohne
`Cache-Control` schätzt der Browser die Frische der `index.html` selbst und
fragt tagelang nicht nach. Nach einem Ausrollen sieht er dann weiter die alte
App — nicht kaputt, nur alt, und niemand merkt es am Server.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from wortlaut.web import IMMER_NACHFRAGEN, UNVERAENDERLICH, FrontendDateien


@pytest.fixture
def klient(tmp_path: Path) -> Iterator[TestClient]:
    """Ein Frontend, wie Vite es baut: index.html plus gehashte Bündel."""
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-Dw8ROtVv.js").write_text("console.log(1)", encoding="utf-8")

    app = FastAPI()
    app.mount("/", FrontendDateien(directory=tmp_path, html=True), name="frontend")
    with TestClient(app) as klient:
        yield klient


class TestCacheRegeln:
    def test_index_wird_vor_jeder_benutzung_nachgefragt(self, klient: TestClient) -> None:
        # Die einzige Datei, deren Name sich nie ändert, und die einzige, die
        # auf die Bündelnamen zeigt.
        antwort = klient.get("/")
        assert antwort.status_code == 200
        assert antwort.headers["cache-control"] == IMMER_NACHFRAGEN

    def test_index_auch_unter_ihrem_namen(self, klient: TestClient) -> None:
        antwort = klient.get("/index.html")
        assert antwort.status_code == 200
        assert antwort.headers["cache-control"] == IMMER_NACHFRAGEN

    def test_gehashtes_buendel_darf_der_browser_behalten(self, klient: TestClient) -> None:
        # Ändert sich der Inhalt, ändert Vite den Namen — Nachfragen wäre
        # verschenkte Zeit.
        antwort = klient.get("/assets/index-Dw8ROtVv.js")
        assert antwort.status_code == 200
        assert antwort.headers["cache-control"] == UNVERAENDERLICH
