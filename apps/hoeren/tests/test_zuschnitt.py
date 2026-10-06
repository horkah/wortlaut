"""Zuschnitt: die Stille an den Rändern wegschneiden - und was daran hängt.

Geprüft wird in drei Lagen, weil es drei Zusagen sind:

* **Der Schlüssel.** Ohne gesetzten `WORTLAUT_EDITOR_KEY` ist diese Ansicht
  vollständig zu, auch für einen gültigen Sprecherzugang.
* **Der Schnitt.** Was herauskommt, ist Byte für Byte der Ausschnitt des
  Originals - kein Umkodieren, kein Generationsverlust - und liegt an dessen
  Stelle.
* **Die Folgen.** Nach dem Schnitt arbeitet jede App mit der gekürzten Datei:
  die Auswertung, das Anhören, der Datensatz und das Manifest eines
  Trainingslaufs. Abwandlungen und Messwerte am alten Ton sind weg.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from wortlaut import corpus

from apps.hoeren.backend import deps
from apps.hoeren.backend.config import einstellungen
from apps.hoeren.backend.db.models import Aufnahme, Erkennung, jetzt
from apps.hoeren.backend.main import app
from apps.hoeren.backend.services import augmentierung

EDITOR_KEY = "test-zuschnitt"


@pytest.fixture
def _mit_schluessel(_umgebung: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ein Server, auf dem zugeschnitten werden darf."""
    monkeypatch.setenv("WORTLAUT_EDITOR_KEY", EDITOR_KEY)
    einstellungen.cache_clear()


@pytest.fixture
def schneider(_mit_schluessel: None, klient: TestClient) -> TestClient:
    """Der Zugang eines Sprechers **plus** der Bearbeitungsschlüssel.

    Derselbe Klient wie `klient` und kein zweiter: Einen Zugang auszugeben
    zieht den vorigen zurück (`api/zugang.py`). Ein eigener Klient hier hätte
    den von `quelle` entwertet - und der Test wäre an einer 401 gescheitert,
    die mit dem Zuschnitt nichts zu tun hat.
    """
    klient.headers["X-Editor-Key"] = EDITOR_KEY
    return klient


def nimm_auf(klient: TestClient, sprecher: str, audio_datei: dict) -> str:
    """Eine Aufnahme anlegen und ihre Kennung zurückgeben."""
    antwort_next = klient.get(f"/api/prompts/next?sprecher={sprecher}")
    assert antwort_next.status_code == 200, antwort_next.text
    naechste = antwort_next.json()
    assert naechste.get("aktuell"), naechste
    antwort = klient.post(
        f"/api/recordings?sprecher={sprecher}",
        files=audio_datei,
        data={"prompt_id": naechste["aktuell"]["id"], "modus": "gelesen"},
    )
    assert antwort.status_code == 201, antwort.text
    return antwort.json()["id"]


def rahmen(pfad: Path) -> bytes:
    with wave.open(str(pfad), "rb") as datei:
        return datei.readframes(datei.getnframes())


