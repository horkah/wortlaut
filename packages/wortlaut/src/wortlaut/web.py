"""Das gebaute Frontend ausliefern — mit Ansage, was der Browser behalten darf.

Starlettes `StaticFiles` schickt `ETag` und `Last-Modified`, aber kein
`Cache-Control`. Ohne das darf ein Browser selbst schätzen, wie lange eine
Antwort frisch bleibt (die übliche Faustregel: ein Zehntel des Alters seit
`Last-Modified`) — und er fragt in dieser Zeit gar nicht erst nach. Für die
`index.html` einer Single-Page-App ist das der Unterschied zwischen „neu
ausgerollt" und „sieht weiter die alte App": Sie ist die einzige Datei, die
auf die Namen der Bündel zeigt, und ihr eigener Name ändert sich nie.

Deshalb zwei Regeln statt keiner:

* Alles unter `assets/` trägt einen Inhalts-Hash im Namen (Vite vergibt ihn).
  Ändert sich der Inhalt, ändert sich der Name — solche Dateien darf der
  Browser für immer behalten.
* Alles andere, allen voran die `index.html`, bekommt `no-cache`. Das heißt
  nicht „nicht speichern", sondern „vor jeder Benutzung nachfragen"; dank
  `ETag` ist das im Normalfall ein 304 ohne Rumpf.
"""

from __future__ import annotations

from typing import Any

from starlette.responses import Response
from starlette.staticfiles import StaticFiles

# Ein Jahr ist die übliche Obergrenze; `immutable` erspart auch das Nachfragen
# beim Neuladen der Seite.
UNVERAENDERLICH = "public, max-age=31536000, immutable"
IMMER_NACHFRAGEN = "no-cache"


class FrontendDateien(StaticFiles):
    """`StaticFiles`, das gehashte Bündel und die `index.html` unterscheidet."""

    async def get_response(self, path: str, scope: Any) -> Response:
        antwort = await super().get_response(path, scope)
        # Nur erfolgreiche Antworten festschreiben: Ein 404 auf einen
        # Bündelnamen wäre sonst ein Jahr lang zwischengespeichert.
        gehasht = path.startswith("assets/") and antwort.status_code == 200
        antwort.headers["Cache-Control"] = UNVERAENDERLICH if gehasht else IMMER_NACHFRAGEN
        return antwort
