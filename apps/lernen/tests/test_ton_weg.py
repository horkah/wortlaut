"""Ein Ton, der während der Messung verschwindet, kostet nur seine eigene Zeile.

„hören" ersetzt beim Editieren das Original und löscht seine Datei - auch
während ein Lauf läuft. Die Faltung misst dann ohne sie weiter, wie beim
Zusammenstellen (`laeufe.zeilen_fuer_faltung`).
"""

from __future__ import annotations

from pathlib import Path

from wortlaut import laeufe
from wortlaut.whisper import Transkript

from apps.lernen.training.bewerten import _miss


class Erkenner:
    marke = "test/test"

    def transkribiere(self, wav: Path, sprache: str) -> Transkript:
        return Transkript(text="ein Satz", abschnitte=[])


class Bericht:
    def __init__(self) -> None:
        self.gesagt: list[str] = []

    def sage(self, text: str) -> None:
        self.gesagt.append(text)


def test_eine_verschwundene_aufnahme_faellt_heraus(tmp_path: Path) -> None:
    korpus = tmp_path / "korpus"
    (korpus / "audio").mkdir(parents=True)
    (korpus / "audio" / "rec_da.wav").write_bytes(b"")
    zeilen = [
        {"recording_id": "rec_weg", "audio": "audio/rec_weg.wav", "text": "ein Satz"},
        {"recording_id": "rec_da", "audio": "audio/rec_da.wav", "text": "ein Satz"},
    ]
    bericht = Bericht()

    ergebnis = _miss(Erkenner(), zeilen, korpus, "de", 0, tmp_path, bericht)

    assert [zeile["recording_id"] for zeile in ergebnis] == ["rec_da"]
    assert [zeile["recording_id"] for zeile in laeufe.bewertungszeilen(tmp_path)] == ["rec_da"]
    assert any("rec_weg" in text for text in bericht.gesagt)
