-- Jede Aufnahme wird viermal gemessen, nicht einmal.
--
-- Bisher hielt `erkennungen` je Aufnahme und Modell eine Zeile
-- (`005_auswertung.sql`). Gemessen wurde damit genau ein Fall: diese Stimme,
-- dieses Mikrofon, dieser Pegel, dieser Raum. Ob ein Modell den Sprecher
-- versteht oder bloß diese eine Aufnahmesituation gut verträgt, war daran
-- nicht abzulesen - und das ist die Frage, auf die es ankommt.
--
-- Neben jeder Aufnahme liegen deshalb drei abgewandelte Fassungen
-- (`wortlaut/augmentierung.py`): ausgesteuert, pauschal lauter, mit
-- Grundrauschen. Jede geht durch jedes Modell, und diese Spalte sagt, welche
-- Fassung eine Zeile gemessen hat.
--
-- **Warum eine Spalte und keine zweite Tabelle.** Eine Erkennung gehört zu
-- genau einer Fassung genau einer Aufnahme; das ist eine Eigenschaft der
-- Zeile und keine eigene Sache. Eine Tabelle `varianten` daneben wäre
-- außerdem eine zweite Wahrheit darüber, welche Dateien es gibt - wo sie
-- liegen, rechnet `corpus.variante_relpfad` aus Kennung und Namen aus, und
-- die Datei selbst ist der einzige Beleg dafür, dass sie da ist.
--
-- **Warum `original` als Vorgabe.** Was vor dieser Änderung gerechnet wurde,
-- ist genau das: die unabgewandelte Aufnahme. Die vorhandenen Zeilen behalten
-- damit ihren Sinn und ihre Gültigkeit, und der nächste Lauf holt nur die drei
-- Fassungen nach, die fehlen. Nichts wird verworfen, nichts doppelt gerechnet.
ALTER TABLE erkennungen ADD COLUMN variante TEXT NOT NULL DEFAULT 'original';

-- Der alte Index ließ je Aufnahme und Modell nur eine Zeile zu - genau das,
-- was jetzt vier sein sollen. Er wird nicht gelockert, sondern um die dritte
-- Spalte erweitert: Die Eindeutigkeit ist es, worauf die Wiederaufnehmbarkeit
-- des Laufs beruht, und zugleich die Abfrage, mit der er herausfindet, was
-- noch fehlt.
DROP INDEX erkennungen_je_aufnahme_und_modell;

CREATE UNIQUE INDEX erkennungen_je_aufnahme_modell_und_variante
    ON erkennungen (recording_id, modell, variante);
