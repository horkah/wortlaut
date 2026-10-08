-- Vorgespult wird je Modellstand (`erkennungen.tempo`), nicht je Sprecher;
-- die Spalte am Profil liest niemand.
ALTER TABLE speakers DROP COLUMN tempo;
