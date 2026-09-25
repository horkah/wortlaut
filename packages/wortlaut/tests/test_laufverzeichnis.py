"""Das Laufverzeichnis - die Nahtstelle zwischen „lernen" und der Karte.

Zwei Prozesse in zwei Containern lesen und schreiben hier dieselben Dateien.
Was dabei schiefgehen kann, geht leise schief: eine halb geschriebene Datei,
eine Zeile, die noch keine ganze ist, ein Auftrag, den niemand mehr als offen
erkennt. Genau das steht hier geprüft.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from wortlaut import laeufe


def _auftrag(datenverzeichnis: Path, job_id: str, sprecher: str = "spr_a") -> Path:
    verzeichnis = laeufe.lauf_verzeichnis(datenverzeichnis, job_id)
    laeufe.schreibe_json(
        verzeichnis / laeufe.AUFTRAG,
        {"job_id": job_id, "sprecher_id": sprecher, "methode": "lora", "daten": "original"},
    )
    return verzeichnis


class TestFaltungen:
    def test_jede_faltung_kommt_gleich_oft_vor(self) -> None:
        vergeben = laeufe.verteile([1] * (laeufe.FALTUNGEN * 4))
        assert sorted(set(vergeben)) == list(range(laeufe.FALTUNGEN))
        assert all(vergeben.count(faltung) == 4 for faltung in range(laeufe.FALTUNGEN))

    def test_einzelne_aufnahmen_gehen_reihum(self) -> None:
        # 1, 2, 3, 4, 5, 6, 1, 2, … - die siebte Aufnahme fängt wieder vorn an.
        n = laeufe.FALTUNGEN
        assert laeufe.verteile([1] * (2 * n + 1)) == [*range(n), *range(n), 0]

    def test_eine_grosse_gruppe_wird_aufgeholt(self) -> None:
        # So stand FEMKE bei 4, 4, 4, 6, 4, 4: eine dreiteilige Verwandtschaft
        # an vierter Stelle, reihum weitergezählt. Nach Zählerstand überspringen
        # die nächsten Aufnahmen die volle Faltung, bis die anderen gleichauf
        # sind.
        groessen = [1, 1, 1, 3, *[1] * 20]
        vergeben = laeufe.verteile(groessen)
        stand = [0] * laeufe.FALTUNGEN
        for faltung, groesse in zip(vergeben, groessen, strict=True):
            stand[faltung] += groesse
        assert stand == [5, 5, 4, 4, 4, 4]
        assert vergeben[:6] == [0, 1, 2, 3, 4, 5]
        assert vergeben[6:11] == [0, 1, 2, 4, 5]

    def test_bei_gleichstand_die_niedrigste_nummer(self) -> None:
        assert laeufe.verteile([2, 1, 1]) == [0, 1, 2]
        assert laeufe.verteile([]) == []


class TestWarteschlange:
    def test_ohne_zustand_ist_ein_auftrag_offen(self, tmp_path: Path) -> None:
        _auftrag(tmp_path, "job_1")
        offen = laeufe.naechster_offener(tmp_path)
        assert offen is not None and offen.job_id == "job_1"

    def test_mit_zustand_ist_er_es_nicht_mehr(self, tmp_path: Path) -> None:
        verzeichnis = _auftrag(tmp_path, "job_1")
        laeufe.schreibe_json(verzeichnis / laeufe.ZUSTAND, {"status": laeufe.LAEUFT})
        assert laeufe.naechster_offener(tmp_path) is None

    def test_der_aelteste_kommt_zuerst(self, tmp_path: Path) -> None:
        # Die Kennungen sind zeitlich sortierbar (siehe `ids.py`), also ist die
        # Reihenfolge im Verzeichnis die der Aufträge.
        for job_id in ("job_01B", "job_01A", "job_01C"):
            _auftrag(tmp_path, job_id)
        offen = laeufe.naechster_offener(tmp_path)
        assert offen is not None and offen.job_id == "job_01A"

    def test_ein_verzeichnis_ohne_auftrag_wird_uebergangen(self, tmp_path: Path) -> None:
        # Etwa ein halb angelegter Lauf: Der Auftrag wird zuletzt geschrieben,
        # genau damit dieser Fall kein offener Lauf ist.
        (laeufe.wurzel(tmp_path) / "job_halb").mkdir(parents=True)
        assert laeufe.naechster_offener(tmp_path) is None

    def test_ohne_wurzel_ist_die_liste_leer(self, tmp_path: Path) -> None:
        assert laeufe.alle_laeufe(tmp_path) == []
        assert laeufe.naechster_offener(tmp_path) is None

    def test_nach_sprecher_gefiltert(self, tmp_path: Path) -> None:
        _auftrag(tmp_path, "job_1", "spr_a")
        _auftrag(tmp_path, "job_2", "spr_b")
        assert [lauf.job_id for lauf in laeufe.alle_laeufe(tmp_path, "spr_b")] == ["job_2"]


class TestGeteilteDateien:
    def test_json_wird_nie_halb_gesehen(self, tmp_path: Path) -> None:
        # Geschrieben wird daneben und dann umbenannt: Ein Leser sieht entweder
        # den alten Stand oder den neuen, nie die Hälfte.
        ziel = tmp_path / "zustand.json"
        laeufe.schreibe_json(ziel, {"status": "alt"})
        laeufe.schreibe_json(ziel, {"status": "neu"})
        assert laeufe.lies_json(ziel) == {"status": "neu"}
        assert not list(tmp_path.glob("*.neu"))

    def test_eine_fehlende_datei_ist_kein_fehler(self, tmp_path: Path) -> None:
        assert laeufe.lies_json(tmp_path / "gibtsnicht.json") is None

    def test_eine_halbe_datei_ist_auch_keiner(self, tmp_path: Path) -> None:
        # Kommt vor, wenn jemand von Hand hineingreift. Ein 500er in der
        # Oberfläche wäre die schlechtere Antwort als „noch nichts da".
        (tmp_path / "halb.json").write_text('{"status": "lae', encoding="utf-8")
        assert laeufe.lies_json(tmp_path / "halb.json") is None

    def test_eine_angefangene_zeile_wird_uebergangen(self, tmp_path: Path) -> None:
        # Der Trainer schreibt, während die Oberfläche liest. Die letzte Zeile
        # kann halb sein; sie kommt beim nächsten Takt vollständig.
        pfad = tmp_path / "fortschritt.jsonl"
        laeufe.haenge_an(pfad, {"art": "schritt", "schritt": 1})
        laeufe.haenge_an(pfad, {"art": "schritt", "schritt": 2})
        with pfad.open("a", encoding="utf-8") as datei:
            datei.write('{"art": "schr')

        gelesen = laeufe.lies_zeilen(pfad)
        assert [zeile["schritt"] for zeile in gelesen] == [1, 2]

    def test_fehlende_jsonl_ist_leer(self, tmp_path: Path) -> None:
        assert laeufe.lies_zeilen(tmp_path / "gibtsnicht.jsonl") == []


class TestManifest:
    def test_kommt_zeilenweise(self, tmp_path: Path) -> None:
        verzeichnis = _auftrag(tmp_path, "job_1")
        with (verzeichnis / laeufe.MANIFEST).open("w", encoding="utf-8") as datei:
            for nummer in range(3):
                datei.write(json.dumps({"audio": f"a{nummer}.wav"}) + "\n")

        assert [zeile["audio"] for zeile in laeufe.manifestzeilen(verzeichnis)] == [
            "a0.wav",
            "a1.wav",
            "a2.wav",
        ]

    def test_ohne_manifest_kommt_nichts(self, tmp_path: Path) -> None:
        verzeichnis = _auftrag(tmp_path, "job_1")
        assert list(laeufe.manifestzeilen(verzeichnis)) == []


class TestVokabular:
    @pytest.mark.parametrize("name", laeufe.METHODEN)
    def test_jede_methode_hat_ein_rezept(self, name: str) -> None:
        # Ein Auftrag mit einer Methode ohne Rezept scheiterte erst im Trainer,
        # Minuten nach dem Knopfdruck.
        rezept = (
            Path(__file__).resolve().parents[3]
            / "apps/lernen/training/rezepte"
            / f"whisper_{name}.yaml"
        )
        assert rezept.is_file(), rezept


class TestOptionscode:
    def test_nur_vorgaben_ergibt_grundmodell_und_methode(self) -> None:
        auftrag = {"basismodell": "openai/whisper-small", "methode": "lora", "daten": "original"}
        assert laeufe.optionscode(auftrag) == "SL"

    def test_jede_gewaehlte_achse_ist_ein_glied(self) -> None:
        auftrag = {
            "basismodell": "openai/whisper-medium",
            "methode": "lora",
            "daten": "augmentiert",
            "dauer": "geduldig",
            "augmentierung": "voll",
            "tempowahl": "optimal",
            "abschluss": "beides",
        }
        assert laeufe.optionscode(auftrag) == "ML-A-E-SRP-Ts-CI"

    def test_die_alte_tempowahl_zaehlt_als_aus(self) -> None:
        auftrag = {"basismodell": "openai/whisper-small", "methode": "full",
                   "tempowahl": "wie_eingestellt"}
        assert laeufe.optionscode(auftrag) == "SV"

    def test_ein_unbekannter_wert_faellt_auf(self) -> None:
        auftrag = {"basismodell": "openai/whisper-small", "methode": "lora", "abschluss": "neu"}
        assert laeufe.optionscode(auftrag) == "SL-?"

    @pytest.mark.parametrize(
        ("basismodell", "code"),
        [
            ("openai/whisper-small", "S"),
            ("openai/whisper-medium", "M"),
            ("openai/whisper-large-v3", "L3"),
            ("openai/whisper-large-v3-turbo", "L3T"),
        ],
    )
    def test_grundmodellcode(self, basismodell: str, code: str) -> None:
        assert laeufe.grundmodellcode(basismodell) == code

    def test_die_glieder_verschiedener_achsen_teilen_keinen_anfang(self) -> None:
        # Sonst hieße `C` je nach Stelle zweierlei.
        tafeln = (
            laeufe.CODE_DATENSATZ,
            laeufe.CODE_DAUER,
            laeufe.CODE_AUGMENTIERUNG,
            laeufe.CODE_TEMPO,
            laeufe.CODE_ABSCHLUSS,
        )
        anfaenge = [{code[0] for code in tafel.values() if code} for tafel in tafeln]
        for i, eine in enumerate(anfaenge):
            for andere in anfaenge[i + 1 :]:
                assert not eine & andere, (eine, andere)

    def test_jeder_wert_jeder_achse_hat_ein_glied(self) -> None:
        assert set(laeufe.CODE_METHODE) == set(laeufe.METHODEN)
        assert set(laeufe.CODE_DATENSATZ) == set(laeufe.DATENSAETZE)
        assert set(laeufe.CODE_DAUER) == set(laeufe.DAUERN)
        assert set(laeufe.CODE_AUGMENTIERUNG) == set(laeufe.AUGMENTIERUNGEN)
        assert set(laeufe.CODE_TEMPO) == set(laeufe.TEMPI)
        assert set(laeufe.CODE_ABSCHLUSS) == set(laeufe.ABSCHLUESSE)


class TestZwischenstaende:
    """Was nach einem Lauf weggeräumt wird - und was dabei stehen bleibt.

    Ein abgebrochener Lauf hatte seinen `arbeitsstand` liegen gelassen: knapp
    drei Gigabyte je Fehllauf, die irgendwann die Platte des Wirts füllten und
    den nächsten Lauf aus demselben Grund umbrachten. Weggeräumt wird deshalb
    auf beiden Wegen und von zwei Seiten, und beides steht hier geprüft.
    """

    def _zwischenstaende(self, verzeichnis: Path) -> None:
        arbeit = verzeichnis / laeufe.ARBEITSSTAND / "checkpoint-63"
        arbeit.mkdir(parents=True)
        (arbeit / "optimizer.pt").write_bytes(b"0" * 16)
        gewichte = verzeichnis / laeufe.GEWICHTE
        gewichte.mkdir(parents=True)
        (gewichte / "model.safetensors").write_bytes(b"0" * 16)

    def test_beide_verzeichnisse_gehen_weg(self, tmp_path: Path) -> None:
        verzeichnis = _auftrag(tmp_path, "job_1")
        self._zwischenstaende(verzeichnis)

        entfernt = laeufe.raeume_zwischenstaende_auf(verzeichnis)

        assert set(entfernt) == {laeufe.ARBEITSSTAND, laeufe.GEWICHTE}
        assert not (verzeichnis / laeufe.ARBEITSSTAND).exists()
        assert not (verzeichnis / laeufe.GEWICHTE).exists()

    def test_der_auftrag_und_sein_protokoll_bleiben(self, tmp_path: Path) -> None:
        # Der Grund, warum hier nicht das ganze Laufverzeichnis gelöscht wird:
        # Woran ein Lauf gescheitert ist, steht danach noch da.
        verzeichnis = _auftrag(tmp_path, "job_1")
        self._zwischenstaende(verzeichnis)
        (verzeichnis / laeufe.PROTOKOLL).write_text("es krachte\n", encoding="utf-8")
        laeufe.schreibe_json(verzeichnis / laeufe.ZUSTAND, {"status": laeufe.GESCHEITERT})

        laeufe.raeume_zwischenstaende_auf(verzeichnis)

        assert (verzeichnis / laeufe.AUFTRAG).is_file()
        assert (verzeichnis / laeufe.PROTOKOLL).read_text(encoding="utf-8") == "es krachte\n"
        lauf = laeufe.lies_lauf(tmp_path, "job_1")
        assert lauf is not None and lauf.status == laeufe.GESCHEITERT

    def test_zweimal_zu_raeumen_ist_kein_fehler(self, tmp_path: Path) -> None:
        # Genau das ist der Normalfall: Der rechnende Prozess räumt selbst auf,
        # der Läufer sieht danach noch einmal nach.
        verzeichnis = _auftrag(tmp_path, "job_1")
        self._zwischenstaende(verzeichnis)

        assert laeufe.raeume_zwischenstaende_auf(verzeichnis)
        assert laeufe.raeume_zwischenstaende_auf(verzeichnis) == []

    def test_ein_lauf_ohne_zwischenstaende_meldet_nichts(self, tmp_path: Path) -> None:
        verzeichnis = _auftrag(tmp_path, "job_1")
        assert laeufe.raeume_zwischenstaende_auf(verzeichnis) == []
