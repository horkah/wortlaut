"""Wo der LoRA-Zusatz sitzt und wie groß er ist - aus Rezept und Auftrag.

Rang und Ziele sind Achsen des Auftrags (`laeufe.LORA_ZIELE`,
`laeufe.LORA_RAENGE`), Ausfall und das Verhältnis α/r stehen im Rezept. α
wächst mit dem Rang: Bei festem α hieße ein kleinerer Rang zugleich eine
größere wirksame Lernrate, und der Vergleich der Ränge mäße beides.

Ohne torch, damit Bestellung, Steckbrief und Tests es lesen können.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from wortlaut import laeufe

# Die Projektionen je Wahl (`laeufe.LORA_MODULE`); im Decoder tragen Selbst-
# und Kreuzaufmerksamkeit dieselben Namen.
BEIDE = ("encoder", "decoder")
ZIELE = laeufe.LORA_MODULE

# α je Rang und Ausfall, wenn das Rezept nichts sagt.
ALPHA_JE_RANG = 2.0
AUSFALL = 0.05


@dataclass(frozen=True)
class Adapter:
    rang: int
    alpha: int
    ausfall: float
    # Die Projektionen, an denen ein Zusatz hängt.
    module: tuple[str, ...]
    # Wo: `encoder`, `decoder` oder beides.
    teile: tuple[str, ...]

    @property
    def muster(self) -> list[str] | str:
        """`target_modules` für peft: die Namen, oder ein Muster auf einen Teil.

        Ein Muster gilt bei peft für den ganzen Namen (`re.fullmatch`), etwa
        `model.decoder.layers.3.encoder_attn.k_proj`.
        """
        if set(self.teile) == set(BEIDE):
            return list(self.module)
        return (
            rf"(.*\.)?({'|'.join(self.teile)})\.layers\.\d+\.(.*\.)?"
            rf"({'|'.join(self.module)})"
        )

    def als_dict(self) -> dict[str, Any]:
        return {
            "lora_rang": self.rang,
            "lora_alpha": self.alpha,
            "lora_ausfall": self.ausfall,
            "lora_ziele": list(self.module),
            "lora_teile": list(self.teile),
        }


def pruefe(auftrag: dict[str, Any]) -> None:
    """Rang und Ziele nur bei LoRA und nur aus der Wahl - sonst sofort ein Fehler."""
    ziele = laeufe.lora_ziele_aus(auftrag)
    rang = laeufe.lora_rang_aus(auftrag)
    if ziele not in laeufe.LORA_ZIELE:
        raise RuntimeError(
            f"Unbekannte LoRA-Ziele: {ziele}. Zur Wahl: {', '.join(laeufe.LORA_ZIELE)}."
        )
    if rang not in laeufe.LORA_RAENGE:
        raise RuntimeError(
            f"Unbekannter LoRA-Rang: {rang}. Zur Wahl: {', '.join(laeufe.LORA_RAENGE)}."
        )
    abweichend = ziele != laeufe.ZIELE_QV or rang != laeufe.RANG_VORGABE
    if abweichend and str(auftrag.get("methode")) != laeufe.LORA:
        raise RuntimeError("LoRA-Ziele und -Rang gibt es nur mit LoRA.")


def adapter_fuer(rezept: dict[str, Any], auftrag: dict[str, Any]) -> Adapter:
    """Der Zusatz, den dieser Auftrag bekommt."""
    pruefe(auftrag)
    einstellung = rezept.get("lora") or {}
    rang = int(laeufe.lora_rang_aus(auftrag))
    module, teile = ZIELE[laeufe.lora_ziele_aus(auftrag)]
    return Adapter(
        rang=rang,
        alpha=round(rang * float(einstellung.get("alpha_je_rang", ALPHA_JE_RANG))),
        ausfall=float(einstellung.get("ausfall", AUSFALL)),
        module=module,
        teile=teile,
    )
