-- Was verschiedene Modelle aus denselben Aufnahmen gemacht haben.
--
-- Der Korpus hält bisher fest, was gesprochen wurde. Diese Tabelle hält fest,
-- was ein Erkenner daraus gemacht hat - je Aufnahme und Modell eine Zeile mit
-- dem erkannten Text und den Maßen gegen die Vorlage
-- (`wortlaut/metriken.py`). Damit ist die Auswertung wiederholbar, ohne
-- dieselben Stunden Rechenzeit noch einmal auszugeben, und der Vergleich
-- zwischen Modellen ist eine Abfrage statt eines zweiten Laufs.
--
-- Sie gehört in den Korpus und nicht daneben: Die Zeilen hängen an genau
-- dieser Aufnahme dieses Sprechers, und wer den Sprecher löscht, löscht sie
-- mit (Grundentscheidung 6 und `scripts/purge_speaker.py` - ein Verzeichnis
-- weniger, nicht ein vergessener Filter).
--
-- Die Maße stehen als eigene Spalten und nicht als JSON: Sie werden sortiert,
-- gemittelt und in eine Kurve gelegt, und das kann SQLite nur, was es auch
-- sieht. Ein Maß dazu ist eine Spalte und eine Migration - dass das selten
-- vorkommt, ist der Preis dafür, dass die Auswertung selbst billig bleibt.
CREATE TABLE erkennungen (
    id            TEXT PRIMARY KEY,
    recording_id  TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    -- Der Name des Erkenners, wie ihn faster-whisper versteht: 'tiny',
    -- 'small', 'medium' - oder später der Verweis auf einen eigenen Stand aus
    -- „lernen". Darum Text und keine feste Auswahl.
    modell        TEXT NOT NULL,
    -- Der erkannte Text, roh und unbearbeitet. Gemessen wird auf einer
    -- angeglichenen Fassung (Kleinschreibung, ohne Satzzeichen), angezeigt
    -- wird diese hier: Der Mensch soll den echten Unterschied sehen.
    text          TEXT NOT NULL,
    -- Fehlerraten, kleiner ist besser. Siehe `wortlaut/metriken.py`.
    wer           REAL NOT NULL,
    cer           REAL NOT NULL,
    mer           REAL NOT NULL,
    wil           REAL NOT NULL,
    -- Die eine Zahl darüber, 0 bis 100 - größer ist besser.
    genauigkeit   REAL NOT NULL,
    -- Wie lange das Erkennen gedauert hat. Nicht Teil der Güte, aber die
    -- andere Hälfte jeder Modellwahl: Ein Modell, das doppelt so gut ist und
    -- zwanzigmal so lange braucht, ist nicht ohne Weiteres das bessere.
    rechenzeit_s  REAL NOT NULL,
    erstellt      TEXT NOT NULL
);

-- Je Aufnahme und Modell genau eine Zeile: Der Lauf soll wiederaufnehmbar
-- sein, ohne dass ein zweiter Durchgang alles verdoppelt. Zugleich ist dieser
-- Index die Abfrage, mit der der Lauf herausfindet, was noch fehlt.
CREATE UNIQUE INDEX erkennungen_je_aufnahme_und_modell
    ON erkennungen (recording_id, modell);
