-- Schema der App „hören". Eine Datenbank je Sprecher, siehe wortlaut/corpus.py.
--
-- Zeitangaben sind ISO-8601-Text in UTC; JSON-Felder sind Text. Beides ist in
-- SQLite üblich und hält das Schema ohne Zusatzwerkzeug lesbar.

CREATE TABLE speakers (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    sprache      TEXT NOT NULL DEFAULT 'de',
    basismodell  TEXT NOT NULL,
    erstellt     TEXT NOT NULL
);

-- Woher eine Vorlage stammt: LLM-Auftrag, hochgeladener Text oder eine
-- Korrektur aus „schreiben". `parameter` hält die Erzeugungsparameter fest,
-- damit später nachvollziehbar ist, wie ein Text zustande kam.
CREATE TABLE text_sources (
    id          TEXT PRIMARY KEY,
    speaker_id  TEXT NOT NULL REFERENCES speakers(id) ON DELETE CASCADE,
    art         TEXT NOT NULL CHECK (art IN ('llm', 'upload', 'korrektur')),
    titel       TEXT NOT NULL,
    parameter   TEXT NOT NULL DEFAULT '{}',
    erstellt    TEXT NOT NULL
);

-- Eine Sprecheinheit. `position` ist über alle Quellen eines Sprechers
-- fortlaufend und bestimmt damit die Reihenfolge der Warteschlange.
CREATE TABLE prompts (
    id                  TEXT PRIMARY KEY,
    source_id           TEXT NOT NULL REFERENCES text_sources(id) ON DELETE CASCADE,
    speaker_id          TEXT NOT NULL REFERENCES speakers(id) ON DELETE CASCADE,
    position            INTEGER NOT NULL,
    text                TEXT NOT NULL,
    dauer_geschaetzt_s  REAL NOT NULL,
    erstellt            TEXT NOT NULL
);
CREATE UNIQUE INDEX prompts_reihenfolge ON prompts (speaker_id, position);

-- Eine Aufnahmesitzung. Sie ist jederzeit unterbrechbar; die Position in der
-- Warteschlange ergibt sich aus den vorhandenen Aufnahmen, nicht aus einem
-- Zeiger, der veralten könnte.
CREATE TABLE sessions (
    id             TEXT PRIMARY KEY,
    speaker_id     TEXT NOT NULL REFERENCES speakers(id) ON DELETE CASCADE,
    begonnen       TEXT NOT NULL,
    zuletzt_aktiv  TEXT NOT NULL
);

-- `status = 'verworfen'` bleibt als Spur erhalten, das zugehörige Audio wird
-- aber gelöscht: verworfene Aufnahmen werden nicht gebraucht, und weniger
-- Stimmdaten sind besser als mehr.
CREATE TABLE recordings (
    id               TEXT PRIMARY KEY,
    prompt_id        TEXT NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    speaker_id       TEXT NOT NULL REFERENCES speakers(id) ON DELETE CASCADE,
    session_id       TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    blob             TEXT NOT NULL,
    dauer_s          REAL NOT NULL,
    pegel_dbfs       REAL NOT NULL,
    spitze_dbfs      REAL NOT NULL,
    clipping_anteil  REAL NOT NULL,
    stille_vorn_s    REAL NOT NULL,
    stille_hinten_s  REAL NOT NULL,
    modus            TEXT NOT NULL CHECK (modus IN ('gelesen', 'nachgesprochen', 'frei')),
    status           TEXT NOT NULL CHECK (status IN ('ok', 'verworfen')),
    hinweise         TEXT NOT NULL DEFAULT '[]',
    -- Kennung des Abschnitts aus „schreiben". Verhindert, dass die dortige
    -- Outbox beim Wiederholen dieselbe Korrektur zweimal einliefert.
    externe_id       TEXT UNIQUE,
    erstellt         TEXT NOT NULL
);
CREATE INDEX recordings_je_vorlage ON recordings (prompt_id, status);
