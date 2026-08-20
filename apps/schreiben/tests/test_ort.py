"""Wo diese App liegt.

Alles hängt unter `/schreiben` — die API eingeschlossen —, damit vor den
Containern eine Regel genügt, die den Pfad unverändert durchreicht. Als das
einmal nicht galt, beantwortete „hören" den Klick auf den Reiter mit der
eigenen Seite und die App war nicht erreichbar; deshalb steht es hier geprüft.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from apps.schreiben.backend.main import BASIS


class TestPfad:
    def test_api_haengt_unter_dem_pfad(self, klient: TestClient) -> None:
        assert klient.post(f"{BASIS}/api/sessions").status_code == 201

    def test_ausserhalb_des_pfades_gibt_es_nichts(self, klient: TestClient) -> None:
        # Ohne Präfix müsste ein Proxy es abschneiden — genau die Regel, die
        # beim Wechsel auf einen vorhandenen Reverse Proxy verlorenging.
        assert klient.post("/api/sessions").status_code == 404

    def test_wurzel_führt_in_die_app(self, klient: TestClient) -> None:
        antwort = klient.get("/", follow_redirects=False)
        assert antwort.status_code in (307, 308)
        assert antwort.headers["location"] == f"{BASIS}/"

    def test_gesundheit_bleibt_auf_der_wurzel(self, klient: TestClient) -> None:
        # Der Prüfpunkt für Überwachung und Compose spricht den Container
        # unmittelbar an und weiß nichts von der Pfadverteilung.
        assert klient.get("/gesundheit").json() == {"status": "ok"}
