-- Womit dieser Sprecher gerade diktiert.
--
-- Bisher stand das in der Umgebung: `WORTLAUT_MODELL_REF`, für alle gleich,
-- änderbar nur mit einem Neustart. Das war richtig, solange es je Sprecher
-- höchstens einen trainierten Stand gab - dann ist die Wahl keine.
--
-- Inzwischen gibt es vier: „lernen" trainiert zwei Methoden mal zwei
-- Datensätze (siehe `wortlaut/laeufe.py`), und daneben stehen die
-- unveränderten Grundmodelle, gegen die in „hören" schon gemessen wurde. Die
-- Frage, welcher davon dieser Person am besten zuhört, beantwortet keine
-- Kennzahl allein - sie beantwortet sich beim Diktieren. Dafür muss man
-- wechseln können, ohne einen Container neu zu starten.
--
-- Was dabei **nicht** aufgegeben wird: Zu jeder Ausgabe muss feststehen, welches
-- Modell sie erzeugt hat. Die Kopfzeile nennt es deshalb weiterhin dauerhaft,
-- und zwar jetzt mit Methode und Datensatz - vier Stände mit demselben Datum
-- wären sonst nicht auseinanderzuhalten.
CREATE TABLE modellwahl (
    -- Genau eine Zeile je Datenbank, und je Sprecher gibt es eine Datenbank.
    -- Der feste Schlüssel macht das Ersetzen zu einem `INSERT OR REPLACE` und
    -- erspart die Frage, welche von zwei Zeilen gilt.
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    -- Was geladen wird. Entweder ein Grundmodell (`base`, `small`, `medium`,
    -- `large-v3`) oder ein Stand aus der Registry in der Form
    -- `<sprecher_id>/<version>`. Der Schrägstrich unterscheidet beides - ein
    -- Whisper-Modellname enthält keinen.
    ref       TEXT NOT NULL,
    gewaehlt  TEXT NOT NULL
);
