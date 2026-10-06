-- Spalten, die `019_zuschnitt_ueberschreibt.sql` wieder entfernt. Die Datei
-- bleibt, weil jede Datenbank sie in `schema_migrations` als gelaufen führt.
ALTER TABLE recordings ADD COLUMN zuschnitt_start_s REAL;
ALTER TABLE recordings ADD COLUMN zuschnitt_ende_s REAL;
