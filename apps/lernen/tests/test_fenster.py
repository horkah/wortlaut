"""Wie lang das gekürzte Encoder-Fenster wird (`training/fenster.py`)."""

from __future__ import annotations

from wortlaut import laeufe

from apps.lernen.training import fenster

REZEPT = {"fenster_zuschlag_s": 1.0, "augmentierung": {"tempo_faktor": [0.9, 1.1]}}


def _zeilen(*dauern: float) -> list[dict]:
    return [{"dauer_s": dauer} for dauer in dauern]


def test_die_laengste_aufnahme_samt_zuschlag_auf_ganze_sekunden() -> None:
    assert fenster.rahmen_fuer(_zeilen(3.2, 4.5), 1.0, REZEPT, laeufe.AUG_KEINE) == 600


def test_vorgespult_wird_es_kuerzer() -> None:
    # 8 s bei doppeltem Tempo sind 4 s, dazu der Zuschlag.
    assert fenster.rahmen_fuer(_zeilen(8.0), 2.0, REZEPT, laeufe.AUG_KEINE) == 500


def test_die_tempo_abwandlung_macht_es_laenger() -> None:
    # Bei 0,9facher Geschwindigkeit werden 4,5 s zu 5 s.
    assert fenster.rahmen_fuer(_zeilen(4.5), 1.0, REZEPT, laeufe.AUG_VOLL) == 600
    assert fenster.rahmen_fuer(_zeilen(4.5), 1.0, REZEPT, laeufe.AUG_UMGEBUNG) == 600
    assert fenster.rahmen_fuer(_zeilen(4.6), 1.0, REZEPT, laeufe.AUG_VOLL) == 700


def test_nie_mehr_als_30_sekunden() -> None:
    assert fenster.rahmen_fuer(_zeilen(42.0), 1.0, REZEPT, laeufe.AUG_KEINE) == fenster.VOLL


def test_ohne_dauer_bleibt_es_voll() -> None:
    # Sonst schnitte das Fenster womöglich Sprache ab, und der Text stimmte nicht mehr.
    zeilen = [*_zeilen(3.0), {"audio": "ohne.wav"}]
    assert fenster.rahmen_fuer(zeilen, 1.0, REZEPT, laeufe.AUG_KEINE) == fenster.VOLL


def test_ohne_zeilen_voll() -> None:
    assert fenster.rahmen_fuer([], 1.0, REZEPT, laeufe.AUG_KEINE) == fenster.VOLL
