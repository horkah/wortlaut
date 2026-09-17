"""Welche Sprachen dieses System kennt - heute eine, und sie steht hier.

**Warum eine Datei für eine einzige Sprache.** Weil „de" vorher an
achtzehn Stellen stand: als Vorgabe einer Signatur, als Rückfallwert hinter
einem `or`, als Zeichenkette in einem Pydantic-Feld, als Filter in der
Oberfläche. Jede einzelne war richtig, solange es nur Deutsch gibt, und jede
einzelne wäre beim Hinzufügen der zweiten Sprache zu finden gewesen - von
jemandem, der weiß, dass es sie gibt. Diese Datei ist die Antwort auf die
Frage „wo muss ich suchen": hier, und sonst nirgends.

**Was eine Sprache hier ist.** Ein Kürzel, wie Whisper es versteht - `de`,
`es`, `en`. Zwei Buchstaben nach ISO 639-1, kein Gebiet dahinter: Whisper
unterscheidet `de` und nicht `de-DE` oder `de-AT`, und eine Unterscheidung,
die das Modell nicht kennt, soll hier auch nicht entstehen. Wo ein Gebiet
wirklich gebraucht wird - die Stimmen von Piper heißen `de_DE-thorsten-high` -,
trägt es der Name der Stimme und nicht die Sprache des Profils
(`wortlaut/vorlesen.py`).

**Ein Profil, eine Sprache.** Die Sprache steht am Sprecherprofil und gilt für
alles, was daran hängt: die Vorlagen, die Aufnahmen, das Feintuning, die
Bewertung, das Diktat. Wer wortlaut in zwei Sprachen braucht, bekommt zwei
Profile. Warum das so ist und was eine zweite Sprache sonst noch kostet, steht
in `docs/sprachen.md`.

**Was hier bewusst nicht steht.** Die hundert Kürzel, die Whisper annimmt.
Angenommen zu werden heißt nicht, brauchbar zu sein, und eine Liste, aus der
sich jemand eine Sprache aussucht, für die es weder Vorlagen noch eine Stimme
noch eine Oberfläche gibt, wäre ein Versprechen, das dieses System nicht hält.
Was in `UNTERSTUETZT` steht, ist durchgearbeitet; alles andere wird abgewiesen.
"""

from __future__ import annotations

DEUTSCH = "de"

# Was dieses System wirklich kann - Kürzel auf den Namen in der eigenen
# Sprache. Die Beschriftung steht hier und nicht in der Oberfläche, weil sie
# zur Sprache gehört und nicht zur Ansicht: Wer eine zweite hinzufügt, soll
# nicht daran denken müssen, sie an einer zweiten Stelle zu benennen.
ENGLISCH = "en"

UNTERSTUETZT: dict[str, str] = {
    DEUTSCH: "Deutsch",
    ENGLISCH: "English",
}

# Womit ein Profil angelegt wird, wenn niemand etwas sagt. Solange es eine
# Sprache gibt, ist das keine Wahl, sondern die einzige Möglichkeit - aber sie
# steht als Wert da und nicht als Zeichenkette im Quelltext, und das ist der
# Unterschied, auf den es beim Hinzufügen der zweiten ankommt.
VORGABE = DEUTSCH


class UnbekannteSprache(ValueError):
    """Ein Kürzel, das dieses System nicht führt.

    Eigene Klasse, damit ein Endpunkt daraus eine saubere Antwort machen kann,
    ohne jeden `ValueError` abzufangen.
    """


def normiere(kuerzel: str) -> str:
    """`de-DE`, `DE`, ` de ` → `de`.

    Nachsichtig beim Lesen: Ein Aufrufer, der ein Gebiet mitschickt, meint
    dieselbe Sprache, und ihn dafür abzuweisen hilft niemandem. Gespeichert
    wird trotzdem nur die normierte Form - sonst stünden in der Datenbank
    zwei Schreibweisen für dasselbe.
    """
    return kuerzel.strip().replace("_", "-").split("-", 1)[0].lower()


def ist_unterstuetzt(kuerzel: str) -> bool:
    return normiere(kuerzel) in UNTERSTUETZT


def pruefe(kuerzel: str) -> str:
    """Die normierte Sprache - oder `UnbekannteSprache`.

    Der Weg, auf dem eine Sprache von außen hereinkommt. Was hier durchkommt,
    darf in die Datenbank.
    """
    normiert = normiere(kuerzel)
    if normiert not in UNTERSTUETZT:
        bekannt = ", ".join(sorted(UNTERSTUETZT))
        raise UnbekannteSprache(
            f"Diese Sprache führt wortlaut nicht: {kuerzel!r}. Zur Wahl steht: {bekannt}."
        )
    return normiert


def name(kuerzel: str) -> str:
    """Der Name zur Beschriftung; unbekannt bleibt das Kürzel selbst.

    Hässlich, aber richtig - dieselbe Regel wie bei einer fremden Stimme in
    `vorlesen.py`: Lieber ein Kürzel anzeigen als einen Bestand verschweigen,
    der nun einmal da ist.
    """
    return UNTERSTUETZT.get(normiere(kuerzel), kuerzel)
