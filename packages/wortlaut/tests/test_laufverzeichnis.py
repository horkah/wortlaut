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
    @staticmethod
    def _staemme(anzahl: int, vorsilbe: str = "rec_") -> list[str]:
        return [f"{vorsilbe}{nummer:04d}" for nummer in range(anzahl)]

    def test_dieselbe_kennung_dieselbe_faltung(self) -> None:
        staemme = self._staemme(50)
        assert laeufe.verteile(staemme) == laeufe.verteile(list(staemme))

    def test_neue_und_geloeschte_verschieben_keine_andere(self) -> None:
        # Die Zusage des Hashs: Eine Aufnahme misst in jedem Lauf in derselben
        # Faltung, was immer dazukommt oder wegfällt.
        staemme = self._staemme(60)
        vorher = dict(zip(staemme, laeufe.verteile(staemme), strict=True))
        spaeter = [*staemme[5:], *self._staemme(20, "neu_")]
        nachher = dict(zip(spaeter, laeufe.verteile(spaeter), strict=True))
        assert all(nachher[stamm] == vorher[stamm] for stamm in staemme[5:])

    def test_die_reihenfolge_zaehlt_nicht(self) -> None:
        staemme = self._staemme(40)
        vorwaerts = dict(zip(staemme, laeufe.verteile(staemme), strict=True))
        rueckwaerts = list(reversed(staemme))
        assert dict(zip(rueckwaerts, laeufe.verteile(rueckwaerts), strict=True)) == vorwaerts

    def test_viele_staemme_fuellen_jede_faltung(self) -> None:
        vergeben = laeufe.verteile(self._staemme(300))
        assert set(vergeben) == set(range(laeufe.FALTUNGEN))
        # Ungefähr gleich groß - ein Hash, kein Zählerstand.
        assert all(30 <= vergeben.count(faltung) <= 70 for faltung in range(laeufe.FALTUNGEN))

    @pytest.mark.parametrize("anzahl", [6, 7, 8, 11])
    def test_bei_wenigen_bleibt_keine_leer(self, anzahl: int) -> None:
        # Bliebe eine Faltung leer, ginge es reihum in Hash-Reihenfolge.
        vergeben = laeufe.verteile(self._staemme(anzahl))
        assert set(vergeben) == set(range(laeufe.FALTUNGEN))

    def test_leer_bleibt_leer(self) -> None:
        assert laeufe.verteile([]) == []


class TestMessenNurVorlagen:
    """Gemessen wird nur an Vorlagen; Korrekturen lernen in jeder Faltung mit."""

    @staticmethod
    def _manifest(verzeichnis: Path) -> None:
        zeilen = [
            {"recording_id": "rec_a", "faltung": 0, "quelle": "vorlage", "variante": "original"},
            {"recording_id": "rec_a", "faltung": 0, "quelle": "vorlage", "variante": "rauschen"},
            {"recording_id": "rec_k", "faltung": 0, "quelle": "korrektur", "variante": "original"},
            {"recording_id": "rec_k", "faltung": 0, "quelle": "korrektur", "variante": "rauschen"},
            {"recording_id": "rec_b", "faltung": 1, "quelle": "vorlage", "variante": "original"},
        ]
        (verzeichnis / laeufe.MANIFEST).write_text(
            "\n".join(json.dumps({**zeile, "audio": f"{zeile['recording_id']}.wav"}) for zeile in zeilen),
            encoding="utf-8",
        )

    @staticmethod
    def _kennungen(zeilen: list[dict]) -> list[tuple[str, str]]:
        return [(zeile["recording_id"], zeile["variante"]) for zeile in zeilen]

    def test_eine_korrektur_wird_nie_gemessen(self, tmp_path: Path) -> None:
        self._manifest(tmp_path)
        lern, mess = laeufe.zeilen_fuer_faltung(tmp_path, 0, laeufe.NUR_ORIGINAL)
        assert self._kennungen(mess) == [("rec_a", "original"), ("rec_a", "rauschen")]
        # Auch in ihrer eigenen Faltung lernt sie mit - gemessen wird dort ja nicht an ihr.
        assert self._kennungen(lern) == [("rec_k", "original"), ("rec_b", "original")]

    def test_mit_varianten_lernt_die_korrektur_in_allen_fassungen(self, tmp_path: Path) -> None:
        self._manifest(tmp_path)
        lern, _ = laeufe.zeilen_fuer_faltung(tmp_path, 1, laeufe.MIT_VARIANTEN)
        assert ("rec_k", "rauschen") in self._kennungen(lern)
        assert ("rec_b", "original") not in self._kennungen(lern)

    def test_das_endmodell_misst_nichts(self, tmp_path: Path) -> None:
        self._manifest(tmp_path)
        lern, mess = laeufe.zeilen_fuer_faltung(tmp_path, None, laeufe.NUR_ORIGINAL)
        assert mess == []
        assert {kennung for kennung, _ in self._kennungen(lern)} == {"rec_a", "rec_k", "rec_b"}


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
            "auswahl": "kern",
            "dauer": "geduldig",
            "augmentierung": "voll",
            "tempowahl": "optimal",
            "abschluss": "beides",
        }
        assert laeufe.optionscode(auftrag) == "ML-A-K-E-SRP-Ts-CI"

    def test_die_alte_tempowahl_zaehlt_als_aus(self) -> None:
        auftrag = {"basismodell": "openai/whisper-small", "methode": "full",
                   "tempowahl": "wie_eingestellt"}
        assert laeufe.optionscode(auftrag) == "SV"

    def test_ein_unbekannter_wert_faellt_auf(self) -> None:
        auftrag = {"basismodell": "openai/whisper-small", "methode": "lora", "abschluss": "neu"}
        assert laeufe.optionscode(auftrag) == "SL-?"

    def test_auf_einem_stand_steht_dessen_kennung_vorn(self) -> None:
        # Nicht `ML`: Ein Lauf auf `medium` und einer auf einem Stand darüber
        # sind verschiedene Rezepte und dürfen sich keine Folge teilen.
        auftrag = {
            "basismodell": "openai/whisper-medium",
            "ausgangsstand": "spr_x/20260926T0458-medium-lora-augmentiert-beides-voll-geduldig",
            "methode": "lora",
            "daten": "augmentiert",
        }
        assert laeufe.optionscode(auftrag) == "C6G67-L-A"
        assert laeufe.grundmodell_aus(auftrag) == auftrag["ausgangsstand"]

    def test_ohne_stand_ist_die_wahl_das_grundmodell(self) -> None:
        assert laeufe.grundmodell_aus({"basismodell": "openai/whisper-small"}) == (
            "openai/whisper-small"
        )

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
            laeufe.CODE_AUSWAHL,
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
        assert set(laeufe.CODE_AUSWAHL) == set(laeufe.AUSWAHLEN)
        assert set(laeufe.CODE_DAUER) == set(laeufe.DAUERN)
        assert set(laeufe.CODE_AUGMENTIERUNG) == set(laeufe.AUGMENTIERUNGEN)
        assert set(laeufe.CODE_TEMPO) == set(laeufe.TEMPI)
        assert set(laeufe.CODE_ABSCHLUSS) == set(laeufe.ABSCHLUESSE)


