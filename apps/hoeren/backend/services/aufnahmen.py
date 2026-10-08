"""Eine Aufnahme annehmen: umwandeln, vermessen, ablegen.

Jeder Weg in den Korpus geht hier durch - der Browser (`api/recordings.py`),
die Korrekturen aus „schreiben" (`api/intake.py`) und der Import
(`scripts/importieren.py`). Die Messwerte des `audio.Befund` heißen wie die
Spalten von `recordings`; `dataclasses.asdict(befund)` füllt die Zeile.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from wortlaut import audio as klang
from wortlaut import storage


def nimm_an(eingang: bytes | Path, ablage: storage.Ablage, relpfad: str) -> klang.Befund:
    """Beliebiges Format → 16 kHz mono WAV unter `relpfad`, mit seinen Messwerten.

    Erst vermessen, dann ablegen: Eine unlesbare Datei landet nie im Korpus,
    sondern als `audio.AudioFehler` beim Aufrufer.
    """
    with tempfile.TemporaryDirectory() as verzeichnis:
        if isinstance(eingang, bytes):
            roh = Path(verzeichnis) / "eingang"
            roh.write_bytes(eingang)
            eingang = roh
        wav = Path(verzeichnis) / "aufnahme.wav"
        klang.wandle_in_wav(eingang, wav)
        befund = klang.untersuche(wav)
        ablage.lege_ab(relpfad, wav)
    return befund
