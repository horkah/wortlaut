-- Wer eine Aufnahme verwirft, verwirft auch, was ein Modell daraus gemacht hat.
--
-- Verwerfen löscht das Audio (`api/recordings.py`): Eine weggeworfene Aufnahme
-- ist kein Prüfstück, sondern ein Fehlversuch, und weniger Gesundheitsdaten
-- sind besser als mehr. Die Messzeilen dazu blieben trotzdem stehen - samt dem
-- erkannten Text, also derselben Äußerung in Schrift.
--
-- Sichtbar wurde es an einer Zahl, die es nicht geben darf: „gerechnet" zählte
-- diese Zeilen mit, „gesamt" zählte die Aufnahme nicht mehr, und der Balken
-- stand über 100 %.
--
-- Von hier an räumt das Verwerfen selbst auf, und gezählt wird ohnehin nur,
-- was gilt. Dies ist der eine Rückstand, den beides nicht mehr erreicht.
DELETE FROM erkennungen
WHERE recording_id NOT IN (SELECT id FROM recordings WHERE status = 'ok');