class TestKern:
    def test_ohne_kern_wird_auf_allem_gelernt(self, tmp_path: Path) -> None:
        assert laeufe.kern_aus(tmp_path, {"daten": "original"}) is None
        assert laeufe.kern_aus(tmp_path, {"auswahl": "alle"}) is None

    def test_der_kern_kommt_aus_der_kernauswahl(self, tmp_path: Path) -> None:
        laeufe.schreibe_json(tmp_path / laeufe.KERNAUSWAHL, {"kern": ["rec_a", "rec_b"]})
        assert laeufe.kern_aus(tmp_path, {"auswahl": "kern"}) == {"rec_a", "rec_b"}

    def test_ohne_datei_kein_stiller_rueckfall_auf_alles(self, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match="kernauswahl.json"):
            laeufe.kern_aus(tmp_path, {"auswahl": "kern"})

    def test_ein_ungewaehlter_kern_ist_kein_leerer(self, tmp_path: Path) -> None:
        # Offene Werte heißen: noch nicht gewählt - und nicht: auf nichts lernen.
        laeufe.schreibe_json(tmp_path / laeufe.KERNAUSWAHL, {"offen": ["rec_a"]})
        with pytest.raises(RuntimeError, match="noch nicht gewählt"):
            laeufe.kern_aus(tmp_path, {"auswahl": "kern"})

    def test_verwandte_bleiben_im_kern_zusammen(self) -> None:
        # rec_b ist ein Teil von rec_a: Beide müssen in dieselbe Faltung.
        staemme = {"rec_a": "rec_a", "rec_b": "rec_a", "rec_c": "rec_c", "rec_x": "rec_x"}
        faltungen = laeufe.verteile_kern(["rec_a", "rec_b", "rec_c"], staemme)
        assert set(faltungen) == {"rec_a", "rec_b", "rec_c"}
        assert faltungen["rec_a"] == faltungen["rec_b"] != faltungen["rec_c"]

    def test_ohne_eigene_faltungen_gelten_die_des_manifests(self, tmp_path: Path) -> None:
        # Eine Kernauswahl ohne eigene Faltungen: die des Manifests, auf den Kern beschränkt.
        (tmp_path / laeufe.MANIFEST).write_text(
            "\n".join(
                json.dumps({"recording_id": kennung, "faltung": faltung})
                for kennung, faltung in (("rec_a", 0), ("rec_b", 3), ("rec_c", 1))
            ),
            encoding="utf-8",
        )
        laeufe.schreibe_json(tmp_path / laeufe.KERNAUSWAHL, {"kern": ["rec_a", "rec_b"]})
        assert laeufe.kernfaltungen_aus(tmp_path, {"auswahl": "kern"}) == {"rec_a": 0, "rec_b": 3}

    def test_aufgerundet_und_bei_gleichstand_nach_kennung(self) -> None:
        assert laeufe.kern_anzahl(10) == 7
        assert laeufe.kern_anzahl(9) == 7
        assert laeufe.kern_anzahl(292) == 205
        wer = {"rec_c": 0.1, "rec_b": 0.2, "rec_a": 0.2, "rec_d": 0.9}
        assert laeufe.waehle_kern(wer) == ["rec_c", "rec_a", "rec_b"]


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
