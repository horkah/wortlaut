-- Wann eine Aufnahme zuletzt in „Editieren" gespeichert wurde. Leer: nie.
-- `erstellt` bleibt das Datum der Aufnahme, auch bei ihren Teilen.
ALTER TABLE recordings ADD COLUMN geaendert TEXT;
