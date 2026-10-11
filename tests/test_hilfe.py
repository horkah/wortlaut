"""„Hilfe" führt an Stellen im Handbuch (`packages/ui/hilfe.ts`).

Die Tafel steht im Frontend, die Anker stehen im Markdown - zwei Dateien, die
niemand gemeinsam ändert. Fehlt ein Anker, öffnet GitHub die Seite trotzdem,
nur am Anfang; das sähe niemand. Darum hier.
"""

from __future__ import annotations

import re
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
TAFEL = WURZEL / "packages" / "ui" / "hilfe.ts"
DOCS = WURZEL / "docs"

STELLE = re.compile(r"\['([\w-]+\.md)', '(hilfe-[\w-]+)'\]")
ANKER = re.compile(r'<a id="(hilfe-[\w-]+)"></a>')


def _stellen() -> set[tuple[str, str]]:
    return set(STELLE.findall(TAFEL.read_text(encoding="utf-8")))


def _anker() -> set[tuple[str, str]]:
    return {
        (datei.name, anker)
        for datei in DOCS.glob("*.md")
        for anker in ANKER.findall(datei.read_text(encoding="utf-8"))
    }


def test_die_tafel_nennt_stellen() -> None:
    assert len(_stellen()) > 10


def test_jede_stelle_hat_ihren_anker() -> None:
    assert _stellen() - _anker() == set()


def test_jeder_anker_wird_angesprungen() -> None:
    assert _anker() - _stellen() == set()


def test_ein_anker_steht_nie_zweimal() -> None:
    gefunden = [
        anker
        for datei in DOCS.glob("*.md")
        for anker in ANKER.findall(datei.read_text(encoding="utf-8"))
    ]
    assert len(gefunden) == len(set(gefunden))
