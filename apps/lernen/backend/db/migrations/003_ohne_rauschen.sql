-- Gelernt und gemessen wird nur noch die Aufnahme selbst: Die Zeilen der
-- Kopien mit Rauschen gehen, und mit ihnen die Spalte, die beide unterschied.
DELETE FROM daten WHERE coalesce(variante, 'original') <> 'original';
DELETE FROM messungen WHERE coalesce(variante, 'original') <> 'original';
ALTER TABLE daten DROP COLUMN variante;
ALTER TABLE messungen DROP COLUMN variante;

DROP VIEW uebersicht;
CREATE VIEW uebersicht AS
SELECT
    l.job_id,
    l.kennung,
    l.titel,
    l.datensatz,
    l.status,
    l.erstellt,
    l.beendet,
    l.entfernt,
    json_extract(l.auftrag, '$.basismodell') AS basismodell,
    json_extract(l.auftrag, '$.methode') AS methode,
    json_extract(l.zustand, '$.metriken.wer') AS wer,
    json_extract(l.zustand, '$.metriken.cer') AS cer,
    (SELECT count(*) FROM daten d WHERE d.job_id = l.job_id) AS zeilen,
    (SELECT count(*) FROM messungen m WHERE m.job_id = l.job_id) AS messungen
FROM laeufe l;
