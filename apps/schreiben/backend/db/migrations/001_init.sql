-- Schema der App „schreiben". Eine Datenbank für die ganze Instanz — anders
-- als bei „hören" gibt es hier nur einen Sprecher (Grundentscheidung 7).
--
-- Zeitangaben sind ISO-8601-Text in UTC. Was hier steht, ist Arbeitsstand:
-- Bleiben soll allein, was als Korrektur an „hören" geht.

-- Eine Diktiersitzung: einmal sprechen, korrigieren, bestätigen.
CREATE TABLE sessions (
    id          TEXT PRIMARY KEY,
    status      TEXT NOT NULL CHECK (status IN ('offen', 'bestaetigt')),
    erstellt    TEXT NOT NULL,
    bestaetigt  TEXT
);

-- Ein Abschnitt ist, was Whisper als Segment geliefert hat: die Einheit zum
-- Vorlesen und zugleich die Einheit der Korrektur. `blob` wird NULL, sobald
-- die Aufnahme im Korpus von „hören" angekommen ist — zweimal braucht sie
-- niemand, und weniger Gesundheitsdaten sind besser als mehr.
CREATE TABLE segments (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    text        TEXT NOT NULL,
    blob        TEXT,
    dauer_s     REAL NOT NULL,
    -- initial = aus dem ersten Diktat, neu = einzeln nachgesprochen.
    herkunft    TEXT NOT NULL CHECK (herkunft IN ('initial', 'neu')),
    erstellt    TEXT NOT NULL
);
CREATE UNIQUE INDEX segments_reihenfolge ON segments (session_id, position);

-- Der Postausgang puffert, wenn „hören" gerade nicht erreichbar ist. Je
-- Abschnitt höchstens ein Eintrag; die Wiederholung ist gefahrlos, weil
-- „hören" den Abschnitt an seiner Kennung (`externe_id`) wiedererkennt.
CREATE TABLE outbox (
    id             TEXT PRIMARY KEY,
    segment_id     TEXT NOT NULL UNIQUE REFERENCES segments(id) ON DELETE CASCADE,
    status         TEXT NOT NULL CHECK (status IN ('offen', 'gesendet')),
    versuche       INTEGER NOT NULL DEFAULT 0,
    letzter_fehler TEXT,
    erstellt       TEXT NOT NULL,
    zuletzt        TEXT
);
CREATE INDEX outbox_offene ON outbox (status);
