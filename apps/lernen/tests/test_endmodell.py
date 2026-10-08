"""Der Stand, mit dem später diktiert wird - das Mittel der Faltungen.

Die Zahlen eines Laufs stammen aus seinen Faltungen. Freigegeben wird ihr
Mittel, das jede Aufnahme kennt und sich deshalb nicht bewerten lässt - wohl
aber prüfen, ob es überhaupt zuhört, statt nach dem ersten Satz
weiterzureden. Welche Faltung ins Mittel geht, entscheidet `pruefe_faltungen`.
"""

from __future__ import annotations

from apps.lernen.backend.api.modelle import _vorbehalt
from wortlaut import registry

from apps.lernen.training.bewerten import befund_ueber, freie_version

FALTUNGEN = [{"wer": 0.23}] * 10


def _stichprobe(wer: float, anzahl: int = 6) -> list[dict]:
    return [{"wer": wer}] * anzahl


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
        schwer = [{"wer": 0.55}] * 10
        assert befund_ueber(_stichprobe(0.5), schwer)["auffaellig"] is False

    def test_ausfransen_faellt_auch_ohne_vergleich_auf(self) -> None:
        """Der Fall, den der Vergleich allein nicht fängt.

        Stehen die Faltungen selbst nahe 1,0 - kleiner oder schwerer Korpus -,
        ist die anderthalbfache Schwelle unerreichbar, und jeder Stand käme
        durch. Genau so sind Femkes vier Stände durchgerutscht, die Sätze
        wiederholen. Mehr Fehler als Wörter ist aber nie in Ordnung.
        """
        aussichtslos = [{"wer": 0.95}] * 10
        gemischt = [*_stichprobe(0.2, 8), *_stichprobe(1.4, 4)]
        befund = befund_ueber(gemischt, aussichtslos)
        assert befund["grund"] == "ausgefranst"
        # Der Median bleibt niedrig - daran allein wäre nichts zu sehen.
        assert befund["wer_median"] < 1.0

    def test_eine_einzelne_missratene_aufnahme_reicht_nicht(self) -> None:
        # Ein Viertel ist die Schwelle: Platz für einen Ausreißer, nicht für
        # ein Muster.
        gemischt = [*_stichprobe(0.2, 11), *_stichprobe(1.4, 1)]
        assert befund_ueber(gemischt, FALTUNGEN)["auffaellig"] is False

    def test_der_grund_steht_dabei(self) -> None:
        # Die beiden Gründe verlangen verschiedene Antworten - der eine mehr
        # Daten, der andere ein anderes Training.
        assert befund_ueber(_stichprobe(0.2), FALTUNGEN)["grund"] == ""
        assert befund_ueber(_stichprobe(0.6), FALTUNGEN)["grund"] == "schlechter"

    def test_ohne_faltungen_wird_nur_das_ausfransen_geurteilt(self) -> None:
        # Ohne Vergleichsmaßstab gibt es kein „schlechter als" - eine Warnung
        # ohne Grundlage wäre schlimmer als keine. Das absolute Maß steht
        # trotzdem: Mehr Fehler als Wörter braucht keinen Vergleich.
        assert befund_ueber(_stichprobe(0.6), [])["auffaellig"] is False
        assert befund_ueber(_stichprobe(2.0), [])["grund"] == "ausgefranst"


