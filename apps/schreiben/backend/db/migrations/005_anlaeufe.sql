-- Wie oft ein Abschnitt gesprochen wurde, bis er bestätigt war.
--
-- 1 heißt: so bestätigt, wie das erste Diktat ihn brachte; jedes einzelne
-- Nachsprechen zählt eins dazu (`api/segments.sprich_neu`). Die Zahl geht mit
-- der Korrektur an „hören" und von dort ins Manifest eines Laufs: Ein
-- unverändert bestätigter Abschnitt ist etwas anderes als einer, den die
-- Person in drei Anläufen durchgesetzt hat (`docs/trainingsverfahren.md`,
-- „Die Korrekturen").
ALTER TABLE segments ADD COLUMN anlaeufe INTEGER NOT NULL DEFAULT 1;
