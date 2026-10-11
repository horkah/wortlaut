"""Editieren: kürzen, teilen, den Text berichtigen - und was daran hängt.

Geprüft wird in vier Lagen, weil es vier Zusagen sind:

* **Der Schlüssel.** Ohne gesetzten `WORTLAUT_EDITOR_KEY` ist diese Ansicht
  vollständig zu, auch für einen gültigen Sprecherzugang.
* **Der Schnitt.** Was herauskommt, ist Byte für Byte der Ausschnitt des
  Originals - kein Umkodieren, kein Generationsverlust - und liegt an dessen
  Stelle.
* **Der Text.** Er steht an der Aufnahme, die Vorlage bleibt; eine Korrektur
  gilt nach dem Speichern als geprüft.
* **Die Folgen.** Danach arbeitet jede App mit der gekürzten Datei und dem
  neuen Text: die Auswertung, das Anhören, der Datensatz und das Manifest
  eines Trainingslaufs. Messwerte am alten Ton oder Text sind weg.

Dazu das Teilen: Die Teile ersetzen das Original, an derselben Vorlage.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from wortlaut import corpus

from apps.hoeren.backend import deps
from apps.hoeren.backend.config import einstellungen
from apps.hoeren.backend.db.models import GUELTIG, Aufnahme, Erkennung, Textquelle, Vorlage, jetzt
from apps.hoeren.backend.services import zuschnitt

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


def gueltige(sprecher: str) -> list[tuple[str, str, str]]:
    """Die gültigen Aufnahmen der Reihe nach: Kennung, Datum, Text der Vorlage."""
    with Session(deps.engine_fuer(sprecher)) as sitzung:
        return [
            (aufnahme.id, aufnahme.erstellt, vorlage.text)
            for aufnahme, vorlage in sitzung.execute(
                select(Aufnahme, Vorlage)
                .join(Vorlage, Vorlage.id == Aufnahme.prompt_id)
                .where(Aufnahme.status == GUELTIG)
                .order_by(*zuschnitt.reihenfolge())
            ).tuples()
        ]


def rahmen(pfad: Path) -> bytes:
    with wave.open(str(pfad), "rb") as datei:
        return datei.readframes(datei.getnframes())


def text_von(sprecher: str, kennung: str) -> str:
    """Der Text einer Aufnahme, wie ihn der Editor vorbelegt."""
    with Session(deps.engine_fuer(sprecher)) as sitzung:
        aufnahme = sitzung.get(Aufnahme, kennung)
        return aufnahme.text_zu(sitzung.get(Vorlage, aufnahme.prompt_id))


def dauer_von(sprecher: str, kennung: str) -> float:
    with Session(deps.engine_fuer(sprecher)) as sitzung:
        return sitzung.get(Aufnahme, kennung).dauer_s


def speichere(
    schneider: TestClient,
    sprecher: str,
    kennung: str,
    start_s: float,
    ende_s: float,
    teilung_s: float | None = None,
    texte: list[str] | None = None,
):
    """Was der Editor beim Speichern schickt; ohne Texte der bisherige."""
    if texte is None:
        text = text_von(sprecher, kennung)
        texte = [text] if teilung_s is None else text.split(" ", 1)
    return schneider.post(
        f"/api/zuschnitt/speichern?sprecher={sprecher}",
        json={
            "id": kennung,
            "start_s": start_s,
            "ende_s": ende_s,
            "teilung_s": teilung_s,
            "texte": texte,
        },
    )


def kuerze(schneider: TestClient, sprecher: str, kennung: str, start_s: float, ende_s: float):
    return speichere(schneider, sprecher, kennung, start_s, ende_s)


def miss(sprecher: str, kennung: str, erkennung_id: str = "erk_test") -> None:
    """Einen Messwert an eine Aufnahme hängen - ohne Whisper."""
    with Session(deps.engine_fuer(sprecher)) as sitzung:
        sitzung.add(
            Erkennung(
                id=erkennung_id,
                recording_id=kennung,
                modell="small",
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


def als_korrektur(sprecher: str, kennung: str) -> None:
    """Die Quelle dieser Aufnahme zur Korrektur machen, wie aus „schreiben"."""
    with Session(deps.engine_fuer(sprecher)) as sitzung:
        vorlage = sitzung.get(Vorlage, sitzung.get(Aufnahme, kennung).prompt_id)
        sitzung.get(Textquelle, vorlage.source_id).art = "korrektur"
        sitzung.commit()