class TestVorbehalt:
    def test_ohne_pruefung_steht_nichts_da(self) -> None:
        # Ohne Befund ist nichts zu behaupten.
        assert _vorbehalt({}) == ""

    def test_ein_unauffaelliger_stand_traegt_keinen_satz(self) -> None:
        assert _vorbehalt({"pruefung": befund_ueber(_stichprobe(0.2), FALTUNGEN)}) == ""

    def test_ein_auffaelliger_stand_sagt_es_in_einem_satz(self) -> None:
        satz = _vorbehalt({"pruefung": befund_ueber(_stichprobe(0.6), FALTUNGEN)})
        assert satz.startswith("Geprüft und durchgefallen")
        # Beide Zahlen darin, sonst ist der Satz eine Behauptung.
        assert "0.60" in satz and "0.23" in satz

    def test_ausfransen_bekommt_seinen_eigenen_satz(self) -> None:
        # „Durchgefallen gegen die Faltungen" wäre hier falsch: Gegen sie hat
        # der Stand bestanden. Er redet nur weiter.
        aussichtslos = [{"wer": 0.95}] * 10
        gemischt = [*_stichprobe(0.2, 8), *_stichprobe(1.4, 4)]
        satz = _vorbehalt({"pruefung": befund_ueber(gemischt, aussichtslos)})
        assert "länger als alles Gesagte" in satz
        assert "4 von 12" in satz


class TestFreieVersion:
    """Dasselbe Rezept in derselben Minute beauftragt - und kein Stand geht verloren."""

    VERSION = "20260925T2204-medium-lora-original-beides-voll-geduldig"

    def _auftrag(self, job_id: str, folge: str = "") -> dict:
        return {"sprecher_id": "spr_x", "job_id": job_id, "folge": folge}

    def _eintragen(self, tmp_path, job_id: str, version: str) -> None:
        registry.schreibe_stand(tmp_path, {"id": f"spr_x/{version}", "job_id": job_id})

    def test_freier_name_bleibt(self, tmp_path) -> None:
        assert freie_version(tmp_path, self._auftrag("job_b"), self.VERSION) == self.VERSION

    def test_derselbe_lauf_behaelt_seinen_namen(self, tmp_path) -> None:
        # Trägt ein Lauf seinen Stand noch einmal ein, bleibt der Name.
        self._eintragen(tmp_path, "job_b", self.VERSION)
        assert freie_version(tmp_path, self._auftrag("job_b", "43b"), self.VERSION) == self.VERSION

    def test_fremder_lauf_bekommt_seine_folge(self, tmp_path) -> None:
        self._eintragen(tmp_path, "job_b", self.VERSION)
        version = freie_version(tmp_path, self._auftrag("job_c", "43c"), self.VERSION)
        assert version == f"{self.VERSION}-43c"

    def test_ohne_folge_die_kennung_des_laufs(self, tmp_path) -> None:
        self._eintragen(tmp_path, "job_b", self.VERSION)
        version = freie_version(tmp_path, self._auftrag("job_c"), self.VERSION)
        assert version == f"{self.VERSION}-job_c"


def _messungen(faltung: int, wer: float, anzahl: int = 8) -> list[dict]:
    return [
        {"faltung": faltung, "wer": wer, "recording_id": f"r{faltung}_{i}"}
        for i in range(anzahl)
    ]


def _grund(zeilen: list[dict], wer_je_faltung: dict[int, float]) -> dict:
    """Die WER des Grundmodells je Aufnahme - je Faltung eine Schwierigkeit."""
    return {z["recording_id"]: wer_je_faltung[z["faltung"]] for z in zeilen}


