"""Die Ränder abschneiden - und dabei keine Silbe verlieren.

Der Schaden ist einseitig: Ein bisschen Stille zu viel kostet Rechenzeit, ein
abgeschnittener Laut kostet die Aufnahme und macht die Vorlage daneben falsch.
Die Tests hier prüfen deshalb vor allem, wann **nicht** geschnitten wird.
"""

from __future__ import annotations

import array
import math
import wave
from pathlib import Path

from wortlaut import audio, stille, tempo, vorbereitung

RATE = audio.ABTASTRATE


def _welle(pfad: Path, abschnitte: list[tuple[float, float]]) -> Path:
    """Eine WAV-Datei aus Abschnitten von `(Dauer, Amplitude)`.

    Amplitude als Anteil des Vollausschlags; ein 220-Hz-Ton, damit es ein
    Signal ist und kein Gleichanteil.
    """
    werte = array.array("h")
    for dauer_s, pegel in abschnitte:
        for n in range(int(dauer_s * RATE)):
            werte.append(int(pegel * 32000 * math.sin(2 * math.pi * 220 * n / RATE)))
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(pfad), "wb") as datei:
        datei.setnchannels(1)
        datei.setsampwidth(2)
        datei.setframerate(RATE)
        datei.writeframes(werte.tobytes())
    return pfad


class TestGrenzen:
    def test_lange_raender_fallen(self, tmp_path: Path) -> None:
        # Zwei Sekunden Stille, eine Sekunde Ton, zwei Sekunden Stille.
        wav = _welle(tmp_path / "a.wav", [(2.0, 0.0), (1.0, 0.5), (2.0, 0.0)])
        von, bis = stille.grenzen(wav)
        # Der Rand bleibt stehen - und zwar auf beiden Seiten.
        assert 2.0 - stille.RAND_S - 0.05 <= von <= 2.0
        assert 3.0 <= bis <= 3.0 + stille.RAND_S + 0.05

    def test_wer_durchgehend_spricht_wird_nicht_geschnitten(self, tmp_path: Path) -> None:
        wav = _welle(tmp_path / "a.wav", [(3.0, 0.5)])
        assert stille.grenzen(wav) is None

    def test_ein_knappes_zehntel_lohnt_nicht(self, tmp_path: Path) -> None:
        # Sonst entstünde für jede Aufnahme eine zweite Datei, die nichts bringt.
        wav = _welle(tmp_path / "a.wav", [(0.05, 0.0), (3.0, 0.5), (0.05, 0.0)])
        assert stille.grenzen(wav) is None

    def test_eine_aufnahme_ganz_ohne_signal_bleibt_ganz(self, tmp_path: Path) -> None:
        # Bliebe nichts übrig, hat die Messung etwas anderes gefunden als eine
        # Äußerung - dann ist die ganze Aufnahme die ehrlichere Auskunft.
        wav = _welle(tmp_path / "a.wav", [(3.0, 0.0)])
        assert stille.grenzen(wav) is None

    def test_ein_gleichmaessiges_rauschen_gilt_als_stille(self, tmp_path: Path) -> None:
        """Der Fall, um den es geht: Es ist nicht still, aber es spricht niemand.

        Ein Lüfter unter der Sprache liegt weit unter deren Spitze, und die
        Schwelle in `audio.untersuche` ist relativ zu genau dieser Spitze.
        """
        leise = 0.004  # gut 48 dB unter der Sprache daneben
        wav = _welle(tmp_path / "a.wav", [(2.0, leise), (1.0, 0.5), (2.0, leise)])
        von, bis = stille.grenzen(wav)
        assert von > 1.0
        assert bis < 4.0

    def test_ein_geraeusch_am_rand_bleibt_lieber_stehen(self, tmp_path: Path) -> None:
        """Eine zuschlagende Tür gilt als Sprache - und das ist die Absicht.

        Sie von der Stimme zu unterscheiden verlangte ein zweites Modell. Der
        Fehler geht hier in die harmlose Richtung: ein Geräusch zu viel im
        Ausschnitt statt einer Silbe zu wenig.
        """
        wav = _welle(tmp_path / "a.wav", [(0.3, 0.6), (2.0, 0.0), (1.0, 0.5)])
        # Vorn das Geräusch, hinten die Stimme: An keinem der beiden Ränder
        # liegt Stille, also fällt nichts. Die zwei Sekunden **mitten** darin
        # bleiben ebenfalls stehen - geschnitten werden die Ränder und nicht
        # die Pausen, in denen jemand Luft holt.
        assert stille.grenzen(wav) is None


class TestGilt:
    def test_fehlt_die_angabe_wird_nicht_geschnitten(self) -> None:
        # Die eine Regel, und sie gilt überall gleich: Ein Stand von vor dieser
        # Achse hat ungeschnittene Ausschnitte gelernt.
        assert stille.gilt(None) is False
        assert stille.gilt(False) is False

    def test_nur_ein_ausdrueckliches_ja_zaehlt(self) -> None:
        # Kein `bool(wert)`: Eine Zeichenkette aus einer alten Datei wäre wahr,
        # ohne dass jemand das gemeint hätte.
        assert stille.gilt(True) is True
        assert stille.gilt("ja") is False
        assert stille.gilt(1) is False


class TestVorbereitung:
    def test_ohne_auftrag_entsteht_keine_datei(self, tmp_path: Path) -> None:
        wav = _welle(tmp_path / "a.wav", [(2.0, 0.0), (1.0, 0.5)])
        ablage = tmp_path / "ablage"
        ablage.mkdir()
        fertig, versatz = vorbereitung.bereite_vor(wav, ablage)
        assert fertig == wav
        assert versatz == 0.0
        assert not list(ablage.iterdir())

    def test_der_versatz_sagt_was_vorne_fehlt(self, tmp_path: Path) -> None:
        """Ohne ihn verrutscht in „schreiben" jeder Abschnitt.

        Whispers Zeitmarken zählen ab dem Anfang dessen, was es gehört hat.
        Wird vorn geschnitten, ist das nicht mehr der Anfang der Aufnahme.
        """
        wav = _welle(tmp_path / "a.wav", [(2.0, 0.0), (1.0, 0.5)])
        ablage = tmp_path / "ablage"
        ablage.mkdir()
        fertig, versatz = vorbereitung.bereite_vor(wav, ablage, schneiden=True)
        assert fertig != wav
        assert versatz > 1.0
        assert audio.dauer(fertig) < audio.dauer(wav)

    def test_aus_einem_alten_manifest_kommt_nichts(self) -> None:
        assert vorbereitung.aus_manifest({}) == (tempo.VORGABE, False)
        assert vorbereitung.aus_manifest(None) == (tempo.VORGABE, False)

    def test_aus_einem_neuen_manifest_kommt_beides(self) -> None:
        assert vorbereitung.aus_manifest({"tempo": 2.0, "stille": True}) == (2.0, True)
