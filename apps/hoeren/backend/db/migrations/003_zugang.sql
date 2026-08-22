-- Der Zugang zu einem Sprecher — zugleich seine Kennung.
--
-- Bisher nannte jede Anfrage ihren Sprecher als Abfrageparameter. Das war eine
-- Behauptung: Wer den Token hatte, konnte jede Kennung hinschreiben, auch
-- versehentlich aus einem alten Reiter oder einem falschen Lesezeichen — und
-- dann landeten Aufnahmen im fremden Korpus. Ab hier legt der Aufrufer einen
-- Zugang vor, der seine Kennung trägt, und der Server leitet sie daraus ab.
--
-- Gespeichert wird nur der Prüfwert, nie das Geheimnis selbst: Ein verlorener
-- Zugang lässt sich deshalb nicht wieder anzeigen, sondern nur ersetzen — und
-- genau das ist der Rückzug. NULL heißt: kein Zugang, niemand kommt herein.
ALTER TABLE speakers ADD COLUMN zugang_hash TEXT;

-- Wann der geltende Zugang ausgegeben wurde. Nicht für die Prüfung, sondern
-- für die Auskunft: Wer einen Zugang ersetzt, will hinterher sehen, dass der
-- alte weg ist.
ALTER TABLE speakers ADD COLUMN zugang_erneuert TEXT;
