"""Die Auskunft für „System" - geprüft wird das Lesen, nicht die Maschine.

Was `nvidia-smi` und `/proc` auf dieser Maschine gerade sagen, weiß kein
Test. Wie ihre Ausgabe gelesen wird, schon: Dort steckt die Rechnung, und
dort sitzen die Fallen - „[N/A]" statt einer Zahl, `iowait`, das keine
Arbeit ist.
"""

from __future__ import annotations

from pathlib import Path

from wortlaut import systemlage

NVIDIA_SMI = (
    "0, NVIDIA GeForce RTX 2080 Ti, 550.163.01, 7.5, 11264, 5194, 83, 55, 69, "
    "259.87, 260.00, 55, 1800, 2175, 3, 16\n"
    "1, Tesla T4, 550.163.01, 7.5, 15360, 0, 0, 0, 41, [N/A], 70.00, [N/A], 300, "
    "1590, [Not Supported], [Not Supported]\n"
)


class TestKarten:
    def test_eine_zeile_je_karte(self) -> None:
        erste, zweite = systemlage.lies_karten(NVIDIA_SMI)
        assert erste.name == "NVIDIA GeForce RTX 2080 Ti"
        assert erste.speicher_mib == 11264
        assert erste.speicher_belegt_mib == 5194
        assert erste.auslastung == 83
        assert erste.leistung_w == 259.87
        assert erste.pcie == "Gen 3 ×16"
        assert zweite.index == 1

    def test_was_die_karte_nicht_weiss_bleibt_leer(self) -> None:
        # Ohne Lüfter und ohne Messung der Leistung - kein Fehler, nur keine Zahl.
        zweite = systemlage.lies_karten(NVIDIA_SMI)[1]
        assert zweite.leistung_w is None
        assert zweite.luefter is None
        assert zweite.pcie is None
        assert zweite.leistung_grenze_w == 70

    def test_ohne_ausgabe_keine_karte(self) -> None:
        assert systemlage.lies_karten("") == []
        assert systemlage.lies_karten("Failed to initialize NVML\n") == []


class TestProzessor:
    VORHER = "cpu  100 0 100 800 0 0 0 0 0 0\ncpu0 50 0 50 400 0 0 0 0 0 0\nintr 1 2 3\n"
    NACHHER = "cpu  150 0 150 850 50 0 0 0 0 0\ncpu0 100 0 50 450 0 0 0 0 0 0\nintr 4 5 6\n"

    def test_last_ist_der_unterschied_zweier_ablesungen(self) -> None:
        last = systemlage.auslastung(
            systemlage.lies_zeiten(self.VORHER), systemlage.lies_zeiten(self.NACHHER)
        )
        # Insgesamt 200 Takte, davon 50 untätig und 50 im Warten auf die Platte.
        assert last["cpu"] == 50.0
        assert last["cpu0"] == 50.0

    def test_ohne_vergangene_zeit_keine_last(self) -> None:
        zeiten = systemlage.lies_zeiten(self.VORHER)
        assert systemlage.auslastung(zeiten, zeiten) == {"cpu": 0.0, "cpu0": 0.0}


class TestSpeicher:
    def test_belegt_ist_was_nicht_verfuegbar_ist(self) -> None:
        # Der Seitencache zählt nicht als belegt: Der Kern gibt ihn auf Zuruf her.
        meminfo = (
            "MemTotal:  1000 kB\nMemFree:  100 kB\nMemAvailable:  600 kB\n"
            "SwapTotal:  500 kB\nSwapFree:  500 kB\n"
        )
        speicher = systemlage.lies_speicher(meminfo)
        assert speicher.gesamt == 1000 * 1024
        assert speicher.belegt == 400 * 1024
        assert speicher.swap_belegt == 0


class TestAblagen:
    def test_jede_platte_nur_einmal(self, tmp_path: Path) -> None:
        (tmp_path / "unter").mkdir()
        ablagen = systemlage.ablagen([("Daten", tmp_path), ("Training", tmp_path / "unter")])
        assert [ablage.name for ablage in ablagen] == ["Daten"]

    def test_ein_fehlender_ort_faellt_weg(self, tmp_path: Path) -> None:
        assert systemlage.ablagen([("Fehlt", tmp_path / "gibt-es-nicht")]) == []


def test_lage_scheitert_nicht_an_dieser_maschine(tmp_path: Path) -> None:
    # Mit Karte oder ohne, unter Linux oder nicht: Eine Auskunft kommt heraus.
    lage = systemlage.lage([("Daten", tmp_path)])
    assert lage.ablagen and lage.ablagen[0].name == "Daten"
    assert isinstance(lage.karten, list)
