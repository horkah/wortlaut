-- Das Register der Läufe - was ein Lauf war, auch wenn sein Modell gelöscht ist.
--
-- Ein Lauf lebt in `data/snapshots/<job_id>/`, sein Modell in
-- `data/modelle/<sprecher_id>/<version>/` (`wortlaut/laeufe.py`,
-- `wortlaut/registry.py`). Beide gehen beim Löschen, und beide liegen auf der
-- Trainingsablage, die nicht gesichert wird. Hier bleibt, was es braucht, um
-- einen Lauf wissenschaftlich auszuwerten und neu zu rechnen: der Auftrag,
-- welche Daten er sah, in welcher Umgebung er lief, und alles, was sich nur mit
-- dem Modell messen ließ.
--
-- Eine Datei je Sprecher unter `data/lernen/<sprecher_id>/`, geschrieben nur
-- von „lernen" (Grundentscheidung 6), gesichert und gelöscht mit dem Sprecher
-- (`hoeren/services/loeschung.py`). Der Sprecher steht als Kennung darin, nie
-- mit Namen. Auf Aufnahmen und Vorlagen zeigt das Register mit deren Kennung -
-- zusammen mit `korpus/<sprecher_id>/hoeren.sqlite` ergibt `ATTACH` den Rest.
--
-- Eingetragen wird, wenn ein Lauf endet (`training/laeufer.py`), bevor er
-- gelöscht wird (`services/auftraege.loesche`), und mit `scripts/register.py`.
-- Ein zweites Eintragen ersetzt, was aus dem Laufverzeichnis kommt; was nur
-- hier steht, bleibt.

CREATE TABLE laeufe (
    job_id        TEXT PRIMARY KEY,
    sprecher_id   TEXT NOT NULL,
    -- Optionscode und Folge, wie „lernen" den Lauf nennt (`laeufe.titel`).
    titel         TEXT NOT NULL,
    -- `wartet`, `laeuft`, `fertig`, `abgebrochen`, `gescheitert` - beim letzten Eintragen.
    status        TEXT NOT NULL,
    erstellt      TEXT,
    begonnen      TEXT,
    beendet       TEXT,
    -- Der Stand, der daraus wurde: `<sprecher_id>/<version>` und seine
    -- Kurzkennung (`registry.kurzkennung`), wie sie in der Oberfläche steht.
    modell        TEXT,
    kennung       TEXT,
    -- Die Dateien des Laufs, wie sie waren - JSON:
    -- `auftrag`     auftrag.json: jede Achse, Grundmodell, Umfang
    -- `zustand`     zustand.json: Metriken samt Bootstrap-Intervall, Zuschnitt, Fehler
    -- `stand`       manifest.json des Modells: Rezept, Abschluss, Endmodell, Faltungen,
    --               Grundmodell daneben, Plausibilitätsprüfung
    -- `kernauswahl` kernauswahl.json, nur bei Kernauswahl
    auftrag       TEXT NOT NULL,
    zustand       TEXT,
    stand         TEXT,
    kernauswahl   TEXT,
    -- Worin gerechnet wurde: Quellstand (SHA-256 über den Code des Trainers),
    -- Python, Bibliotheken, Revision des Grundmodells, Karte. Vom Läufer am
    -- Ende des Laufs; leer bei nachgetragenen Läufen.
    umgebung      TEXT,
    -- Die rohe Ausgabe des Trainers (protokoll.txt).
    protokoll     TEXT,
    -- Wann Laufverzeichnis und Modell gelöscht wurden; leer, solange es sie gibt.
    entfernt      TEXT,
    eingetragen   TEXT NOT NULL,
    aktualisiert  TEXT NOT NULL
);

-- Worauf gelernt und gemessen wurde: je Zeile des Manifests eine. Die Faltung
-- sagt beides - gemessen wird eine Vorlage in ihrer Faltung, gelernt in den
-- übrigen (`laeufe.zeilen_fuer_faltung`).
CREATE TABLE daten (
    job_id        TEXT NOT NULL REFERENCES laeufe (job_id) ON DELETE CASCADE,
    zeile         INTEGER NOT NULL,
    recording_id  TEXT,
    -- `original` oder eine Abwandlung (`wortlaut/augmentierung.py`).
    variante      TEXT,
    faltung       INTEGER,
    gewicht       REAL,
    -- `vorlage`, `korrektur` oder `selbst` - und wie gesprochen wurde.
    quelle        TEXT,
    modus         TEXT,
    dauer_s       REAL,
    -- Der Text, auf den gelernt wurde - so, wie er damals war. Eine Vorlage
    -- lässt sich später bearbeiten, eine Aufnahme verwerfen.
    text          TEXT,
    -- Die Datei relativ zum Korpus und ihr SHA-256, gerechnet beim ersten
    -- Eintragen; leer, wenn die Datei da schon fehlte. Ob ein Neutraining
    -- dieselben Klänge sieht, sagt der Vergleich.
    audio         TEXT,
    audio_sha256  TEXT,
    -- Alle übrigen Felder der Manifestzeile, JSON.
    weitere       TEXT,
    PRIMARY KEY (job_id, zeile)
);

-- Was ein Modell aus einer Aufnahme gemacht hat - nur mit dem Modell zu rechnen.
--
-- `faltung`    aus der Kreuzvalidierung (bewertung.jsonl): das Faltungsmodell,
--              das die Aufnahme nicht gelernt hatte.
-- `endmodell`  aus der Auswertung von „hören" (`erkennungen`), übernommen beim
--              Löschen: der ausgelieferte Stand auf Aufnahmen, die er nie hörte.
CREATE TABLE messungen (
    job_id        TEXT NOT NULL REFERENCES laeufe (job_id) ON DELETE CASCADE,
    herkunft      TEXT NOT NULL,
    nummer        INTEGER NOT NULL,
    faltung       INTEGER,
    recording_id  TEXT,
    variante      TEXT,
    -- Der erkannte Text, roh.
    text          TEXT,
    wer           REAL,
    cer           REAL,
    mer           REAL,
    wil           REAL,
    genauigkeit   REAL,
    rechenzeit_s  REAL,
    rechenwerk    TEXT,
    tempo         REAL,
    weitere       TEXT,
    PRIMARY KEY (job_id, herkunft, nummer)
);

-- Der Verlauf (fortschritt.jsonl): Stufen, Verlust je Schritt, Validierung je
-- Durchgang, gescheiterte Faltungen. `daten` trägt die Felder jeder Zeile als JSON.
CREATE TABLE ereignisse (
    job_id        TEXT NOT NULL REFERENCES laeufe (job_id) ON DELETE CASCADE,
    nummer        INTEGER NOT NULL,
    zeit          TEXT,
    art           TEXT,
    daten         TEXT NOT NULL,
    PRIMARY KEY (job_id, nummer)
);

-- Ein Blick über alle Läufe, ohne JSON zu lesen.
CREATE VIEW uebersicht AS
SELECT
    l.job_id,
    l.kennung,
    l.titel,
    l.status,
    l.erstellt,
    l.beendet,
    l.entfernt,
    json_extract(l.auftrag, '$.basismodell') AS basismodell,
    json_extract(l.auftrag, '$.methode') AS methode,
    json_extract(l.auftrag, '$.daten') AS daten,
    json_extract(l.zustand, '$.metriken.wer') AS wer,
    json_extract(l.zustand, '$.metriken.cer') AS cer,
    (SELECT count(*) FROM daten d WHERE d.job_id = l.job_id) AS zeilen,
    (SELECT count(*) FROM messungen m WHERE m.job_id = l.job_id) AS messungen
FROM laeufe l;
