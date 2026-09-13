"""Typisierte Modelle zum Schema aus `migrations/`.

Die Migrationen sind die Wahrheit über das Schema; diese Klassen bilden es für
den Zugriff ab. Wer eine Spalte hinzufügt, ändert beides - eine neue
`.sql`-Datei und die passende Zeile hier.

**Zur Zeit ist hier nichts abzubilden.** Die einzige Tabelle hielt die
Aufteilung in Lernen, Steuern und Prüfen; sie ist mit dem Testdrittel
weggefallen (`002_ohne_aufteilung.sql`). Die Faltungen der Kreuzvalidierung
folgen der Reihenfolge des Korpus und stehen im Schnappschuss jedes Laufs -
gespeichert werden muss dafür nichts.

Die Datei bleibt samt der Datenbank dahinter stehen: „lernen" hat damit
weiterhin einen Ort für das, was nur „lernen" angeht, und der nächste, der
etwas zu speichern hat, muss ihn nicht erst wieder anlegen.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Basis(DeclarativeBase):
    pass
