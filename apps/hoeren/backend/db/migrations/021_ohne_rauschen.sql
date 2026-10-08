-- Gemessen wird nur noch die Aufnahme selbst: Die Messungen der Kopien mit
-- Rauschen gehen, und mit ihnen die Spalte, die beide unterschied.
DELETE FROM erkennungen WHERE variante <> 'original';

DROP INDEX IF EXISTS erkennungen_je_aufnahme_modell_und_variante;
ALTER TABLE erkennungen DROP COLUMN variante;

CREATE UNIQUE INDEX erkennungen_je_aufnahme_und_modell
    ON erkennungen (recording_id, modell);
