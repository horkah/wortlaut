-- Die Faltung jedes Stamms, vergeben mit seiner ersten Aufnahme
-- (`services/faltungen.py`). Was schon im Korpus liegt, bekommt keine Zeile
-- und bleibt in der Faltung nach dem Hash seines Stamms.
CREATE TABLE faltungen (
    stamm   TEXT PRIMARY KEY,
    faltung INTEGER NOT NULL,
    erstellt TEXT NOT NULL
);
