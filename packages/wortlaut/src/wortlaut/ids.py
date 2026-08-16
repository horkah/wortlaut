"""Kennungen: zeitlich sortierbar, ohne Datenbanksequenz, mit lesbarem Präfix.

Aufbau wie eine ULID: 48 Bit Millisekunden seit 1970, danach 80 Bit Zufall,
zusammen in Base32 ohne die verwechselbaren Zeichen I, L, O und U. Als Text
sortiert stehen sie damit grob in Entstehungsreihenfolge — praktisch für
Verzeichnislisten.

Grob heißt: auf die Millisekunde genau. Kennungen aus derselben Millisekunde
stehen zufällig zueinander, weil der hintere Teil Zufall ist und keinen Zähler
enthält. Wo die Reihenfolge zählt, wird deshalb nach einer eigenen Spalte
sortiert (`position`, `erstellt`), nie nach der Kennung.
"""

from __future__ import annotations

import os
import time

_ZEICHEN = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # 32 Zeichen, Crockford-Base32


def neue_id(praefix: str) -> str:
    """Neue Kennung, z. B. `neue_id("rec")` → `rec_01J8Z…`."""
    rohwert = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    # 128 Bit ergeben genau 26 Base32-Zeichen (26 * 5 = 130, oben aufgefüllt).
    zeichen = [_ZEICHEN[(rohwert >> verschiebung) & 0x1F] for verschiebung in range(125, -1, -5)]
    return f"{praefix}_{''.join(zeichen)}"
