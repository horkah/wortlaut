"""wortlaut — geteilte Bausteine für „hören", „lernen" und „schreiben".

Die Bibliothek enthält nur Fachlogik ohne Web- oder Datenbankrahmen und liest
selbst niemals Umgebungsvariablen: alle Pfade und Schlüssel werden ihr von der
jeweiligen App übergeben (siehe deren `config.py`). Dadurch ist sie ohne
Aufbau einer Umgebung benutz- und prüfbar.
"""

__all__ = ["audio", "corpus", "db", "ids", "registry", "storage", "text", "whisper"]
