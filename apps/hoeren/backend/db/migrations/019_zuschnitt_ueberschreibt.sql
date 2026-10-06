-- Ein Zuschnitt überschreibt die Aufnahme (`services/zuschnitt.py`): Die
-- Datei unter `blob` ist die gekürzte, und die Zeile beschreibt sie. Grenzen
-- und eine zweite Datei daneben gibt es nicht.
ALTER TABLE recordings DROP COLUMN zuschnitt_start_s;
ALTER TABLE recordings DROP COLUMN zuschnitt_ende_s;
