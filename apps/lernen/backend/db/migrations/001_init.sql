-- Was „lernen" sich merken muss, und warum es so wenig ist.
--
-- Der Korpus gehört „hören" (Grundentscheidung 6), die Modellstände sind
-- Verzeichnisse (`wortlaut/registry.py`), und ein Trainingslauf ist ebenfalls
-- ein Verzeichnis (`wortlaut/laeufe.py`) - der Trainer läuft in einem anderen
-- Container und schreibt dorthin, wo beide hinsehen können. Eine Jobtabelle
-- daneben wäre eine zweite Wahrheit über denselben Lauf, und irgendwann eine
-- Zeile, die „läuft" sagt, während längst nichts mehr läuft.
--
-- Übrig bleibt genau eine Sache, die nirgends sonst stehen kann: die
-- Aufteilung.
CREATE TABLE aufteilung (
    -- Die Aufnahme aus dem Korpus. Kein Fremdschlüssel: Sie steht in einer
    -- anderen Datenbank, und das ist Absicht - „lernen" liest den Korpus, es
    -- schreibt ihn nicht.
    recording_id  TEXT PRIMARY KEY,
    -- train | validierung | test (siehe `wortlaut/laeufe.py`).
    teil          TEXT NOT NULL,
    -- Die wievielte je zugeteilte Aufnahme dieses Sprechers - der Platz im
    -- Muster. Sie steht hier, damit die Zuteilung nachvollziehbar bleibt:
    -- Ohne sie ließe sich später nicht mehr prüfen, ob das Muster eingehalten
    -- wurde, und ein Fehler darin fiele erst am Ergebnis auf.
    nummer        INTEGER NOT NULL,
    zugeteilt     TEXT NOT NULL
);

-- Zugeteilt wird in der Reihenfolge des Korpus, und jede Nummer kommt genau
-- einmal vor. Der Index ist zugleich die Abfrage, mit der die nächste Nummer
-- gefunden wird.
CREATE UNIQUE INDEX aufteilung_je_nummer ON aufteilung (nummer);
