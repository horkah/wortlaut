-- Was in einer Aufnahme wirklich gesagt wurde. Leer: der Text der Vorlage.
-- „Editieren" schreibt immer hierher, die Vorlage bleibt unberührt - bei einer
-- Korrektur aus „schreiben" steht dort weiter, was das Modell schrieb.
ALTER TABLE recordings ADD COLUMN text TEXT;

-- Ob ein Mensch den Text einer Korrektur geprüft hat (`api/zuschnitt.speichern`).
-- Eine geprüfte Korrektur zählt in Training und Messung wie eine Vorlage.
ALTER TABLE recordings ADD COLUMN validiert INTEGER NOT NULL DEFAULT 0;
