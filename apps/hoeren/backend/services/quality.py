"""Serverseitige Prüfung: Pegel, Clipping, Randstille, Dauerplausibilität.

Wichtig ist, was diese Datei *nicht* tut: Sie lehnt nichts ab. Bei
Sprechstörungen sind Ausreißer normal — ungewöhnlich langsam, ungewöhnlich
leise, mit langen Pausen. Wer das wegautomatisiert, wirft genau die Daten weg,
für die das Projekt existiert. Es entstehen Hinweise, mehr nicht; die
Entscheidung trifft der Mensch vor dem Mikrofon.
"""

from __future__ import annotations

from wortlaut.audio import Befund

# Alle Grenzen sind absichtlich weit gesetzt.
PEGEL_LEISE_DBFS = -35.0
PEGEL_LAUT_DBFS = -6.0
CLIPPING_ANTEIL = 0.001  # ein Tausendstel der Abtastwerte am Anschlag
STILLE_S = 1.5
DAUER_FAKTOR_KURZ = 0.4  # weniger als 40 % der geschätzten Sprechdauer
DAUER_FAKTOR_LANG = 3.0


def pruefe(befund: Befund, dauer_erwartet_s: float) -> list[str]:
    """Gibt lesbare Hinweise zurück — leere Liste heißt: nichts aufgefallen."""
    hinweise: list[str] = []

    if befund.pegel_dbfs < PEGEL_LEISE_DBFS:
        hinweise.append("Sehr leise — näher ans Mikrofon oder Eingangspegel erhöhen.")
    elif befund.pegel_dbfs > PEGEL_LAUT_DBFS:
        hinweise.append("Sehr laut — Eingangspegel senken.")

    if befund.clipping_anteil > CLIPPING_ANTEIL:
        hinweise.append("Übersteuert: Teile der Aufnahme liegen am Anschlag.")

    if befund.stille_vorn_s > STILLE_S:
        hinweise.append(f"Lange Stille am Anfang ({befund.stille_vorn_s:.1f} s).")
    if befund.stille_hinten_s > STILLE_S:
        hinweise.append(f"Lange Stille am Ende ({befund.stille_hinten_s:.1f} s).")

    # Die geschätzte Sprechdauer ist eine grobe Näherung; nur deutliche
    # Abweichungen sind ein Hinweis wert.
    if dauer_erwartet_s > 0:
        if befund.dauer_s < dauer_erwartet_s * DAUER_FAKTOR_KURZ:
            hinweise.append("Deutlich kürzer als erwartet — wurde alles gesprochen?")
        elif befund.dauer_s > dauer_erwartet_s * DAUER_FAKTOR_LANG:
            hinweise.append("Deutlich länger als erwartet — Aufnahme läuft womöglich nach.")

    return hinweise
