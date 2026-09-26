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
from wortlaut import registry

from apps.lernen.training.bewerten import befund_ueber, freie_version

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

    def test_ausfransen_faellt_auch_ohne_vergleich_auf(self) -> None:
        """Der Fall, den der Vergleich allein nicht fängt.

        Stehen die Faltungen selbst nahe 1,0 - kleiner oder schwerer Korpus -,
        ist die anderthalbfache Schwelle unerreichbar, und jeder Stand käme
        durch. Genau so sind Femkes vier Stände durchgerutscht, die Sätze
        wiederholen. Mehr Fehler als Wörter ist aber nie in Ordnung.
        """
        aussichtslos = [{"wer": 0.95, "variante": "original"}] * 10
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
        satz = _vorbehalt({"pruefung": befund_ueber(_stichprobe(0.6), FALTUNGEN)})
        assert satz.startswith("Geprüft und durchgefallen")
        # Beide Zahlen darin, sonst ist der Satz eine Behauptung.
        assert "0.60" in satz and "0.23" in satz

    def test_ausfransen_bekommt_seinen_eigenen_satz(self) -> None:
        # „Durchgefallen gegen die Faltungen" wäre hier falsch: Gegen sie hat
        # der Stand bestanden. Er redet nur weiter.
        aussichtslos = [{"wer": 0.95, "variante": "original"}] * 10
        gemischt = [*_stichprobe(0.2, 8), *_stichprobe(1.4, 4)]
        satz = _vorbehalt({"pruefung": befund_ueber(gemischt, aussichtslos)})
        assert "länger als alles Gesagte" in satz
        assert "4 von 12" in satz


class TestPlanZurueckgelesen:
    """Der Plan der Faltungen steht nicht im Manifest - aber im Fortschritt.

    Ein Stand von vor September 2026 trägt unter `kreuzvalidierung` nur die
    Durchgangszahl. Den Horizont, über den die Lernrate lief, hat aber jede
    Faltung beim Start gemeldet. Ohne ihn ließe sich ein altes Endmodell nicht
    mit dem heutigen Verfahren nachziehen.
    """

    def _lauf(self, tmp_path, *zeilen: dict):
        from wortlaut import laeufe

        for zeile in zeilen:
            laeufe.haenge_an(tmp_path / laeufe.FORTSCHRITT, zeile)
        return tmp_path

    def test_die_erste_startmeldung_zaehlt(self, tmp_path) -> None:
        from apps.lernen.training.nachziehen import plan_aus_dem_lauf

        # Alle sechs Faltungen planen gleich; sie hören nur verschieden früh auf.
        lauf = self._lauf(
            tmp_path,
            {"art": "stufe", "name": "vorbereiten"},
            {"art": "start", "epochen": 8.0, "schritte_gesamt": 300},
            {"art": "schritt", "epoche": 1.0},
            {"art": "start", "epochen": 8.0, "schritte_gesamt": 300},
        )
        assert plan_aus_dem_lauf(lauf) == 8.0

    def test_ohne_startmeldung_wird_nichts_behauptet(self, tmp_path) -> None:
        from apps.lernen.training.nachziehen import plan_aus_dem_lauf

        # Null heißt „nicht zu ermitteln" - dann bleibt es beim alten
        # Verhalten, und das ist ehrlicher als ein geratener Horizont.
        assert plan_aus_dem_lauf(self._lauf(tmp_path, {"art": "schritt"})) == 0.0

    def test_ein_fehlender_lauf_ist_kein_fehler(self, tmp_path) -> None:
        from apps.lernen.training.nachziehen import plan_aus_dem_lauf

        assert plan_aus_dem_lauf(tmp_path / "gibtesnicht") == 0.0


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
        # So rechnet `nachziehen` einen Stand an seinem Platz neu.
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
