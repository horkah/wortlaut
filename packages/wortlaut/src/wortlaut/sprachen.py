"""Welche Sprachen dieses System kennt - die eine Stelle dafür.

Wer eine Sprache hinzufügt, sucht hier und nirgends sonst; jede andere Stelle
liest das Profil oder `VORGABE`.

**Was eine Sprache hier ist.** Ein Kürzel nach ISO 639-1, wie Whisper es
versteht - `de`, `en`, ohne Gebiet: Whisper unterscheidet `de-DE` und `de-AT`
nicht. Wo ein Gebiet gebraucht wird, trägt es der Name der Stimme
(`de_DE-thorsten-high`, `wortlaut/vorlesen.py`).

**Ein Profil, eine Sprache.** Sie gilt für Vorlagen, Aufnahmen, Feintuning,
Bewertung und Diktat; wer zwei braucht, bekommt zwei Profile
(`docs/sprachen.md`).

**Nur, was durchgearbeitet ist.** Whisper nimmt hundert Kürzel an, aber eine
Sprache ohne Vorlagen, Stimme und Chunker-Maß wäre ein leeres Versprechen.
Was nicht in `UNTERSTUETZT` steht, wird abgewiesen.
"""

from __future__ import annotations

DEUTSCH = "de"
ENGLISCH = "en"

# Kürzel auf den Namen in der eigenen Sprache - hier und nicht in der
# Oberfläche, damit eine neue Sprache an einer Stelle benannt wird.
UNTERSTUETZT: dict[str, str] = {
    DEUTSCH: "Deutsch",
    ENGLISCH: "English",
}

# Womit ein Profil angelegt wird, wenn niemand etwas wählt.
VORGABE = DEUTSCH


class UnbekannteSprache(ValueError):
    """Ein Kürzel, das dieses System nicht führt.

    Eigene Klasse, damit ein Endpunkt daraus eine saubere Antwort machen kann,
    ohne jeden `ValueError` abzufangen.
    """


def normiere(kuerzel: str) -> str:
    """`de-DE`, `DE`, ` de ` → `de`.

    Nachsichtig beim Lesen, gespeichert wird nur die normierte Form.
    """
    return kuerzel.strip().replace("_", "-").split("-", 1)[0].lower()


def ist_unterstuetzt(kuerzel: str) -> bool:
    return normiere(kuerzel) in UNTERSTUETZT


def pruefe(kuerzel: str) -> str:
    """Die normierte Sprache - oder `UnbekannteSprache`. Der Weg von außen herein."""
    normiert = normiere(kuerzel)
    if normiert not in UNTERSTUETZT:
        bekannt = ", ".join(sorted(UNTERSTUETZT))
        raise UnbekannteSprache(
            f"Diese Sprache führt wortlaut nicht: {kuerzel!r}. Zur Wahl steht: {bekannt}."
        )
    return normiert


def name(kuerzel: str) -> str:
    """Der Name zur Beschriftung; unbekannt bleibt das Kürzel selbst - lieber
    ein Kürzel als ein verschwiegener Bestand."""
    return UNTERSTUETZT.get(normiere(kuerzel), kuerzel)
