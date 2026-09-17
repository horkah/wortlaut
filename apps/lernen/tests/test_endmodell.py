"""Der siebte Stand - der, mit dem später diktiert wird.

Die Zahlen eines Laufs stammen aus seinen sechs Faltungen. Freigegeben wird ein
siebtes Modell, das auf allem gelernt hat; **bewerten** lässt es sich nicht
mehr, denn es kennt jede Aufnahme. Bis September 2026 hieß das: Es wurde auch
nicht angesehen. Ein Lauf vom 13. September gab daraufhin einen Stand frei, der
den ersten Satz erkennt und dann weiterredet - während seine Faltungen daneben
bei WER 0,23 standen und niemand widersprach.

Hier steht, was seitdem dagegen steht: eine Prüfung, die kein Urteil über die
Güte fällt, sondern eines darüber, ob der Stand überhaupt noch zuhört.
"""

from __future__ import annotations

from apps.lernen.backend.api.modelle import _vorbehalt
from apps.lernen.training.bewerten import befund_ueber

FALTUNGEN = [{"wer": 0.23, "variante": "original"}] * 10


def _stichprobe(wer: float, anzahl: int = 6) -> list[dict]:
    return [{"wer": wer, "variante": "original"}] * anzahl


class TestBefund:
    def test_wer_auf_bekanntem_besser_ist_unauffaellig(self) -> None:
        # Der Normalfall: Das Endmodell hat den leichteren Teil und nutzt ihn.
        assert befund_ueber(_stichprobe(0.20), FALTUNGEN)["auffaellig"] is False

    def test_gleichauf_ist_noch_in_ordnung(self) -> None:
        # Genau gleichauf heißt nicht „kaputt" - der Spielraum ist dafür da.
        assert befund_ueber(_stichprobe(0.23), FALTUNGEN)["auffaellig"] is False

    def test_deutlich_schlechter_auf_bekanntem_faellt_auf(self) -> None:
        befund = befund_ueber(_stichprobe(1.1), FALTUNGEN)
        assert befund["auffaellig"] is True
        # Mehr Fehler als Wörter: Der Stand redet weiter, statt aufzuhören.
        assert befund["ausgefranst"] == 6

    def test_ein_guter_lauf_mit_hohem_wer_faellt_nicht_auf(self) -> None:
        # Ein schwerer Korpus zieht beide Seiten hoch. Verglichen wird das
        # Verhältnis und nicht eine feste Schwelle - sonst stünde bei jedem
        # schwierigen Sprecher eine Warnung, die nichts meint.
        schwer = [{"wer": 0.55, "variante": "original"}] * 10
        assert befund_ueber(_stichprobe(0.5), schwer)["auffaellig"] is False

    def test_ohne_faltungen_wird_nicht_geurteilt(self) -> None:
        # Kein Vergleichsmaßstab, kein Urteil - eine Warnung ohne Grundlage
        # wäre schlimmer als keine.
        assert befund_ueber(_stichprobe(2.0), [])["auffaellig"] is False

    def test_verrauschte_fassungen_zaehlen_auf_keiner_seite(self) -> None:
        # Sie sind schwerer. Eine Seite mit ihnen gegen eine ohne wäre kein
        # Vergleich, sondern zwei Messungen.
        gemischt = [*FALTUNGEN, *[{"wer": 0.9, "variante": "rauschen"}] * 10]
        assert befund_ueber(_stichprobe(0.25), gemischt)["faltungen_wer_median"] == 0.23


class TestVorbehalt:
    def test_ohne_pruefung_steht_nichts_da(self) -> None:
        # Stände von vor September 2026 sind nie geprüft worden. Über sie ist
        # nichts bekannt, und nichts zu behaupten ist die richtige Auskunft.
        assert _vorbehalt({}) == ""

    def test_ein_unauffaelliger_stand_traegt_keinen_satz(self) -> None:
        assert _vorbehalt({"pruefung": befund_ueber(_stichprobe(0.2), FALTUNGEN)}) == ""

    def test_ein_auffaelliger_stand_sagt_es_in_einem_satz(self) -> None:
        satz = _vorbehalt({"pruefung": befund_ueber(_stichprobe(1.1), FALTUNGEN)})
        assert satz.startswith("Bei der Freigabe geprüft und durchgefallen")
        # Beide Zahlen darin, sonst ist der Satz eine Behauptung.
        assert "1.10" in satz and "0.23" in satz