class TestSchluessel:
    def test_ohne_gesetzten_schluessel_ist_alles_zu(
        self, klient: TestClient, sprecher: str
    ) -> None:
        """Leer heißt abgeschaltet, nicht offen - wie bei Verwaltung und Aufsicht."""
        antwort = klient.get(f"/api/zuschnitt/aufnahmen?sprecher={sprecher}")
        assert antwort.status_code == 401
        assert "WORTLAUT_EDITOR_KEY" in antwort.json()["detail"]

    def test_sprecherzugang_allein_genuegt_nicht(
        self, _mit_schluessel: None, klient: TestClient, sprecher: str
    ) -> None:
        """Der Zugang sagt, wessen Aufnahmen - nicht, wer in den Bestand greift."""
        antwort = klient.get(f"/api/zuschnitt/aufnahmen?sprecher={sprecher}")
        assert antwort.status_code == 401
        assert "Bearbeitungsschlüssel" in antwort.json()["detail"]

    def test_falscher_schluessel_wird_abgewiesen(
        self, _mit_schluessel: None, klient: TestClient, sprecher: str
    ) -> None:
        klient.headers["X-Editor-Key"] = "daneben"
        antwort = klient.get(f"/api/zuschnitt/aufnahmen?sprecher={sprecher}")
        assert antwort.status_code == 401

    def test_mit_schluessel_geht_es(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        nimm_auf(schneider, sprecher, audio_datei)
        antwort = schneider.get(f"/api/zuschnitt/aufnahmen?sprecher={sprecher}")
        assert antwort.status_code == 200
        assert antwort.json()["gesamt"] == 1


class TestAnsicht:
    def test_liefert_kurve_und_vorschlag(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        """Kurve und Grenzen kommen aus derselben Rechnung - sonst liegt die
        Linie neben dem Ausschlag."""
        nimm_auf(schneider, sprecher, audio_datei)
        eine = schneider.get(f"/api/zuschnitt/aufnahmen?sprecher={sprecher}").json()["aufnahmen"][
            0
        ]

        # Die Testaufnahme ist vier Sekunden lang mit 0,3 s Stille vorn.
        assert eine["dauer_s"] == pytest.approx(4.0, abs=0.05)
        assert len(eine["verlauf"]) == pytest.approx(200, abs=2)
        assert eine["fenster_s"] == pytest.approx(0.02)
        # Der Vorschlag setzt hinter der Stille an, aber mit Luft davor.
        assert 0.1 < eine["vorschlag_start_s"] < 0.3
        assert eine["vorschlag_ende_s"] == pytest.approx(4.0, abs=0.05)
        assert eine["text"]

    def test_zeigt_nach_dem_schnitt_die_gekuerzte_datei(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        schneider.post(
            f"/api/zuschnitt/schreiben?sprecher={sprecher}",
            json={"grenzen": [{"id": kennung, "start_s": 1.0, "ende_s": 2.0}]},
        )

        eine = schneider.get(f"/api/zuschnitt/aufnahmen?sprecher={sprecher}").json()["aufnahmen"][
            0
        ]
        assert eine["dauer_s"] == pytest.approx(1.0, abs=0.05)

    def test_original_endpunkt_liefert_die_datei(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        schneider.post(
            f"/api/zuschnitt/schreiben?sprecher={sprecher}",
            json={"grenzen": [{"id": kennung, "start_s": 1.0, "ende_s": 2.0}]},
        )

        antwort = schneider.get(
            f"/api/zuschnitt/aufnahmen/{kennung}/original?sprecher={sprecher}"
        )
        assert antwort.status_code == 200
        datei = tmp_path / "data" / corpus.audio_relpfad(sprecher, kennung)
        assert antwort.content == datei.read_bytes()


class TestSchnitt:
    def test_schneidet_verlustfrei_und_ueberschreibt_das_original(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        """Byte für Byte derselbe Ausschnitt - kein Umkodieren, kein Verlust."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        datei = tmp_path / "data" / corpus.audio_relpfad(sprecher, kennung)
        vorher = rahmen(datei)

        antwort = schneider.post(
            f"/api/zuschnitt/schreiben?sprecher={sprecher}",
            json={"grenzen": [{"id": kennung, "start_s": 1.0, "ende_s": 3.0}]},
        )
        assert antwort.status_code == 200
        assert antwort.json() == {"geschrieben": 1, "fehler": {}}

        # An derselben Stelle liegt genau der Byte-Bereich aus dem Original.
        rate, breite = 16_000, 2
        assert rahmen(datei) == vorher[1 * rate * breite : 3 * rate * breite]

    def test_rundet_nach_aussen(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        """Lieber ein Rahmen zu viel als ein angeschnittener Abtastwert."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        datei = tmp_path / "data" / corpus.audio_relpfad(sprecher, kennung)
        vorher = rahmen(datei)
        # Grenzen, die zwischen zwei Abtastwerte fallen (16 kHz → 62,5 µs).
        schneider.post(
            f"/api/zuschnitt/schreiben?sprecher={sprecher}",
            json={"grenzen": [{"id": kennung, "start_s": 1.000_03, "ende_s": 2.000_03}]},
        )

        # Anfang abwärts, Ende aufwärts - der Ausschnitt ist eher zu lang.
        breite = 2
        assert rahmen(datei) == vorher[16_000 * breite : 32_001 * breite]

    def test_zweiter_schnitt_kuerzt_die_gekuerzte_datei(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        """Das Original ist nach dem ersten Schnitt weg; der zweite geht von dessen Ergebnis aus."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        datei = tmp_path / "data" / corpus.audio_relpfad(sprecher, kennung)
        vorher = rahmen(datei)
        for grenzen in ([1.0, 3.0], [0.5, 1.5]):
            schneider.post(
                f"/api/zuschnitt/schreiben?sprecher={sprecher}",
                json={"grenzen": [{"id": kennung, "start_s": grenzen[0], "ende_s": grenzen[1]}]},
            )

        rate, breite = 16_000, 2
        assert rahmen(datei) == vorher[int(1.5 * rate) * breite : int(2.5 * rate) * breite]

    def test_die_zeile_beschreibt_die_neue_datei(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        schneider.post(
            f"/api/zuschnitt/schreiben?sprecher={sprecher}",
            json={"grenzen": [{"id": kennung, "start_s": 1.0, "ende_s": 3.0}]},
        )
        with Session(deps.engine_fuer(sprecher)) as sitzung:
            assert sitzung.get(Aufnahme, kennung).dauer_s == pytest.approx(2.0, abs=0.01)

    def test_leerer_ausschnitt_wird_abgewiesen(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        antwort = schneider.post(
            f"/api/zuschnitt/schreiben?sprecher={sprecher}",
            json={"grenzen": [{"id": kennung, "start_s": 2.0, "ende_s": 1.0}]},
        )
        assert antwort.status_code == 200
        assert antwort.json()["geschrieben"] == 0
        assert kennung in antwort.json()["fehler"]

    def test_eine_fehlerhafte_nimmt_die_anderen_nicht_mit(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        erste = nimm_auf(schneider, sprecher, audio_datei)
        zweite = nimm_auf(schneider, sprecher, audio_datei)
        antwort = schneider.post(
            f"/api/zuschnitt/schreiben?sprecher={sprecher}",
            json={
                "grenzen": [
                    {"id": erste, "start_s": 1.0, "ende_s": 2.0},
                    {"id": "rec_gibtsnicht", "start_s": 1.0, "ende_s": 2.0},
                    {"id": zweite, "start_s": 1.0, "ende_s": 2.0},
                ]
            },
        )
        assert antwort.json()["geschrieben"] == 2
        assert list(antwort.json()["fehler"]) == ["rec_gibtsnicht"]


class TestFolgen:
    """Nach dem Schnitt arbeitet jede App mit der gekürzten Datei."""

    def _mit_zuschnitt(
        self, schneider: TestClient, sprecher: str, audio_datei: dict
    ) -> str:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        antwort = schneider.post(
            f"/api/zuschnitt/schreiben?sprecher={sprecher}",
            json={"grenzen": [{"id": kennung, "start_s": 1.0, "ende_s": 2.0}]},
        )
        assert antwort.json()["geschrieben"] == 1
        return kennung

    def test_anhoeren_liefert_die_gekuerzte_datei(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        kennung = self._mit_zuschnitt(schneider, sprecher, audio_datei)
        antwort = schneider.get(f"/api/recordings/{kennung}/audio?sprecher={sprecher}")
        assert antwort.status_code == 200
        datei = tmp_path / "data" / corpus.audio_relpfad(sprecher, kennung)
        assert antwort.content == datei.read_bytes()

    def test_abwandlungen_entstehen_aus_dem_zuschnitt(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        """Sonst hörte ein Training dieselbe Äußerung in zwei Längen."""
        kennung = self._mit_zuschnitt(schneider, sprecher, audio_datei)
        for abwandlung in augmentierung.ABWANDLUNGEN:
            datei = (
                tmp_path
                / "data"
                / corpus.variante_relpfad(sprecher, kennung, abwandlung.name)
            )
            assert datei.is_file()
            with wave.open(str(datei), "rb") as offen:
                dauer = offen.getnframes() / offen.getframerate()
            assert dauer == pytest.approx(1.0, abs=0.01)

    def test_messwerte_werden_verworfen(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        """Eine Zahl vom alten Ton beschriebe eine Datei, die es nicht mehr
        gibt - und die Auswertung hielte sie für erledigt."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        with Session(deps.engine_fuer(sprecher)) as sitzung:
            sitzung.add(
                Erkennung(
                    id="erk_test",
                    recording_id=kennung,
                    modell="small",
                    variante=augmentierung.ORIGINAL,
                    text="irgendetwas",
                    wer=0.2,
                    cer=0.1,
                    mer=0.2,
                    wil=0.2,
                    genauigkeit=80.0,
                    rechenzeit_s=1.0,
                    rechenwerk="cpu/int8",
                    erstellt=jetzt(),
                )
            )
            sitzung.commit()

        schneider.post(
            f"/api/zuschnitt/schreiben?sprecher={sprecher}",
            json={"grenzen": [{"id": kennung, "start_s": 1.0, "ende_s": 2.0}]},
        )

        with Session(deps.engine_fuer(sprecher)) as sitzung:
            assert sitzung.get(Erkennung, "erk_test") is None

    def test_datensatz_traegt_den_zuschnitt(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        import io
        import zipfile

        kennung = self._mit_zuschnitt(schneider, sprecher, audio_datei)
        antwort = schneider.get(f"/api/konto/datensatz?sprecher={sprecher}")
        assert antwort.status_code == 200

        datei = tmp_path / "data" / corpus.audio_relpfad(sprecher, kennung)
        with zipfile.ZipFile(io.BytesIO(antwort.content)) as archiv:
            enthalten = archiv.read(f"{sprecher}/audio/{kennung}.wav")
        assert enthalten == datei.read_bytes()

    def test_trainingsmanifest_traegt_den_zuschnitt(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        from apps.lernen.backend.services import aufteilung, auftraege

        kennung = self._mit_zuschnitt(schneider, sprecher, audio_datei)
        with Session(deps.engine_fuer(sprecher)) as korpus:
            proben = aufteilung.proben(korpus)
            zeile = auftraege._manifestzeile(
                proben[0], augmentierung.ORIGINAL, "vorlage", sprecher
            )

        assert zeile["audio"] == f"audio/{kennung}.wav"
        assert zeile["dauer_s"] == pytest.approx(1.0, abs=0.01)


def _teile(schneider: TestClient, sprecher: str, kennung: str, **abweichend) -> dict:
    """Eine Aufnahme an der ersten Wortgrenze teilen - im Ton bei 2,0 s."""
    with Session(deps.engine_fuer(sprecher)) as sitzung:
        from apps.hoeren.backend.db.models import Vorlage

        text = sitzung.get(Vorlage, sitzung.get(Aufnahme, kennung).prompt_id).text
    vorn, hinten = text.split(" ", 1)
    auftrag = {
        "id": kennung,
        "start_s": 0.5,
        "teilung_s": 2.0,
        "ende_s": 3.5,
        "text_vorn": vorn,
        "text_hinten": hinten,
        **abweichend,
    }
    return schneider.post(f"/api/zuschnitt/teilen?sprecher={sprecher}", json=auftrag)


class TestTeilen:
    """Eine Aufnahme in zwei neue zerlegen - Ton und Text."""

    def test_eine_aufnahme_einzeln(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        antwort = schneider.get(f"/api/zuschnitt/aufnahmen/{kennung}?sprecher={sprecher}")
        assert antwort.status_code == 200
        assert antwort.json()["id"] == kennung
        assert schneider.get(f"/api/zuschnitt/aufnahmen/rec_gibtsnicht").status_code == 404

    def test_die_teile_liegen_lueckenlos_aneinander(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        """Byte für Byte der Bereich des Originals - kein Rahmen doppelt, keiner fehlt."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        original = tmp_path / "data" / corpus.audio_relpfad(sprecher, kennung)

        antwort = _teile(schneider, sprecher, kennung)
        assert antwort.status_code == 200, antwort.text
        vorn, hinten = antwort.json()["ids"]

        rate, breite = 16_000, 2
        erwartet = rahmen(original)[int(0.5 * rate) * breite : int(3.5 * rate) * breite]
        dateien = [tmp_path / "data" / corpus.audio_relpfad(sprecher, k) for k in (vorn, hinten)]
        assert len(rahmen(dateien[0])) == int(1.5 * rate) * breite
        assert rahmen(dateien[0]) + rahmen(dateien[1]) == erwartet
        # Das Original bleibt, wie es war.
        assert original.is_file()

    def test_texte_datum_und_reihenfolge(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        """Die Teile stehen direkt unter dem Original und tragen sein Datum."""
        erste = nimm_auf(schneider, sprecher, audio_datei)
        zweite = nimm_auf(schneider, sprecher, audio_datei)
        vorn, hinten = _teile(schneider, sprecher, erste).json()["ids"]

        liste = schneider.get(f"/api/zuschnitt/aufnahmen?sprecher={sprecher}").json()["aufnahmen"]
        assert [eine["id"] for eine in liste] == [erste, vorn, hinten, zweite]
        assert liste[1]["erstellt"] == liste[0]["erstellt"] == liste[2]["erstellt"]
        assert f'{liste[1]["text"]} {liste[2]["text"]}' == liste[0]["text"]

        with Session(deps.engine_fuer(sprecher)) as sitzung:
            assert sitzung.get(Aufnahme, vorn).sortierschluessel == f"{erste}.1"
            assert sitzung.get(Aufnahme, hinten).sortierschluessel == f"{erste}.2"

    def test_der_text_darf_berichtigt_werden(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        """Gesprochen wird nicht immer, was dasteht - die Teile tragen, was gesagt wurde."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        antwort = _teile(schneider, sprecher, kennung, text_hinten="etwas ganz  anderes")
        assert antwort.status_code == 200, antwort.text
        liste = schneider.get(f"/api/zuschnitt/aufnahmen?sprecher={sprecher}").json()["aufnahmen"]
        assert liste[2]["text"] == "etwas ganz anderes"

    def test_ein_teil_ohne_text_wird_abgewiesen(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        assert _teile(schneider, sprecher, kennung, text_vorn=" ").status_code == 400

    def test_teilung_auf_dem_anfang_speichert_nur_teil_zwei(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        """Eine Kopie des Ausschnitts mit eigenem Text - der leere Teil braucht keinen."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        antwort = _teile(
            schneider, sprecher, kennung, teilung_s=0.5, text_vorn="", text_hinten="berichtigt"
        )
        assert antwort.status_code == 200, antwort.text
        (kopie,) = antwort.json()["ids"]
        # Ein zweites Mal hängt hinten an, statt denselben Schlüssel zu tragen.
        (zweite,) = _teile(
            schneider, sprecher, kennung, teilung_s=3.5, text_hinten=""
        ).json()["ids"]
        with Session(deps.engine_fuer(sprecher)) as sitzung:
            assert sitzung.get(Aufnahme, kopie).sortierschluessel == f"{kennung}.1"
            assert sitzung.get(Aufnahme, zweite).sortierschluessel == f"{kennung}.2"
            assert sitzung.get(Aufnahme, kopie).dauer_s == pytest.approx(3.0, abs=0.01)

    def test_teilung_muss_zwischen_den_grenzen_liegen(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        assert _teile(schneider, sprecher, kennung, teilung_s=3.8).status_code == 400
        # Nichts angelegt.
        assert len(
            schneider.get(f"/api/zuschnitt/aufnahmen?sprecher={sprecher}").json()["aufnahmen"]
        ) == 1

    def test_die_vorlage_bleibt_erledigt(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        """Die neuen Vorlagen haben ihre Aufnahme - in der Warteschlange stehen sie nicht."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        vorher = schneider.get("/api/prompts/next").json()
        _teile(schneider, sprecher, kennung)
        nachher = schneider.get("/api/prompts/next").json()
        assert nachher["aktuell"]["id"] == vorher["aktuell"]["id"]


class TestLoeschen:
    def test_loescht_zeile_dateien_und_messwerte(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        schneider.post(
            f"/api/zuschnitt/schreiben?sprecher={sprecher}",
            json={"grenzen": [{"id": kennung, "start_s": 1.0, "ende_s": 2.0}]},
        )
        with Session(deps.engine_fuer(sprecher)) as sitzung:
            vorlage_id = sitzung.get(Aufnahme, kennung).prompt_id
        dateien = [
            tmp_path / "data" / corpus.audio_relpfad(sprecher, kennung),
        ] + [
            tmp_path / "data" / corpus.variante_relpfad(sprecher, kennung, abwandlung.name)
            for abwandlung in augmentierung.ABWANDLUNGEN
        ]
        assert all(datei.is_file() for datei in dateien)

        antwort = schneider.post(
            f"/api/zuschnitt/loeschen?sprecher={sprecher}",
            json={"grenzen": [{"id": kennung, "start_s": 0, "ende_s": 0}]},
        )
        assert antwort.json() == {"geschrieben": 1, "fehler": {}}
        assert not any(datei.exists() for datei in dateien)

        from apps.hoeren.backend.db.models import Vorlage

        with Session(deps.engine_fuer(sprecher)) as sitzung:
            assert sitzung.get(Aufnahme, kennung) is None
            # Die Vorlage geht mit - sonst stünde der Satz wieder in der Warteschlange.
            assert sitzung.get(Vorlage, vorlage_id) is None

    def test_original_loeschen_laesst_die_teile(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        vorn, hinten = _teile(schneider, sprecher, kennung).json()["ids"]
        schneider.post(
            f"/api/zuschnitt/loeschen?sprecher={sprecher}",
            json={"grenzen": [{"id": kennung, "start_s": 0, "ende_s": 0}]},
        )
        liste = schneider.get(f"/api/zuschnitt/aufnahmen?sprecher={sprecher}").json()["aufnahmen"]
        assert [eine["id"] for eine in liste] == [vorn, hinten]

    def test_fremde_aufnahme_bleibt(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        antwort = schneider.post(
            f"/api/zuschnitt/loeschen?sprecher={sprecher}",
            json={"grenzen": [{"id": "rec_gibtsnicht", "start_s": 0, "ende_s": 0}]},
        )
        assert antwort.json()["fehler"] == {"rec_gibtsnicht": "Unbekannte Aufnahme."}