class TestWelcheFaltungen:
    """Was ins Mittel geht (`endmodell.pruefe_faltungen`)."""

    ALLE = list(range(6))

    def _pruefe(self, zeilen: list[dict], vorhanden=None, grund=None):
        from apps.lernen.training.endmodell import pruefe_faltungen

        return pruefe_faltungen(
            zeilen, self.ALLE, set(self.ALLE if vorhanden is None else vorhanden), grund
        )

    def test_gesunde_faltungen_gehen_alle_hinein(self) -> None:
        zeilen = [z for f in self.ALLE for z in _messungen(f, 0.2 + f * 0.02)]
        behalten, ausgelassen = self._pruefe(zeilen, grund=_grund(zeilen, dict.fromkeys(self.ALLE, 0.5)))
        assert behalten == self.ALLE and ausgelassen == []

    def test_eine_ausgefranste_bleibt_draussen(self) -> None:
        # Mehr Fehler als Wörter auf einem Viertel der Originale.
        zeilen = [z for f in range(5) for z in _messungen(f, 0.2)]
        zeilen += _messungen(5, 0.2, 5) + _messungen(5, 1.3, 3)
        behalten, ausgelassen = self._pruefe(zeilen)
        assert behalten == [0, 1, 2, 3, 4]
        assert ausgelassen[0]["faltung"] == 5 and ausgelassen[0]["grund"] == "ausgefranst"

    def test_eine_einzelne_missratene_zeile_reicht_nicht(self) -> None:
        # Bei vier Messungen wäre eine schon ein Viertel.
        zeilen = [z for f in range(5) for z in _messungen(f, 0.2, 4)]
        zeilen += _messungen(5, 0.2, 3) + _messungen(5, 1.3, 1)
        assert self._pruefe(zeilen)[0] == self.ALLE

    def test_schwerere_saetze_sind_kein_ausreisser(self) -> None:
        # Faltung 5 hat die schwersten Sätze: Auch das Grundmodell liegt dort
        # dreimal so hoch. Gemessen daran ist sie wie die anderen.
        zeilen = [z for f in range(5) for z in _messungen(f, 0.1)] + _messungen(5, 0.3)
        grund = _grund(zeilen, {**dict.fromkeys(range(5), 0.4), 5: 1.2})
        assert self._pruefe(zeilen, grund=grund)[0] == self.ALLE

    def test_ein_ausreisser_gegen_das_grundmodell_bleibt_draussen(self) -> None:
        # Gleich schwere Sätze, aber Faltung 5 ist schlechter als das Grundmodell.
        zeilen = [z for f in range(5) for z in _messungen(f, 0.2)] + _messungen(5, 0.6)
        behalten, ausgelassen = self._pruefe(zeilen, grund=_grund(zeilen, dict.fromkeys(self.ALLE, 0.4)))
        assert 5 not in behalten
        assert ausgelassen[0]["grund"] == "ausreisser"
        assert ausgelassen[0]["verhaeltnis"] > 1.0

    def test_besser_als_das_grundmodell_ist_nie_ein_ausreisser(self) -> None:
        # Weit hinter den anderen, aber noch vor dem Grundmodell - kein Schaden.
        zeilen = [z for f in range(5) for z in _messungen(f, 0.05)] + _messungen(5, 0.35)
        grund = _grund(zeilen, dict.fromkeys(self.ALLE, 0.4))
        assert self._pruefe(zeilen, grund=grund)[0] == self.ALLE

    def test_ohne_grundmodell_keine_ausreisserpruefung(self) -> None:
        zeilen = [z for f in range(5) for z in _messungen(f, 0.2)] + _messungen(5, 0.6)
        assert self._pruefe(zeilen)[0] == self.ALLE

    def test_eine_abgebrochene_fehlt(self) -> None:
        zeilen = [z for f in range(5) for z in _messungen(f, 0.2)]
        behalten, ausgelassen = self._pruefe(zeilen, vorhanden=range(5))
        assert behalten == [0, 1, 2, 3, 4]
        assert ausgelassen == [
            {"faltung": 5, "grund": "abgebrochen", "wer": None, "verhaeltnis": None, "median": None}
        ]


class TestAbschlussbild:
    def test_alpha_ist_der_median_und_zurueckgenommen_nur_wenn_ueberall(self) -> None:
        from apps.lernen.training.endmodell import _abschlussbild

        faltungen = [
            {"abschluss": {"alpha": 0.1, "zurueckgenommen": False}},
            {"abschluss": {"alpha": 0.3, "zurueckgenommen": True}},
            {"abschluss": {"alpha": 0.2, "zurueckgenommen": False}},
        ]
        bild = _abschlussbild(faltungen, "interpoliert")
        assert bild["alpha"] == 0.2
        assert bild["zurueckgenommen"] is False
        assert _abschlussbild(faltungen[1:2], "interpoliert")["zurueckgenommen"] is True
