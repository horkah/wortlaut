"""Auf einem trainierten Stand weiterlernen statt auf einem Grundmodell.

Ein Stand liegt nur als CTranslate2 vor (`ct2/model.bin`), das transformers
nicht liest; die Rohgewichte räumt der Lauf weg (`laeufe.ZWISCHENSTAENDE`) -
ein Gigabyte je Stand. Die Umwandlung ist verlustfrei umkehrbar, sie legt nur
um und fügt zusammen:

* `q_proj`, `k_proj` und `v_proj` der Selbstaufmerksamkeit stehen als eine
  Matrix übereinander (`linear_0`), die der Kreuzaufmerksamkeit als `q` für
  sich und `k`, `v` zusammen. `k_proj` hat bei Whisper keinen Bias; die
  Umwandlung setzt an seiner Stelle Nullen, und genau die werden hier geprüft.
* Schichtnormen heißen `gamma`/`beta` statt `weight`/`bias`.
* `proj_out` ist mit den Einbettungen verbunden und steht nur als Verweis da.

Die Stände sind `float16` - dieselben Zahlen, mit denen „schreiben" diktiert.

Einmal je Lauf gerechnet, im Laufverzeichnis abgelegt (`ausgang/`) und mit
den Zwischenständen weggeräumt. Format und Namenszuordnung kommen ohne numpy
und torch aus, damit sie sich ohne Trainerabbild prüfen lassen.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wortlaut import laeufe, registry

# Die Reihenfolge der Datentypen in `include/ctranslate2/types.h`.
_ARTEN = ("float32", "int8", "int16", "int32", "float16", "bfloat16")
_GLEITKOMMA = ("float32", "float16")

# Die gelesene Fassung des Dateiformats; bei einer anderen wird nicht geraten.
_FASSUNG = 6
_SPEZIFIKATION = "WhisperSpec"

# Liegt erst da, wenn alles geschrieben ist - sonst wird neu gerechnet.
_FERTIG = "model.safetensors"


@dataclass(frozen=True)
class Variable:
    """Wo in der `model.bin` eine Größe liegt - noch ohne sie zu lesen."""

    form: tuple[int, ...]
    art: str
    anfang: int
    laenge: int


@dataclass(frozen=True)
class Ausschnitt:
    """Welcher Teil einer CTranslate2-Größe ein Gewicht von transformers ist.

    `von`/`bis` zählen Zeilen der ersten Achse; `None` heißt: die ganze Größe.
    """

    name: str
    von: int | None = None
    bis: int | None = None


def lies_verzeichnis(pfad: Path) -> tuple[dict[str, Variable], dict[str, str]]:
    """Die Größen und Verweise einer `model.bin`, ohne die Zahlen selbst zu laden."""
    with pfad.open("rb") as datei:

        def zahl(format_: str) -> int:
            return struct.unpack(format_, datei.read(struct.calcsize(format_)))[0]

        def text() -> str:
            # Mit Längenangabe und abschließender Null (`model_spec._serialize`).
            return datei.read(zahl("H"))[:-1].decode("utf-8")

        fassung = zahl("I")
        spezifikation = text()
        if fassung != _FASSUNG or spezifikation != _SPEZIFIKATION:
            raise RuntimeError(
                f"{pfad}: {spezifikation} in Fassung {fassung} - erwartet war "
                f"{_SPEZIFIKATION} in Fassung {_FASSUNG}."
            )
        zahl("I")  # die Revision der Spezifikation; für die Gewichte ohne Belang

        variablen: dict[str, Variable] = {}
        for _ in range(zahl("I")):
            name = text()
            form = tuple(zahl("I") for _ in range(zahl("B")))
            art = _ARTEN[zahl("B")]
            laenge = zahl("I")
            variablen[name] = Variable(form=form, art=art, anfang=datei.tell(), laenge=laenge)
            datei.seek(laenge, 1)

        verweise = {text(): text() for _ in range(zahl("I"))}
    return variablen, verweise


def _schichten(variablen: dict[str, Variable], seite: str) -> int:
    muster = re.compile(rf"^{seite}/layer_(\d+)/")
    nummern = {int(treffer.group(1)) for name in variablen if (treffer := muster.match(name))}
    return max(nummern) + 1 if nummern else 0


def zuordnung(variablen: dict[str, Variable]) -> dict[str, Ausschnitt]:
    """Jedes Gewicht von `WhisperForConditionalGeneration` → wo es in der `model.bin` steht.

    Die Umkehrung von `WhisperLoader` in `ctranslate2/converters/transformers.py`.
    """
    breite = variablen["encoder/layer_0/self_attention/linear_1/weight"].form[0]
    karte: dict[str, Ausschnitt] = {}

    def linear(hf: str, ct2: str, von: int | None = None, bis: int | None = None) -> None:
        karte[f"{hf}.weight"] = Ausschnitt(f"{ct2}/weight", von, bis)
        karte[f"{hf}.bias"] = Ausschnitt(f"{ct2}/bias", von, bis)

    def norm(hf: str, ct2: str) -> None:
        karte[f"{hf}.weight"] = Ausschnitt(f"{ct2}/gamma")
        karte[f"{hf}.bias"] = Ausschnitt(f"{ct2}/beta")

    def selbst(hf: str, ct2: str) -> None:
        linear(f"{hf}.q_proj", f"{ct2}/linear_0", 0, breite)
        # `k_proj` ohne Bias - die Nullen an seiner Stelle prüft `pruefe_nullen`.
        karte[f"{hf}.k_proj.weight"] = Ausschnitt(f"{ct2}/linear_0/weight", breite, 2 * breite)
        linear(f"{hf}.v_proj", f"{ct2}/linear_0", 2 * breite, 3 * breite)
        linear(f"{hf}.out_proj", f"{ct2}/linear_1")

    def ffn(hf: str, ct2: str) -> None:
        linear(f"{hf}.fc1", f"{ct2}/ffn/linear_0")
        linear(f"{hf}.fc2", f"{ct2}/ffn/linear_1")
        norm(f"{hf}.final_layer_norm", f"{ct2}/ffn/layer_norm")

    for seite in ("encoder", "decoder"):
        hf = f"model.{seite}"
        karte[f"{hf}.embed_positions.weight"] = Ausschnitt(f"{seite}/position_encodings/encodings")
        norm(f"{hf}.layer_norm", f"{seite}/layer_norm")
        for nummer in range(_schichten(variablen, seite)):
            schicht, ct2 = f"{hf}.layers.{nummer}", f"{seite}/layer_{nummer}"
            selbst(f"{schicht}.self_attn", f"{ct2}/self_attention")
            norm(f"{schicht}.self_attn_layer_norm", f"{ct2}/self_attention/layer_norm")
            ffn(schicht, ct2)
            if seite == "decoder":
                quer = f"{schicht}.encoder_attn"
                linear(f"{quer}.q_proj", f"{ct2}/attention/linear_0")
                karte[f"{quer}.k_proj.weight"] = Ausschnitt(
                    f"{ct2}/attention/linear_1/weight", 0, breite
                )
                linear(f"{quer}.v_proj", f"{ct2}/attention/linear_1", breite, 2 * breite)
                linear(f"{quer}.out_proj", f"{ct2}/attention/linear_2")
                norm(f"{schicht}.encoder_attn_layer_norm", f"{ct2}/attention/layer_norm")

    for faltung in ("conv1", "conv2"):
        linear(f"model.encoder.{faltung}", f"encoder/{faltung}")
    karte["model.decoder.embed_tokens.weight"] = Ausschnitt("decoder/embeddings/weight")
    karte["proj_out.weight"] = Ausschnitt("decoder/projection/weight")
    return karte


def nullen(variablen: dict[str, Variable]) -> list[Ausschnitt]:
    """Wo die Umwandlung für den fehlenden Bias von `k_proj` Nullen eingesetzt hat."""
    breite = variablen["encoder/layer_0/self_attention/linear_1/weight"].form[0]
    stellen = []
    for seite in ("encoder", "decoder"):
        for nummer in range(_schichten(variablen, seite)):
            ct2 = f"{seite}/layer_{nummer}"
            stellen.append(Ausschnitt(f"{ct2}/self_attention/linear_0/bias", breite, 2 * breite))
            if seite == "decoder":
                stellen.append(Ausschnitt(f"{ct2}/attention/linear_1/bias", 0, breite))
    return stellen


def uebrig(variablen: dict[str, Variable], verweise: dict[str, str], karte: dict[str, Ausschnitt]) -> set[str]:
    """Gewichte der `model.bin`, die in keinem Gewicht von transformers ankommen.

    Leer muss es sein. Ist es das nicht, hat CTranslate2 etwas dazugelernt, das
    diese Zuordnung nicht kennt - und ein Modell, dem ein Teil fehlt, soll
    nicht still auf dem Grundmodell weiterlaufen.
    """
    benutzt = {verweise.get(ausschnitt.name, ausschnitt.name) for ausschnitt in karte.values()}
    return {
        name
        for name, variable in variablen.items()
        if variable.art in _GLEITKOMMA and variable.form and name not in benutzt
    }


def lade_in(modell: Any, model_bin: Path) -> None:
    """Die Gewichte aus `model_bin` in ein schon gebautes Whisper-Modell kopieren."""
    import numpy as np
    import torch

    variablen, verweise = lies_verzeichnis(model_bin)
    karte = zuordnung(variablen)
    rest = uebrig(variablen, verweise, karte)
    if rest:
        raise RuntimeError(f"Nicht zugeordnet: {', '.join(sorted(rest))}")

    speicher = np.memmap(model_bin, dtype=np.uint8, mode="r")

    def zahlen(ausschnitt: Ausschnitt) -> Any:
        variable = variablen[verweise.get(ausschnitt.name, ausschnitt.name)]
        roh = speicher[variable.anfang : variable.anfang + variable.laenge]
        feld = roh.view(np.dtype(variable.art)).reshape(variable.form)
        return feld if ausschnitt.von is None else feld[ausschnitt.von : ausschnitt.bis]

    for stelle in nullen(variablen):
        if np.any(zahlen(stelle)):
            raise RuntimeError(f"{stelle.name}: Hier standen Nullen erwartet, die Zuordnung stimmt nicht.")

    zustand = modell.state_dict()
    fehlend = sorted(set(zustand) - set(karte))
    if fehlend:
        raise RuntimeError(f"Ohne Quelle in der model.bin: {', '.join(fehlend)}")
    with torch.no_grad():
        for name, ziel in zustand.items():
            # Eine Kopie und keine Sicht: Die Sicht in die `memmap` ist nur
            # lesbar, und torch warnt bei jeder solchen.
            quelle = torch.from_numpy(np.array(zahlen(karte[name])))
            if tuple(quelle.shape) != tuple(ziel.shape):
                raise RuntimeError(
                    f"{name}: Form {tuple(quelle.shape)} in der model.bin, "
                    f"{tuple(ziel.shape)} im Modell."
                )
            ziel.copy_(quelle)


def quelle(verzeichnis: Path, datenverzeichnis: Path, auftrag: dict[str, Any], bericht: Any) -> str:
    """Woraus die Gewichte dieses Laufs kommen: ein Name für `from_pretrained`.

    Ohne Ausgangsstand das Grundmodell selbst. Mit einem das Verzeichnis
    `ausgang/` dieses Laufs - beim ersten Aufruf zurückgerechnet, danach nur
    noch genannt.
    """
    basismodell = str(auftrag["basismodell"])
    ref = str(auftrag.get(laeufe.AUSGANGSSTAND) or "")
    if not ref:
        return basismodell

    ziel = verzeichnis / laeufe.AUSGANG
    if (ziel / _FERTIG).is_file():
        return str(ziel)

    import torch
    from transformers import WhisperForConditionalGeneration

    model_bin = registry.ct2_verzeichnis(datenverzeichnis, ref) / "model.bin"
    if not model_bin.is_file():
        raise RuntimeError(f"Ausgangsstand {registry.beschriftung(ref)} liegt nicht mehr da: {model_bin}")
    bericht.sage(f"Ausgangsstand {registry.beschriftung(ref)}: Gewichte aus CTranslate2 zurückrechnen")
    # Das Gerüst vom Grundmodell - Aufbau, `generation_config`, Einbettungen
    # für die Zeitmarken -, die Zahlen darin alle vom Stand.
    modell = WhisperForConditionalGeneration.from_pretrained(basismodell)
    lade_in(modell, model_bin)
    # Halbe Genauigkeit - genauer waren die Zahlen nie. Geladen wird in voller.
    modell.to(torch.float16).save_pretrained(ziel, safe_serialization=True)
    del modell
    return str(ziel)


def erkenner(datenverzeichnis: Path, auftrag: dict[str, Any]) -> str:
    """Was faster-whisper laden soll, wenn das **unveränderte** Ausgangsmodell gefragt ist.

    Für die Tempowahl: Sie misst, wie gut das Modell am Anfang des Trainings
    diesen Sprecher bei welchem Tempo versteht. Auf einem Stand ist das der
    Stand, und der liegt schon in genau dem Format vor, das sie braucht.
    """
    ref = str(auftrag.get(laeufe.AUSGANGSSTAND) or "")
    if ref:
        return str(registry.ct2_verzeichnis(datenverzeichnis, ref))
    return laeufe.kurzname(str(auftrag["basismodell"]))