class TestSchluessel:
    def test_ohne_gesetzten_schluessel_ist_alles_zu(
        self, klient: TestClient, sprecher: str
    ) -> None:
        """Leer heißt abgeschaltet, nicht offen - wie bei Verwaltung und Aufsicht."""
        antwort = klient.get(f"/api/zuschnitt/aufnahmen/rec_x?sprecher={sprecher}")
        assert antwort.status_code == 401
        assert "WORTLAUT_EDITOR_KEY" in antwort.json()["detail"]

    def test_sprecherzugang_allein_genuegt_nicht(
        self, _mit_schluessel: None, klient: TestClient, sprecher: str
    ) -> None:
        """Der Zugang sagt, wessen Aufnahmen - nicht, wer in den Bestand greift."""
        antwort = klient.get(f"/api/zuschnitt/aufnahmen/rec_x?sprecher={sprecher}")
        assert antwort.status_code == 401
        assert "Bearbeitungsschlüssel" in antwort.json()["detail"]

    def test_falscher_schluessel_wird_abgewiesen(
        self, _mit_schluessel: None, klient: TestClient, sprecher: str
    ) -> None:
        klient.headers["X-Editor-Key"] = "daneben"
        antwort = klient.get(f"/api/zuschnitt/aufnahmen/rec_x?sprecher={sprecher}")
        assert antwort.status_code == 401

    def test_mit_schluessel_geht_es(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        antwort = schneider.get(f"/api/zuschnitt/aufnahmen/{kennung}?sprecher={sprecher}")
        assert antwort.status_code == 200
        assert antwort.json()["id"] == kennung


class TestAnsicht:
    def test_liefert_kurve_und_vorschlag(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        """Kurve und Grenzen kommen aus derselben Rechnung - sonst liegt die
        Linie neben dem Ausschlag."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        eine = schneider.get(f"/api/zuschnitt/aufnahmen/{kennung}?sprecher={sprecher}").json()

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
        kuerze(schneider, sprecher, kennung, 1.0, 2.0)

        eine = schneider.get(f"/api/zuschnitt/aufnahmen/{kennung}?sprecher={sprecher}").json()
        assert eine["dauer_s"] == pytest.approx(1.0, abs=0.05)

    def test_original_endpunkt_liefert_die_datei(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        kuerze(schneider, sprecher, kennung, 1.0, 2.0)

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

        antwort = kuerze(schneider, sprecher, kennung, 1.0, 3.0)
        assert antwort.status_code == 200
        assert antwort.json() == {"ids": [kennung]}

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
        kuerze(schneider, sprecher, kennung, 1.000_03, 2.000_03)

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
            kuerze(schneider, sprecher, kennung, grenzen[0], grenzen[1])

        rate, breite = 16_000, 2
        assert rahmen(datei) == vorher[int(1.5 * rate) * breite : int(2.5 * rate) * breite]

    def test_die_zeile_beschreibt_die_neue_datei(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        kuerze(schneider, sprecher, kennung, 1.0, 3.0)
        with Session(deps.engine_fuer(sprecher)) as sitzung:
            assert sitzung.get(Aufnahme, kennung).dauer_s == pytest.approx(2.0, abs=0.01)

    def test_leerer_ausschnitt_wird_abgewiesen(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        antwort = kuerze(schneider, sprecher, kennung, 2.0, 1.0)
        assert antwort.status_code == 400

    def test_verlaengern_geht_nicht(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        """Nach dem Schnitt ist das Weggeschnittene weg - das Ende liegt in der Datei."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        kuerze(schneider, sprecher, kennung, 1.0, 2.0)
        assert kuerze(schneider, sprecher, kennung, 0.0, 3.0).status_code == 400

    def test_unbekannte_aufnahme(self, schneider: TestClient, sprecher: str) -> None:
        antwort = speichere(schneider, sprecher, "rec_gibtsnicht", 1.0, 2.0, texte=["x"])
        assert antwort.status_code == 404


class TestFolgen:
    """Nach dem Schnitt arbeitet jede App mit der gekürzten Datei."""

    def _mit_zuschnitt(
        self, schneider: TestClient, sprecher: str, audio_datei: dict
    ) -> str:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        antwort = kuerze(schneider, sprecher, kennung, 1.0, 2.0)
        assert antwort.status_code == 200, antwort.text
        return kennung

    def test_anhoeren_liefert_die_gekuerzte_datei(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        kennung = self._mit_zuschnitt(schneider, sprecher, audio_datei)
        antwort = schneider.get(f"/api/recordings/{kennung}/audio?sprecher={sprecher}")
        assert antwort.status_code == 200
        datei = tmp_path / "data" / corpus.audio_relpfad(sprecher, kennung)
        assert antwort.content == datei.read_bytes()

    def test_messwerte_werden_verworfen(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        """Eine Zahl vom alten Ton beschriebe eine Datei, die es nicht mehr
        gibt - und die Auswertung hielte sie für erledigt."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        miss(sprecher, kennung)

        kuerze(schneider, sprecher, kennung, 1.0, 2.0)

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
            zeile = auftraege._manifestzeile(proben[0], "vorlage", sprecher)

        assert zeile["audio"] == f"audio/{kennung}.wav"
        assert zeile["dauer_s"] == pytest.approx(1.0, abs=0.01)


class TestText:
    """Der Text steht an der Aufnahme; die Vorlage bleibt, wie sie war."""

    def test_ein_neuer_text_steht_an_der_aufnahme(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        with Session(deps.engine_fuer(sprecher)) as sitzung:
            vorher = sitzung.get(Vorlage, sitzung.get(Aufnahme, kennung).prompt_id).text
        miss(sprecher, kennung)
        antwort = speichere(
            schneider, sprecher, kennung, 0.0, dauer_von(sprecher, kennung), texte=["etwas  anderes"]
        )
        assert antwort.status_code == 200, antwort.text

        with Session(deps.engine_fuer(sprecher)) as sitzung:
            aufnahme = sitzung.get(Aufnahme, kennung)
            assert aufnahme.text == "etwas anderes"
            assert sitzung.get(Vorlage, aufnahme.prompt_id).text == vorher
            # Gemessen war gegen den alten Text.
            assert sitzung.get(Erkennung, "erk_test") is None
        eine = schneider.get(f"/api/zuschnitt/aufnahmen/{kennung}?sprecher={sprecher}").json()
        assert eine["text"] == "etwas anderes"

    def test_derselbe_text_laesst_die_messwerte_stehen(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        miss(sprecher, kennung)
        assert speichere(schneider, sprecher, kennung, 0.0, dauer_von(sprecher, kennung)).status_code == 200
        with Session(deps.engine_fuer(sprecher)) as sitzung:
            assert sitzung.get(Erkennung, "erk_test") is not None

    def test_ohne_text_wird_abgewiesen(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        assert speichere(schneider, sprecher, kennung, 0.0, dauer_von(sprecher, kennung), texte=[" "]).status_code == 400

    def test_eine_korrektur_gilt_danach_als_geprueft(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        """Auch ohne geänderten Text - das Speichern ist die Prüfung."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        als_korrektur(sprecher, kennung)
        eine = schneider.get(f"/api/zuschnitt/aufnahmen/{kennung}?sprecher={sprecher}").json()
        assert eine["korrektur"] is True
        assert eine["validiert"] is False

        assert speichere(schneider, sprecher, kennung, 0.0, dauer_von(sprecher, kennung)).status_code == 200

        with Session(deps.engine_fuer(sprecher)) as sitzung:
            assert sitzung.get(Aufnahme, kennung).validiert is True

    def test_erst_die_gepruefte_korrektur_wird_gemessen(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        from apps.hoeren.backend.services import auswertung

        kennung = nimm_auf(schneider, sprecher, audio_datei)
        als_korrektur(sprecher, kennung)

        def gemessen() -> bool:
            with Session(deps.engine_fuer(sprecher)) as sitzung:
                return kennung in {a.id for a, _ in auswertung.gemessene_aufnahmen(sitzung)}

        assert not gemessen()
        speichere(schneider, sprecher, kennung, 0.0, dauer_von(sprecher, kennung))
        assert gemessen()

    def test_eine_vorlage_wird_nicht_geprueft(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        speichere(schneider, sprecher, kennung, 0.0, dauer_von(sprecher, kennung), texte=["anders"])
        with Session(deps.engine_fuer(sprecher)) as sitzung:
            assert sitzung.get(Aufnahme, kennung).validiert is False

    def test_die_auswertung_misst_gegen_den_neuen_text(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        speichere(schneider, sprecher, kennung, 0.0, dauer_von(sprecher, kennung), texte=["was wirklich gesagt wurde"])
        vergleich = schneider.get(f"/api/auswertung/{kennung}?sprecher={sprecher}").json()
        assert vergleich["referenz"] == "was wirklich gesagt wurde"


class TestTeilen:
    """Eine Aufnahme in zwei neue zerlegen - Ton und Text, an derselben Vorlage."""

    def test_die_teile_liegen_lueckenlos_aneinander(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        """Byte für Byte der Bereich des Originals - kein Rahmen doppelt, keiner fehlt."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        original = tmp_path / "data" / corpus.audio_relpfad(sprecher, kennung)
        rate, breite = 16_000, 2
        erwartet = rahmen(original)[int(0.5 * rate) * breite : int(3.5 * rate) * breite]

        antwort = speichere(schneider, sprecher, kennung, 0.5, 3.5, teilung_s=2.0)
        assert antwort.status_code == 200, antwort.text
        vorn, hinten = antwort.json()["ids"]

        dateien = [tmp_path / "data" / corpus.audio_relpfad(sprecher, k) for k in (vorn, hinten)]
        assert len(rahmen(dateien[0])) == int(1.5 * rate) * breite
        assert rahmen(dateien[0]) + rahmen(dateien[1]) == erwartet

    def test_texte_datum_reihenfolge_und_vorlage(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        """Die Teile stehen an der Stelle des Originals, tragen sein Datum und seine Vorlage."""
        erste = nimm_auf(schneider, sprecher, audio_datei)
        zweite = nimm_auf(schneider, sprecher, audio_datei)
        ((_, datum, text), _) = gueltige(sprecher)
        with Session(deps.engine_fuer(sprecher)) as sitzung:
            vorlage_id = sitzung.get(Aufnahme, erste).prompt_id
        vorn, hinten = speichere(schneider, sprecher, erste, 0.5, 3.5, teilung_s=2.0).json()["ids"]

        liste = gueltige(sprecher)
        assert [kennung for kennung, _, _ in liste] == [vorn, hinten, zweite]
        assert liste[0][1] == liste[1][1] == datum
        assert f"{text_von(sprecher, vorn)} {text_von(sprecher, hinten)}" == text

        with Session(deps.engine_fuer(sprecher)) as sitzung:
            for teil, nummer in ((vorn, 1), (hinten, 2)):
                zeile = sitzung.get(Aufnahme, teil)
                assert zeile.sortierschluessel == f"{erste}.{nummer}"
                assert zeile.prompt_id == vorlage_id
                assert zuschnitt.vorfahren(zeile) == [erste]
            # Die Vorlage bleibt - ihre gültigen Aufnahmen sind jetzt die Teile.
            assert sitzung.get(Vorlage, vorlage_id).text == text

    def test_der_text_darf_berichtigt_werden(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        """Gesprochen wird nicht immer, was dasteht - die Teile tragen, was gesagt wurde."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        antwort = speichere(
            schneider, sprecher, kennung, 0.5, 3.5, teilung_s=2.0, texte=["eins", "etwas  anderes"]
        )
        assert antwort.status_code == 200, antwort.text
        _, hinten = antwort.json()["ids"]
        eine = schneider.get(f"/api/zuschnitt/aufnahmen/{hinten}?sprecher={sprecher}").json()
        assert eine["text"] == "etwas anderes"

    def test_jeder_teil_braucht_text(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        for texte in (["eins", " "], ["eins"]):
            antwort = speichere(schneider, sprecher, kennung, 0.5, 3.5, teilung_s=2.0, texte=texte)
            assert antwort.status_code == 400

    def test_ein_teil_wird_wieder_geteilt(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        """Ein Teil ist selbst ein Original: Seine Teile hängen unter ihm."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        vorn, _ = speichere(
            schneider,
            sprecher,
            kennung,
            0.0,
            dauer_von(sprecher, kennung),
            teilung_s=2.0,
            texte=["eins zwei", "drei"],
        ).json()["ids"]
        antwort = speichere(
            schneider, sprecher, vorn, 0.0, 2.0, teilung_s=1.0, texte=["eins", "zwei"]
        )
        assert antwort.status_code == 200, antwort.text
        enkel_vorn, enkel_hinten = antwort.json()["ids"]
        with Session(deps.engine_fuer(sprecher)) as sitzung:
            assert sitzung.get(Aufnahme, enkel_vorn).sortierschluessel == f"{kennung}.1.1"
            assert sitzung.get(Aufnahme, enkel_hinten).sortierschluessel == f"{kennung}.1.2"
            assert zuschnitt.stamm(sitzung.get(Aufnahme, enkel_vorn)) == kennung
            # Die Vorfahren stehen am Teil, auch wenn beide gelöscht sind.
            assert sitzung.get(Aufnahme, vorn) is None
            assert zuschnitt.vorfahren(sitzung.get(Aufnahme, enkel_hinten)) == [kennung, vorn]

    def test_teilung_muss_zwischen_den_grenzen_liegen(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        for teilung in (0.5, 3.5, 3.8):
            assert speichere(schneider, sprecher, kennung, 0.5, 3.5, teilung_s=teilung).status_code == 400
        # Nichts angelegt, nichts gelöscht.
        assert [eine for eine, _, _ in gueltige(sprecher)] == [kennung]

    def test_die_vorlage_bleibt_erledigt(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        """Die Teile sind die gültigen Aufnahmen der Vorlage - in der Warteschlange steht sie nicht."""
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        vorher = schneider.get("/api/prompts/next").json()
        fortschritt = schneider.get("/api/progress").json()
        speichere(schneider, sprecher, kennung, 0.5, 3.5, teilung_s=2.0)
        nachher = schneider.get("/api/prompts/next").json()
        assert nachher["aktuell"]["id"] == vorher["aktuell"]["id"]
        assert schneider.get("/api/progress").json()["offene_einheiten"] == (
            fortschritt["offene_einheiten"]
        )

    def test_die_teile_einer_korrektur_sind_geprueft(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        als_korrektur(sprecher, kennung)
        ids = speichere(schneider, sprecher, kennung, 0.5, 3.5, teilung_s=2.0).json()["ids"]
        with Session(deps.engine_fuer(sprecher)) as sitzung:
            assert [sitzung.get(Aufnahme, teil).validiert for teil in ids] == [True, True]

    def test_die_teile_liegen_in_der_faltung_des_originals(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        from apps.lernen.backend.services import aufteilung

        for _ in range(3):
            kennung = nimm_auf(schneider, sprecher, audio_datei)
        with Session(deps.engine_fuer(sprecher)) as korpus:
            vorher = {probe.aufnahme.id: probe.faltung for probe in aufteilung.proben(korpus)}
        ids = speichere(schneider, sprecher, kennung, 0.5, 3.5, teilung_s=2.0).json()["ids"]
        with Session(deps.engine_fuer(sprecher)) as korpus:
            nachher = {probe.aufnahme.id: probe.faltung for probe in aufteilung.proben(korpus)}
        assert nachher[ids[0]] == nachher[ids[1]] == vorher[kennung]


class TestOriginal:
    """Nach dem Teilen ist das Original weg - Zeile, Datei, Messwerte; die Vorlage bleibt."""

    def test_zeile_datei_und_messwerte_gehen(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict, tmp_path: Path
    ) -> None:
        kennung = nimm_auf(schneider, sprecher, audio_datei)
        datei = tmp_path / "data" / corpus.audio_relpfad(sprecher, kennung)
        miss(sprecher, kennung, "erk_original")

        assert speichere(schneider, sprecher, kennung, 0.5, 3.5, teilung_s=2.0).status_code == 200

        assert not datei.exists()
        with Session(deps.engine_fuer(sprecher)) as sitzung:
            assert sitzung.get(Aufnahme, kennung) is None
            assert sitzung.get(Erkennung, "erk_original") is None


class TestAlteOriginale:
    """`scripts/alte_originale.py`: Originale neben ihren Teilen aus älteren Beständen."""

    def test_findet_originale_mit_teilen_ueber_alle_stufen(
        self, schneider: TestClient, sprecher: str, quelle: str, audio_datei: dict
    ) -> None:
        original = nimm_auf(schneider, sprecher, audio_datei)
        allein = nimm_auf(schneider, sprecher, audio_datei)
        with Session(deps.engine_fuer(sprecher)) as sitzung:
            vorlage = sitzung.get(Aufnahme, original).prompt_id
            vorlage_allein = sitzung.get(Aufnahme, allein).prompt_id
            # Wie ältere Bestände: Teil und Teil des Teils neben dem Original.
            for kennung, schluessel, an in (
                ("rec_teil", f"{original}.1", vorlage_allein),
                ("rec_enkel", f"{original}.1.1", vorlage_allein),
            ):
                zeile = sitzung.get(Aufnahme, allein)
                sitzung.add(
                    Aufnahme(
                        id=kennung,
                        prompt_id=an,
                        speaker_id=zeile.speaker_id,
                        session_id=zeile.session_id,
                        blob=zeile.blob,
                        dauer_s=zeile.dauer_s,
                        pegel_dbfs=zeile.pegel_dbfs,
                        spitze_dbfs=zeile.spitze_dbfs,
                        clipping_anteil=zeile.clipping_anteil,
                        stille_vorn_s=zeile.stille_vorn_s,
                        stille_hinten_s=zeile.stille_hinten_s,
                        modus=zeile.modus,
                        status=GUELTIG,
                        hinweise="[]",
                        externe_id=None,
                        sortierschluessel=schluessel,
                        erstellt=zeile.erstellt,
                    )
                )
            sitzung.commit()

            gefunden = {aufnahme.id for aufnahme in zuschnitt.geteilte_originale(sitzung)}
            assert gefunden == {original, "rec_teil"}

            for aufnahme in zuschnitt.geteilte_originale(sitzung):
                zuschnitt.entferne(sitzung, aufnahme)
            sitzung.commit()
            assert sitzung.get(Aufnahme, original) is None
            assert sitzung.get(Vorlage, vorlage) is None
            assert sitzung.get(Aufnahme, "rec_enkel") is not None
            assert zuschnitt.geteilte_originale(sitzung) == []
