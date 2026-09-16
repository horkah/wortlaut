"""Vorlesen auf dem Server - die Mechanik, nicht der Klang.

Geprüft wird, was ohne Piper und ohne Stimmen gilt: dass nichts scheitert,
sondern still nichts zurückkommt. Das ist die Zusage, an der die Oberfläche
hängt - sie fällt dann auf die Browserstimme zurück, und wer einen Satz
nachsprechen will, soll ihn hören und keine Fehlermeldung lesen.

Dass Piper wirklich spricht, prüft kein Test hier: Das braucht eine
Stimmdatei von einigen Dutzend Megabyte. Gemessen wurde es von Hand -
4,34 s Audio in 1,19 s, 16 kHz, 16 bit, mono.

**Und wie es klingt, prüft hier erst recht nichts.** Das ist keine Lücke,
sondern eine Grenze: Ein Test, der eine Zeichenkette in eine Zeichenkette
überführt, kann nicht sagen, ob ein Mensch „ich" hört. Genau daran ist
einmal ein gut gemeinter Eingriff vorbeigelaufen - er brachte eine Meldung
von Piper zum Schweigen, verschlechterte dabei den Klang, und alle Tests
blieben grün (siehe den Kommentar über `PiperMotor` in `vorlesen.py`).

Wer am Lautweg etwas ändert, prüfe es deshalb, indem er den gesprochenen
Satz durch Whisper zurücklesen lässt und mit der Vorlage vergleicht. Das ist
in diesem Projekt keine fremde Übung: Genau das tut die Auswertung in
„hören", nur in der anderen Richtung.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from wortlaut import corpus, vorlesen


class TestSchluessel:
    def test_motor_und_stimme_stehen_im_schluessel(self) -> None:
        stimme = vorlesen.Stimme(schluessel="piper/de_DE-thorsten-high", name="T", erklaerung="")
        assert stimme.motor == "piper"

    def test_der_dateiname_vertraegt_keinen_schraegstrich(self) -> None:
        # Er trennt Motor und Stimme und darf in keinen Pfad; der Punkt trennt
        # im Dateinamen Vorlage und Stimme und darf es ebenso wenig.
        name = corpus.stimmenname("piper/de_DE-thorsten-high")
        assert "/" not in name
        assert "." not in name

    def test_der_pfad_nennt_vorlage_und_stimme(self) -> None:
        pfad = corpus.vorlesung_relpfad("spr_a", "prm_b", "piper/de_DE-eva_k-x_low")
        assert pfad.startswith(corpus.vorlesen_relpfad("spr_a"))
        assert pfad.endswith(".wav")
        assert "prm_b" in pfad


class TestOhneStimmen:
    def test_ein_leeres_verzeichnis_hat_keine_stimmen(self, tmp_path: Path) -> None:
        assert vorlesen.stimmen(tmp_path) == []

    def test_ein_fehlendes_verzeichnis_ist_kein_fehler(self, tmp_path: Path) -> None:
        # Der Normalfall einer frischen Installation.
        assert vorlesen.stimmen(tmp_path / "gibtsnicht") == []

    def test_halb_geladene_stimmen_zaehlen_nicht(self, tmp_path: Path) -> None:
        # Ohne die Beschreibung daneben lässt sich das Modell nicht laden.
        # Eine Stimme anzubieten, die beim ersten Klick scheitert, ist
        # schlechter als eine Stimme weniger.
        (tmp_path / "de_DE-thorsten-high.onnx").write_bytes(b"halb")
        assert vorlesen.stimmen(tmp_path) == []
        (tmp_path / "de_DE-thorsten-high.onnx.json").write_text("{}")
        assert [s.schluessel for s in vorlesen.stimmen(tmp_path)] == [
            "piper/de_DE-thorsten-high"
        ]

    def test_eine_bekannte_stimme_bekommt_ihren_namen(self, tmp_path: Path) -> None:
        (tmp_path / "de_DE-thorsten-high.onnx").write_bytes(b"x")
        (tmp_path / "de_DE-thorsten-high.onnx.json").write_text("{}")
        assert vorlesen.stimmen(tmp_path)[0].name == "Thorsten, hohe Auflösung"

    def test_eine_fremde_stimme_bekommt_ihren_dateinamen(self, tmp_path: Path) -> None:
        # Hässlich, aber richtig - und es hält niemanden davon ab, eine eigene
        # Stimme abzulegen.
        (tmp_path / "de_DE-sonstwer-low.onnx").write_bytes(b"x")
        (tmp_path / "de_DE-sonstwer-low.onnx.json").write_text("{}")
        assert vorlesen.stimmen(tmp_path)[0].name == "de_DE-sonstwer-low"

    def test_eine_nicht_vorhandene_stimme_wirft_den_erwarteten_fehler(
        self, tmp_path: Path
    ) -> None:
        # Erwartet, damit der Aufrufer weiterkommt: Er fällt auf die
        # Browserstimme zurück.
        motor = vorlesen.motor_fuer(tmp_path)
        with pytest.raises(vorlesen.VorlesenFehler):
            motor.sprich("Hallo", "piper/gibtsnicht", tmp_path / "raus.wav")

    def test_ein_unbekannter_motor_wirft(self, tmp_path: Path) -> None:
        with pytest.raises(vorlesen.VorlesenFehler):
            vorlesen.motor_fuer(tmp_path, "zauberei")

    def test_stimmen_schluckt_den_unbekannten_motor(self, tmp_path: Path) -> None:
        # Die Liste ist eine Auskunft und kein Weg, an dem etwas hängt.
        assert vorlesen.stimmen(tmp_path, "zauberei") == []
