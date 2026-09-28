"""Ein Trainingslauf - das, was auf der Karte passiert.

    python -m apps.lernen.training.finetune data/snapshots/job_01J8…

Aufgerufen vom Läufer (`laeufer.py`) mit einem Laufverzeichnis
(`wortlaut/laeufe.py`): Darin stehen Auftrag und Manifest, dorthin geht das
Ergebnis. Ein Prozess je Lauf, weil nur ein endender Prozess den
Kartenspeicher sicher zurückgibt.

`zustand.json` gehört diesem Prozess; der Läufer schreibt nur hinein, wenn er
wortlos gestorben ist.

Faltungen stehen im Manifest, Zahlen im Rezept (`rezepte/`); diese Datei setzt
zusammen. **Wie** auf der Karte gerechnet wird - Genauigkeit, Stapel je
Schritt, Gradientensparen -, misst sie vor jedem Training (`zuschneiden`,
`wortlaut/kartenplan.py`): Dasselbe Rezept läuft auf 11 GB und auf 80 GB.

    python -m apps.lernen.training.finetune --karte

beschreibt nur die Karte (`kartenplan.KARTE`) - der Läufer ruft das beim Start,
damit „lernen" weiß, was passt, bevor der erste Lauf kommt.
"""

from __future__ import annotations

import gc
import json
import math
import shutil
import signal
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from wortlaut import kartenplan, laeufe, sprachen, tempo

from . import abschluss as abschlussrechnung
from . import ausgangsstand
from . import tempowahl
from . import klangwandel
from . import karte
from . import steuerung as steuergroesse
from .daten import Proben, Stapler

REZEPTE = Path(__file__).parent / "rezepte"
# Der Keim des Laufs - für den Trainer und den Würfel des Wandlers (`klangwandel.py`).
KEIM = 20260912
# Jeder wievielte Schritt in die Lernkurve geht - die Oberfläche liest sie im Takt.
LOG_ALLE = 10

# Höchstanteil des Warmlaufs - bei sehr kleinem Korpus wäre die Schrittzahl des
# Rezepts länger als der Lauf (`trainiere`).
WARMLAUF_ANTEIL = 0.2


def _rezeptpfad(methode: str) -> Path:
    return REZEPTE / f"whisper_{methode}.yaml"


def _rezept_fuer(methode: str, basismodell: str) -> dict[str, Any]:
    """Das Rezept dieser Methode, mit den Abweichungen dieses Grundmodells darüber.

    `je_grundmodell` ist für Lernzahlen, die an der Modellgröße hängen; der
    Platz auf der Karte ist keine davon (`zuschneiden`).
    """
    rezept = yaml.safe_load(_rezeptpfad(methode).read_text(encoding="utf-8"))
    abweichungen = (rezept.get("je_grundmodell") or {}).get(laeufe.kurzname(basismodell), {})
    return {**rezept, **abweichungen}


class Bericht:
    """Der Draht nach draußen: Zustand, Fortschritt, Protokoll.

    Eine Stelle für alles, was der Prozess über sich sagt.
    """

    def __init__(self, verzeichnis: Path, spuren: bool = True) -> None:
        self.verzeichnis = verzeichnis
        # Ohne Spuren redet der Bericht nur - `nachziehen.py` lässt den
        # fertigen Lauf unberührt.
        self.spuren = spuren
        self.zustand: dict[str, Any] = {
            "status": laeufe.LAEUFT,
            "stufe": "vorbereiten",
            "begonnen": laeufe.jetzt(),
        }
        self._schreibe()

    def _schreibe(self) -> None:
        if self.spuren:
            laeufe.schreibe_json(self.verzeichnis / laeufe.ZUSTAND, self.zustand)

    def sage(self, text: str) -> None:
        """Ins Protokoll - und auf die Standardausgabe, wo der Läufer mitliest."""
        print(text, flush=True)

    def stufe(self, name: str, **weiteres: Any) -> None:
        self.zustand["stufe"] = name
        self.zustand.update(weiteres)
        self._schreibe()
        self.ereignis(art="stufe", name=name)
        self.sage(f"— {name}")

    def ereignis(self, **felder: Any) -> None:
        if not self.spuren:
            return
        laeufe.haenge_an(
            self.verzeichnis / laeufe.FORTSCHRITT, {"zeit": laeufe.jetzt(), **felder}
        )

    def merke(self, **felder: Any) -> None:
        """Einen Wert in den Zustand legen, den die Übersicht sehen soll.

        Was ein Lauf herausgefunden hat, etwa das Tempo - die Liste zeigt es,
        ohne den Fortschritt zu lesen.
        """
        self.zustand.update(felder)
        self._schreibe()

    def faltung(self, nummer: int | None) -> None:
        """Welche der sieben Trainings gerade läuft - für den Balken der Liste.

        `None` ist das Endmodell.
        """
        self.zustand["faltung"] = nummer
        self.zustand["faltungen_gesamt"] = laeufe.FALTUNGEN
        self.zustand["schritt"] = 0
        self._schreibe()
        self.ereignis(art="faltung", nummer=nummer)

    def schritt(self, schritt: int, gesamt: int) -> None:
        """Der Balken der Liste."""
        self.zustand["schritt"] = schritt
        self.zustand["schritte_gesamt"] = gesamt
        self._schreibe()

    def fertig(self, version: str, metriken: dict[str, Any]) -> None:
        self.zustand.update(
            {
                "status": laeufe.FERTIG,
                "stufe": "",
                "beendet": laeufe.jetzt(),
                "version": version,
                "metriken": metriken,
            }
        )
        self._schreibe()
        self.ereignis(art="fertig", version=version)

    def abgebrochen(self) -> None:
        """Angehalten auf Wunsch (`laeufe.HALT`). Wo er stand, bleibt stehen."""
        self.zustand.update({"status": laeufe.ABGEBROCHEN, "beendet": laeufe.jetzt()})
        self._schreibe()
        self.ereignis(art="abgebrochen")

    def gescheitert(self, grund: str) -> None:
        self.zustand.update(
            {"status": laeufe.GESCHEITERT, "stufe": "", "beendet": laeufe.jetzt(), "fehler": grund}
        )
        self._schreibe()
        self.ereignis(art="fehler", text=grund)


def _rueckmeldung(bericht: Bericht):
    """Ein Trainer-Rückruf, der aus Verlusten eine Kurve macht.

    Innen definiert, damit `transformers` erst beim Training geladen wird.
    """
    from transformers import TrainerCallback

    class Kurve(TrainerCallback):
        def on_train_begin(self, args, zustand, steuerung, **weiteres):
            bericht.ereignis(
                art="start",
                schritte_gesamt=int(zustand.max_steps),
                epochen=float(args.num_train_epochs),
            )
            bericht.schritt(0, int(zustand.max_steps))

        def on_log(self, args, zustand, steuerung, logs=None, **weiteres):
            logs = logs or {}
            if "loss" in logs:
                bericht.ereignis(
                    art="schritt",
                    schritt=int(zustand.global_step),
                    epoche=round(float(zustand.epoch or 0.0), 3),
                    verlust=round(float(logs["loss"]), 5),
                    lernrate=float(logs.get("learning_rate", 0.0)),
                )
            bericht.schritt(int(zustand.global_step), int(zustand.max_steps))

        def on_evaluate(self, args, zustand, steuerung, metrics=None, **weiteres):
            metrics = metrics or {}
            # Nur die Prüfung je Durchgang; der Abschluss misst unter eigenem
            # Präfix (`abschluss.py`).
            if "eval_loss" not in metrics:
                return
            # Bei der Steuergröße `wer` auch die frei dekodierte WER (`steuerung.py`).
            wer = {"wer": round(float(metrics["eval_wer"]), 5)} if "eval_wer" in metrics else {}
            bericht.ereignis(
                art="validierung",
                schritt=int(zustand.global_step),
                epoche=round(float(zustand.epoch or 0.0), 3),
                verlust=round(float(metrics.get("eval_loss", 0.0)), 5),
                **wer,
            )

    return Kurve()


def _trainerklasse():
    """Ein Trainer, der Proben nach ihrem Gewicht zählt.

    Das Gewicht steht je Zeile im Manifest (`services/auftraege.GEWICHTE`).
    Eine eigene Verlustrechnung, weil `transformers` über alle Marken des
    Stapels mittelt und keine Proben kennt.
    """
    import torch
    from transformers import Seq2SeqTrainer

    class GewichtetesTraining(Seq2SeqTrainer):
        # Wie viele Marken eine Prüfung frei erzeugen darf; `None`: Die
        # Prüfung misst nur den Verlust (`steuerung.py`).
        neue_marken: int | None = None

        def prediction_step(
            self, model, inputs, prediction_loss_only, ignore_keys=None, **erzeugung
        ):
            """Der gewichtete Verlust - und bei der Steuergröße `wer` die freie Dekodierung.

            Nicht über `predict_with_generate`: Das reichte `gewichte` an
            `generate` weiter und rechnete den Verlust ungewichtet.
            """
            verlust, _, _ = super(Seq2SeqTrainer, self).prediction_step(
                model, inputs, prediction_loss_only=True, ignore_keys=ignore_keys
            )
            if prediction_loss_only or self.neue_marken is None:
                return verlust, None, None
            eingang = self._prepare_inputs(inputs)
            # Die halbe Genauigkeit des Trainings auch hier: Der Trainer legt
            # sie nur um `forward`, `generate` ruft den Encoder daran vorbei -
            # bei LoRA auf einem halben Grundmodell.
            halb = torch.float16 if self.args.fp16 else torch.bfloat16 if self.args.bf16 else None
            geraet = eingang["input_features"].device.type
            # Gierig: Die Prüfung soll Stände ordnen, nicht die letzte Stelle treffen.
            with torch.no_grad(), torch.autocast(geraet, dtype=halb, enabled=halb is not None):
                erzeugt = model.generate(
                    input_features=eingang["input_features"],
                    max_new_tokens=self.neue_marken,
                    num_beams=1,
                )
            return verlust, erzeugt, eingang["labels"]

        def compute_loss(
            self, model, inputs, return_outputs=False, num_items_in_batch=None
        ):
            gewichte = inputs.pop("gewichte", None)
            marken = inputs["labels"]
            ausgabe = model(**inputs)

            if gewichte is None:
                return (ausgabe.loss, ausgabe) if return_outputs else ausgabe.loss

            # Je Marke ein Verlust, ohne Mittelung - erst danach lässt sich je
            # Probe gewichten.
            je_marke = torch.nn.functional.cross_entropy(
                ausgabe.logits.view(-1, ausgabe.logits.size(-1)).float(),
                marken.view(-1),
                ignore_index=-100,
                reduction="none",
            ).view(marken.shape)

            gilt = marken.ne(-100)
            # Je Probe gemittelt, damit lange Sätze nicht mehr zählen.
            je_probe = (je_marke * gilt).sum(dim=1) / gilt.sum(dim=1).clamp(min=1)
            gewichte = gewichte.to(je_probe.device, je_probe.dtype)
            verlust = (je_probe * gewichte).sum() / gewichte.sum().clamp(min=1e-8)
            return (verlust, ausgabe) if return_outputs else verlust

    return GewichtetesTraining


def _name_fuer(faltung: int | None) -> str:
    """Wie das Verzeichnis einer Faltung heißt - `endmodell`, wenn keine."""
    return "endmodell" if faltung is None else f"faltung-{faltung}"


def _halt_nach(ziel: float, bericht):
    """Ein Rückruf, der nach `ziel` Durchgängen Schluss macht - Plan unberührt.

    Das Endmodell hat kein Abbruchkriterium, weiß aber aus den Faltungen,
    wann sie am besten standen, und hört dort auf - auf derselben Rampe. Ein
    kleineres `num_train_epochs` verschöbe den Lernratenverlauf (`trainiere`).

    Geprüft nach jedem Schritt: Bei der Steuergröße `wer` stand eine Faltung
    auch mitten in einem Durchgang am besten (`steuerung.py`).
    """
    from transformers import TrainerCallback

    class Haltestelle(TrainerCallback):
        def __init__(self) -> None:
            self.gesagt = False

        def on_step_end(self, args, zustand, steuerung, **weiteres):
            # Auf den nächsten Schritt: `ziel` ist auf zwei Stellen gerundet
            # (`_bester_durchgang`).
            je_durchgang = float(zustand.max_steps) / max(1e-9, float(args.num_train_epochs))
            if float(zustand.epoch or 0.0) >= ziel - 0.5 / max(1.0, je_durchgang):
                steuerung.should_training_stop = True
                if not self.gesagt:
                    bericht.sage(
                        f"Schluss nach {zustand.epoch:.1f} Durchgängen - "
                        "so weit reichten die Faltungen."
                    )
                    self.gesagt = True
            return steuerung

    return Haltestelle()


def _bester_durchgang(trainer, obergrenze: float, hat_pruefung: bool) -> float:
    """Bei welchem Durchgang dieser Lauf am besten stand.

    Ohne Steuergröße (Endmodell) die gelaufene Zahl.
    """
    if not hat_pruefung or not trainer.state.best_model_checkpoint:
        return float(trainer.state.epoch or obergrenze)
    schritt = int(Path(trainer.state.best_model_checkpoint).name.rsplit("-", 1)[-1])
    je_durchgang = max(1.0, float(trainer.state.max_steps) / max(1e-9, float(obergrenze)))
    return round(schritt / je_durchgang, 2)


def trainiere(
    verzeichnis: Path,
    datenverzeichnis: Path,
    bericht: Bericht,
    faltung: int | None = None,
    vorgaben: dict[str, Any] | None = None,
) -> tuple[Path, abschlussrechnung.Ergebnis, dict[str, Any]]:
    """Ein Training; gibt Gewichte, Abschluss und die gelernten Kennzahlen zurück.

    `faltung` bleibt draußen: Gelernt wird auf den anderen fünf, gesteuert und
    gemessen auf ihr. `None` ist das Endmodell - lernt auf allem, misst nichts,
    diktiert in „schreiben". Ohne Validierung bringt es Durchgänge, Plan, α
    und Tempo aus den Faltungen mit (`vorgaben`). Den Abschluss regelt
    `abschluss.py`.
    """
    import torch
    from transformers import (
        Seq2SeqTrainingArguments,
        WhisperFeatureExtractor,
        WhisperForConditionalGeneration,
        WhisperTokenizerFast,
    )
    from wortlaut import corpus

    from apps.lernen.backend.config import einstellungen

    auftrag = laeufe.lies_json(verzeichnis / laeufe.AUFTRAG) or {}
    methode = str(auftrag["methode"])
    basismodell = str(auftrag["basismodell"])
    sprecher_id = str(auftrag["sprecher_id"])
    # Vor dem Laden geprüft, damit ein Tippfehler sofort auffällt.
    art = abschlussrechnung.pruefe(
        str(auftrag.get("abschluss") or laeufe.ABSCHLUSS_BESTER)
    )
    abwandlung = klangwandel.pruefe(
        str(auftrag.get("augmentierung") or laeufe.AUG_KEINE)
    )
    dauer = str(auftrag.get("dauer") or laeufe.DAUER_FEST)
    if dauer not in laeufe.DAUERN:
        raise RuntimeError(
            f"Unbekannte Dauer: {dauer}. Zur Wahl stehen: {', '.join(laeufe.DAUERN)}."
        )
    konfiguration = einstellungen()
    # Vor jedem Training: Das Sprachmodell der Textquelle kann seit dem letzten
    # längst wieder geladen sein.
    karte.entlade_ollama(konfiguration.ollama_url, bericht)
    diese_karte = miss_karte()
    # Auch hier geprüft, auf der Karte, die wirklich da ist: Ein Auftrag kann
    # von Hand im Verzeichnis liegen oder von einer anderen Maschine stammen.
    erlaubt = laeufe.methoden_fuer(basismodell, diese_karte, konfiguration.lernen_reserve_mb)
    if methode not in erlaubt:
        raise RuntimeError(
            f"{laeufe.kurzname(basismodell)} lässt sich auf "
            f"{diese_karte.name if diese_karte else 'dem Prozessor'} nur mit "
            f"{', '.join(erlaubt) or 'nichts'} trainieren."
        )
    rezept = _rezept_fuer(methode, basismodell)
    gemischt = bool(rezept.get("mischpraezision", True)) and diese_karte is not None

    bericht.stufe("laden")
    bericht.sage(f"Rezept: {rezept['name']} · Grundmodell: {basismodell}")

    # Fest gesetzt: Sprache zu erkennen kostet bei kurzen Sätzen Genauigkeit.
    sprache = str(auftrag.get("sprache") or sprachen.VORGABE)
    ausleser = WhisperFeatureExtractor.from_pretrained(basismodell)
    # Der schnelle Zerteiler: Nur er schreibt `tokenizer.json`, und ohne sie
    # lädt faster-whisper still den Zerteiler von `whisper-tiny`.
    zerteiler = WhisperTokenizerFast.from_pretrained(
        basismodell, language=sprache, task="transcribe"
    )
    # Gewichte vom Grundmodell oder Ausgangsstand (`ausgangsstand.py`);
    # Zerteiler und Ausleser bleiben die des Grundmodells.
    gewichtsquelle = ausgangsstand.quelle(verzeichnis, datenverzeichnis, auftrag, bericht)
    # Bei LoRA das eingefrorene Grundmodell in halber Genauigkeit, der Zusatz
    # bleibt float32 (`autocast_adapter_dtype` unten) - bei `large-v3` drei
    # Gigabyte weniger (`kartenplan.py`). Die Aufmerksamkeit immer über `sdpa`.
    halb = methode == laeufe.LORA and gemischt
    modell = WhisperForConditionalGeneration.from_pretrained(
        gewichtsquelle,
        attn_implementation="sdpa",
        dtype=_torchtyp(kartenplan.genauigkeit(diese_karte)) if halb else torch.float32,
    )

    # Die erzwungenen Marken stehen schon in denen des Zerteilers.
    modell.generation_config.language = sprache
    modell.generation_config.task = "transcribe"
    modell.generation_config.forced_decoder_ids = None
    modell.config.forced_decoder_ids = None

    # Whispers `config.json` führt Erzeugungsparameter (`max_length`,
    # `suppress_tokens`, …), die in die `generation_config` gehören.
    # `save_pretrained` räumt sie bei jedem Zwischenstand mit Warnung um und
    # setzt dabei den Wert der `config` über den richtigen - bei `small` 86
    # statt 88 unterdrückte Marken. Hier fällt die `config`-Seite weg.
    for feld in list(modell.config._get_non_default_generation_parameters()):
        setattr(modell.config, feld, None)

    if methode == laeufe.LORA:
        from peft import LoraConfig, get_peft_model

        einstellung = rezept["lora"]
        modell = get_peft_model(
            modell,
            LoraConfig(
                r=int(einstellung["rang"]),
                lora_alpha=int(einstellung["alpha"]),
                lora_dropout=float(einstellung["ausfall"]),
                target_modules=list(einstellung["ziele"]),
                bias="none",
            ),
            # Der Zusatz in float32, auch über einem halben Grundmodell.
            autocast_adapter_dtype=True,
        )
        # Sonst bekommt der Zusatz beim Gradientensparen keinen Gradienten -
        # der Lauf liefe durch und lernte nichts. Ob gespart wird, zeigt erst
        # der Probeschritt (`zuschneiden`).
        modell.enable_input_require_grads()
        trainierbar = sum(p.numel() for p in modell.parameters() if p.requires_grad)
        gesamt = sum(p.numel() for p in modell.parameters())
        bericht.sage(f"LoRA: {trainierbar:,} von {gesamt:,} Gewichten werden gelernt")

    korpuswurzel = datenverzeichnis / corpus.sprecher_relpfad(sprecher_id)
    # Nur an den Lernproben; die Steuergröße bleibt unverändert (`klangwandel.py`).
    wandler = klangwandel.Wandler(
        stufe=abwandlung,
        einstellungen=klangwandel.einstellungen_aus(rezept),
        keim=KEIM + (faltung or 0),
    )
    kern = laeufe.kernfaltungen_aus(verzeichnis, auftrag)
    lernzeilen, messzeilen = laeufe.zeilen_fuer_faltung(
        verzeichnis,
        faltung,
        str(auftrag.get("daten") or laeufe.NUR_ORIGINAL),
        korpuswurzel,
        kern,
    )
    if kern is not None:
        bericht.sage(
            f"Kernauswahl: nur der Kern ({len(kern)} Aufnahmen) - "
            f"{len(lernzeilen)} Proben zum Lernen, {len(messzeilen)} zum Steuern und Messen"
        )
    # Das Tempo steht im Auftrag, nicht im Rezept. Vorgespult wird je Datei
    # einmal, ins Zwischenlager des Laufs.
    faktor = float(auftrag.get("tempo", tempo.VORGABE))
    tempoergebnis: tempowahl.Ergebnis | None = None
    gewaehlt = laeufe.tempowahl_aus(auftrag)

    if gewaehlt == laeufe.TEMPO_GESCHAETZT:
        # Aus Textlänge und Aufnahmedauer (`tempowahl.aus_dauern`).
        if vorgaben and vorgaben.get("tempo") is not None:
            faktor = float(vorgaben["tempo"])
            bericht.sage(f"Tempo aus den Faltungen übernommen: Faktor {faktor:g}")
        else:
            tempoergebnis = tempowahl.aus_dauern(lernzeilen, bericht)
            faktor = tempoergebnis.faktor
            if tempoergebnis.hinweis:
                bericht.sage(f"  {tempoergebnis.hinweis}")
    elif gewaehlt == laeufe.TEMPO_OPTIMAL:
        if vorgaben and vorgaben.get("tempo") is not None:
            # Das Endmodell übernimmt das Tempo der Faltungen.
            faktor = float(vorgaben["tempo"])
            bericht.sage(f"Tempo aus den Faltungen übernommen: Faktor {faktor:g}")
        else:
            # Auf den Lernzeilen - nie an dem, woran gemessen wird.
            tempoergebnis = tempowahl.waehle(
                lernzeilen,
                korpuswurzel,
                ausgangsstand.erkenner(datenverzeichnis, auftrag),
                sprache,
                bericht,
                faltung,
            )
            faktor = tempoergebnis.faktor
            if tempoergebnis.hinweis:
                bericht.sage(f"  {tempoergebnis.hinweis}")

    zwischenlager = verzeichnis / laeufe.VORGESPULT if tempo.vorspulen_noetig(faktor) else None
    if zwischenlager is not None:
        bericht.sage(f"Vorgespult: Faktor {faktor:g} - Tonhöhe bleibt")

    lern = Proben(lernzeilen, korpuswurzel, ausleser, zerteiler, wandler, faktor, zwischenlager)
    pruef = Proben(messzeilen, korpuswurzel, ausleser, zerteiler, None, faktor, zwischenlager)
    bericht.sage(f"Proben: {len(lern)} zum Lernen, {len(pruef)} zum Steuern")
    if wandler.taetig:
        bericht.sage(f"Augmentierung: {abwandlung} (nur auf den Lernproben)")
    if not len(lern):
        raise RuntimeError("Das Manifest enthält keine Trainingsprobe.")

    # Das Endmodell hält nichts zurück und hat keine Steuergröße.
    hat_pruefung = len(pruef) > 0

    zuschnitt = zuschneiden(
        modell,
        diese_karte,
        methode,
        int(rezept["stapel"]),
        gemischt,
        laengste=max(len(zerteiler(str(zeile["text"])).input_ids) for zeile in lernzeilen),
        mel_kanaele=int(ausleser.feature_size),
        reserve_mb=konfiguration.lernen_reserve_mb,
        bericht=bericht,
    )

    # `geduldig` braucht eine Validierung; ohne fällt es auf `fest` zurück.
    geduldig = dauer == laeufe.DAUER_GEDULDIG and hat_pruefung
    if dauer == laeufe.DAUER_GEDULDIG and not hat_pruefung:
        bericht.sage(
            "Geduldig nicht möglich: Ohne Validierungsproben gibt es kein "
            "Kriterium. Es gilt die feste Zahl Durchgänge."
        )
    # `plan` ist der Horizont der Lernrate, `halt` wo aufgehört wird. Eine
    # Faltung plant über ihre Obergrenze und hört auf, wenn die Geduld endet.
    plan = float(
        rezept.get("epochen_hoechstens", rezept["epochen"]) if geduldig else rezept["epochen"]
    )
    halt: float | None = None
    if vorgaben and vorgaben.get("durchgaenge"):
        # Das Endmodell erbt Plan und Halt der Faltungen: dieselbe Rampe,
        # derselbe Punkt darauf. Nur die Durchgangszahl mit neu gebautem Plan
        # wäre ein anderer Lauf - mit Warmlauf und Spitze an anderer Stelle
        # (`docs/lernen.md`).
        plan = float(vorgaben.get("plan") or vorgaben["durchgaenge"])
        halt = float(vorgaben["durchgaenge"])
        geduldig = False
        bericht.sage(
            f"Aus den Faltungen übernommen: Plan über {plan:.1f} Durchgänge, "
            f"Schluss nach {halt:.1f} - derselbe Lernratenverlauf wie dort."
        )
    durchgaenge = plan

    # Der Warmlauf, gedeckelt auf `WARMLAUF_ANTEIL` - sonst wäre bei neun
    # Aufnahmen der ganze Lauf Rampe. Größere Läufe behalten die Schrittzahl
    # des Rezepts.
    je_durchgang = max(1, math.ceil(len(lern) / zuschnitt.wirksam))
    gesamtschritte = max(1, int(je_durchgang * durchgaenge))
    warmlauf = min(
        int(rezept["warmlauf_schritte"]),
        max(1, math.ceil(WARMLAUF_ANTEIL * gesamtschritte)),
    )
    if warmlauf < int(rezept["warmlauf_schritte"]):
        bericht.sage(
            f"Warmlauf gekürzt: {warmlauf} statt {rezept['warmlauf_schritte']} Schritte "
            f"- der Lauf hat nur {gesamtschritte}."
        )

    # Wonach ausgewählt wird (`steuerung.py`): bei `wer` öfter geprüft, und
    # jede Prüfung dekodiert frei.
    pruefplan = steuergroesse.plane(
        laeufe.steuerung_aus(auftrag), hat_pruefung, je_durchgang, rezept
    )
    if pruefplan.dekodiert:
        bericht.sage(
            f"Steuergröße WER: {pruefplan.je_durchgang} Prüfungen je Durchgang, "
            f"alle {pruefplan.alle_schritte} Schritte, frei dekodiert"
        )
    # Prüfen und Sichern im selben Takt - `load_best_model_at_end` verlangt es.
    takt = "steps" if pruefplan.alle_schritte else "epoch"

    # Je Faltung ein Arbeitsstand, den `main` vor der nächsten wegräumt.
    ausgabe = verzeichnis / laeufe.ARBEITSSTAND / _name_fuer(faltung)
    sparsam = zuschnitt.gradientensparsam
    argumente = Seq2SeqTrainingArguments(
        output_dir=str(ausgabe),
        per_device_train_batch_size=zuschnitt.stapel,
        per_device_eval_batch_size=zuschnitt.stapel,
        gradient_accumulation_steps=zuschnitt.akkumulation,
        # Aktivierungen beim Rückwärtsgang neu rechnen: dieselben Gradienten,
        # weniger Platz - wenn der Probeschritt es verlangt (`zuschneiden`).
        gradient_checkpointing=sparsam,
        # Sonst warnt torch je Schritt, und die reentrante Fassung verträgt
        # eingefrorene LoRA-Gewichte schlecht.
        gradient_checkpointing_kwargs={"use_reentrant": False} if sparsam else None,
        learning_rate=float(rezept["lernrate"]),
        warmup_steps=warmlauf,
        num_train_epochs=durchgaenge,
        weight_decay=float(rezept.get("gewichtsverfall", 0.0)),
        max_grad_norm=float(rezept.get("gradientenbegrenzung", 1.0)),
        # bf16 ab Ampere, fp16 mit Verlustskalierung darunter (`kartenplan.genauigkeit`).
        fp16=zuschnitt.genauigkeit == "fp16",
        bf16=zuschnitt.genauigkeit == "bf16",
        logging_steps=LOG_ALLE,
        # Je Durchgang prüfen, bei der Steuergröße `wer` öfter - die zweite Kurve.
        eval_strategy=takt if hat_pruefung else "no",
        # Je Prüfung sichern und am Ende den besten nehmen: Die Validierung
        # dreht bei wenig Sprache in der Mitte, danach lernt das Modell
        # auswendig. Die Durchgangszahl ist so nur eine Obergrenze.
        #
        # Wie viele Zwischenstände bleiben, sagt `abschluss.zu_behalten`; wer
        # mittelt oder öfter prüft, sichert ohne Optimierer (`save_only_model`)
        # - fortgesetzt wird ein Lauf nie. Alles verschwindet mit dem
        # `arbeitsstand` (`main`).
        save_strategy=takt if hat_pruefung else "no",
        **(
            {"eval_steps": pruefplan.alle_schritte, "save_steps": pruefplan.alle_schritte}
            if pruefplan.alle_schritte
            else {}
        ),
        save_total_limit=abschlussrechnung.zu_behalten(art, rezept),
        save_only_model=laeufe.mittelt(art) or pruefplan.dekodiert,
        load_best_model_at_end=hat_pruefung,
        metric_for_best_model=pruefplan.metrik,
        greater_is_better=False,
        # Der Bericht ist der einzige Draht nach draußen.
        report_to=[],
        # Eine kurze WAV-Datei liest sich schneller als ein Schritt.
        dataloader_num_workers=2,
        remove_unused_columns=False,
        label_names=["labels"],
        seed=KEIM,
    )

    rueckrufe: list[Any] = [_rueckmeldung(bericht)]
    if halt is not None:
        rueckrufe.append(_halt_nach(halt, bericht))
    if geduldig:
        from transformers import EarlyStoppingCallback

        geduld = pruefplan.geduld(rezept)
        gewinn = float(rezept.get("mindestgewinn", 0.0))
        rueckrufe.append(
            EarlyStoppingCallback(
                early_stopping_patience=geduld, early_stopping_threshold=gewinn
            )
        )
        bericht.sage(
            f"Geduldig: höchstens {durchgaenge:.0f} Durchgänge, Schluss nach {geduld} "
            f"Prüfungen ohne Gewinn von mehr als {gewinn}."
        )

    trainer = _trainerklasse()(
        model=modell,
        args=argumente,
        train_dataset=lern,
        eval_dataset=pruef if len(pruef) else None,
        data_collator=Stapler(zerteiler),
        callbacks=rueckrufe,
        compute_metrics=steuergroesse.wer_rechner(zerteiler) if pruefplan.dekodiert else None,
    )
    if pruefplan.dekodiert:
        # Genug für den längsten Satz der Validierung und etwas Übermaß -
        # mehr erzeugt nur ein Stand, der sich wiederholt.
        laengste_pruefung = max(len(zerteiler(str(zeile["text"])).input_ids) for zeile in messzeilen)
        trainer.neue_marken = min(
            int(modell.config.max_target_positions) // 2, 2 * laengste_pruefung + 10
        )

    bericht.stufe("training")
    trainer.train()

    # Ob die Geduld endete oder die Obergrenze - eine Kurve, die am Ende noch
    # fällt, sieht sonst fertig aus.
    if geduldig:
        gelaufen = float(trainer.state.epoch or 0.0)
        if gelaufen >= durchgaenge - 0.5:
            bericht.sage(
                f"Achtung: Die Obergrenze von {durchgaenge:.0f} Durchgängen war erreicht, "
                "die Geduld also nicht aufgebraucht - es wäre womöglich noch besser geworden."
            )
        else:
            bericht.sage(f"Schluss nach {gelaufen:.0f} Durchgängen: Es wurde nicht mehr besser.")

    if hat_pruefung and trainer.state.best_model_checkpoint:
        # Weit vor dem letzten heißt: Die Obergrenze des Rezepts ist zu hoch.
        bericht.sage(
            f"Bester Durchgang: {Path(trainer.state.best_model_checkpoint).name} "
            f"· {pruefplan.name} {trainer.state.best_metric:.5f}"
        )
        bericht.ereignis(
            art="bester",
            schritt=int(Path(trainer.state.best_model_checkpoint).name.rsplit("-", 1)[-1]),
            mass=pruefplan.mass,
            wert=round(float(trainer.state.best_metric), 5),
        )

    # Bei `bester` geschieht nichts (`abschluss.py`).
    ergebnis = abschlussrechnung.fuehre_aus(
        art=art,
        modell=modell,
        trainer=trainer,
        rezept=rezept,
        # Interpoliert wird zum Anfang des Trainings, also ggf. zum Ausgangsstand.
        basismodell=gewichtsquelle,
        arbeitsstand=ausgabe,
        hat_pruefung=hat_pruefung,
        bericht=bericht,
        alpha_vorgabe=(vorgaben or {}).get("alpha"),
        mass=pruefplan.mass,
    )

    bericht.stufe("sichern")
    gewichte = verzeichnis / laeufe.GEWICHTE / _name_fuer(faltung)
    if methode == laeufe.LORA:
        # Zusammengerechnet: CTranslate2 kennt kein LoRA.
        modell = modell.merge_and_unload()
    modell.save_pretrained(gewichte, safe_serialization=True)
    # Die Umwandlung nimmt beide mit (`wandle_um`).
    zerteiler.save_pretrained(gewichte)
    ausleser.save_pretrained(gewichte)

    # Was das Endmodell von dieser Faltung mitnimmt.
    kennzahlen: dict[str, Any] = {
        "durchgaenge": _bester_durchgang(trainer, durchgaenge, hat_pruefung),
        "plan_durchgaenge": plan,
        "alpha": ergebnis.alpha,
        "tempo": faktor,
        "tempowahl": tempoergebnis.als_dict() if tempoergebnis is not None else None,
        # Worauf und wie gerechnet wurde - fürs Manifest (`bewerten.gib_frei`).
        "zuschnitt": {
            **zuschnitt.als_dict(),
            "karte": diese_karte.als_dict() if diese_karte else None,
        },
    }

    # `del`, sonst hält der Trainer Modell und Optimierer auf der Karte fest.
    del trainer, modell
    raeume_karte(bericht)

    return gewichte, ergebnis, kennzahlen


def trainiere_geduldig(
    verzeichnis: Path,
    datenverzeichnis: Path,
    bericht: Bericht,
    faltung: int | None = None,
    vorgaben: dict[str, Any] | None = None,
) -> tuple[Path, abschlussrechnung.Ergebnis, dict[str, Any]]:
    """`trainiere` - und ist die Karte belegt, warten und die Faltung neu beginnen.

    Von vorn: Zwischenstände und Gewichte der Faltung gehen weg (`karte.py`).
    """

    def aufraeumen() -> None:
        shutil.rmtree(verzeichnis / laeufe.ARBEITSSTAND / _name_fuer(faltung), ignore_errors=True)
        shutil.rmtree(verzeichnis / laeufe.GEWICHTE / _name_fuer(faltung), ignore_errors=True)
        raeume_karte(bericht)

    return karte.mit_geduld(
        lambda: trainiere(verzeichnis, datenverzeichnis, bericht, faltung, vorgaben),
        bericht,
        aufraeumen=aufraeumen,
        fremd_belegt_mb=fremd_belegt_mb,
    )


def fremd_belegt_mb() -> float:
    """Was auf der Karte belegt ist und nicht dem torch dieses Prozesses gehört.

    Der eigene CUDA-Kontext zählt mit; dafür hat `karte.FREMD_AB_MB` Spielraum.
    """
    import torch

    if not torch.cuda.is_available():
        return 0.0
    frei, gesamt = torch.cuda.mem_get_info()
    return (gesamt - frei - torch.cuda.memory_reserved()) / 1e6


def frei_mb() -> float:
    """Was auf der Karte gerade frei ist - für alle, nicht nur für diesen Prozess."""
    import torch

    if not torch.cuda.is_available():
        return 0.0
    return torch.cuda.mem_get_info()[0] / 1e6


def miss_karte() -> kartenplan.Karte | None:
    """Die Karte, auf der gerechnet wird - `None` ohne CUDA.

    Die erste sichtbare; mehrere zählen nur mit (`kartenplan.py`).
    """
    import torch

    if not torch.cuda.is_available():
        return None
    eigenschaften = torch.cuda.get_device_properties(0)
    return kartenplan.Karte(
        name=str(eigenschaften.name),
        speicher_mb=eigenschaften.total_memory / 1e6,
        rechenfaehigkeit=(int(eigenschaften.major), int(eigenschaften.minor)),
        anzahl=int(torch.cuda.device_count()),
    )


def melde_karte(datenverzeichnis: Path, bericht: Bericht | None = None) -> kartenplan.Karte | None:
    """Die Karte messen und neben die Läufe legen - damit `lernen` anbietet, was passt."""
    diese = miss_karte()
    if diese is not None:
        kartenplan.schreibe_karte(laeufe.wurzel(datenverzeichnis), diese)
        if bericht is not None:
            bericht.sage(
                f"Karte: {diese.name}, {diese.speicher_mb:.0f} MB, Rechenfähigkeit "
                f"{diese.rechenfaehigkeit[0]}.{diese.rechenfaehigkeit[1]}"
                + (f", {diese.anzahl} Karten - gerechnet wird auf der ersten" if diese.anzahl > 1 else "")
                + f"; frei {frei_mb():.0f} MB"
            )
    elif bericht is not None:
        bericht.sage("Keine Karte - gerechnet wird auf dem Prozessor.")
    return diese


def _torchtyp(genauigkeit: str):
    import torch

    return {"bf16": torch.bfloat16, "fp16": torch.float16}.get(genauigkeit, torch.float32)


def _probeschritt(
    modell, stapel: int, sparsam: bool, mel_kanaele: int, laengste: int, genauigkeit: str
) -> float:
    """Ein Vorwärts- und Rückwärtsgang mit dem schwersten Stapel; gibt die Spitze in MB.

    Schwerster Stapel: Whisper hört immer 30 Sekunden (3000 Merkmalsrahmen),
    also zählt allein der längste Text. Ein Speichermangel geht als Fehler
    hinaus; was der Schritt belegt hat, gibt er in jedem Fall zurück.
    """
    import torch

    if sparsam:
        modell.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    else:
        modell.gradient_checkpointing_disable()
    modell.train()
    geraet = next(modell.parameters()).device
    merkmale = torch.zeros((stapel, mel_kanaele, 3000), device=geraet)
    # Irgendeine Marke, so oft wie der längste Text lang ist.
    marken = torch.full((stapel, max(2, laengste)), 50257, dtype=torch.long, device=geraet)
    torch.cuda.reset_peak_memory_stats()
    try:
        with torch.autocast("cuda", dtype=_torchtyp(genauigkeit), enabled=genauigkeit != "fp32"):
            verlust = modell(input_features=merkmale, labels=marken).loss
        verlust.backward()
        return torch.cuda.max_memory_reserved() / 1e6
    finally:
        modell.zero_grad(set_to_none=True)
        verlust = merkmale = marken = None
        gc.collect()
        torch.cuda.empty_cache()


def zuschneiden(
    modell,
    diese_karte: kartenplan.Karte | None,
    methode: str,
    wirksam: int,
    gemischt: bool,
    *,
    laengste: int,
    mel_kanaele: int,
    reserve_mb: float,
    bericht: Bericht,
) -> kartenplan.Plan:
    """Wie dieses Training auf diese Karte passt - ausprobiert, nicht geschätzt.

    Die Kandidaten der Reihe nach (`kartenplan.kandidaten`): erst schnell, dann
    sparsam, dann mit kleinerem Stapel. Der erste, dessen Probeschritt samt
    Optimierer neben den anderen Prozessen und der Reserve Platz hat, gilt.
    Passt keiner, ist das ein Speichermangel - `mit_geduld` wartet dann, falls
    andere die Karte halten.
    """
    if diese_karte is None:
        plan = kartenplan.plan(None, methode, wirksam, wirksam, False)
        bericht.sage(f"Zuschnitt: Prozessor · {plan.beschreibung()}")
        return plan

    genau = kartenplan.genauigkeit(diese_karte) if gemischt else "fp32"
    modell.to("cuda")
    trainierbar = sum(p.numel() for p in modell.parameters() if p.requires_grad)
    zusatz = kartenplan.optimierer_mb(trainierbar)
    for stapel, sparsam in kartenplan.kandidaten(wirksam):
        try:
            spitze = _probeschritt(modell, stapel, sparsam, mel_kanaele, laengste, genau)
        except Exception as ursache:  # noqa: BLE001 - was immer torch wirft
            if not karte.ist_speichermangel(ursache):
                raise
            spitze = None
        if spitze is not None and kartenplan.passt(
            spitze, zusatz, diese_karte.speicher_mb, fremd_belegt_mb(), reserve_mb
        ):
            plan = kartenplan.plan(diese_karte, methode, wirksam, stapel, sparsam)
            if not gemischt:
                plan = kartenplan.Plan(
                    genauigkeit="fp32",
                    halbe_grundgewichte=False,
                    stapel=plan.stapel,
                    akkumulation=plan.akkumulation,
                    gradientensparsam=plan.gradientensparsam,
                )
            # Wie beim Probeschritt zuletzt eingestellt - der Trainer schaltet
            # das Sparen nur ein, nie aus.
            if not sparsam:
                modell.gradient_checkpointing_disable()
            bericht.sage(
                f"Zuschnitt: {diese_karte.name} · {plan.beschreibung()} · "
                f"Probeschritt {spitze:.0f} MB, Optimierer {zusatz:.0f} MB, "
                f"Reserve {reserve_mb:.0f} MB"
            )
            bericht.merke(zuschnitt=plan.als_dict())
            return plan
    raise RuntimeError(
        f"CUDA out of memory: Auf {diese_karte.name} passt nicht einmal ein Stapel von 1 "
        f"mit Gradientensparen neben {fremd_belegt_mb():.0f} MB anderer Prozesse und "
        f"{reserve_mb:.0f} MB Reserve (WORTLAUT_LERNEN_RESERVE_MB)."
    )


# Was faster-whisper neben den Gewichten braucht. Ohne `tokenizer.json` nimmt
# es still den Zerteiler von `whisper-tiny`.
BEIZULEGEN = ["tokenizer.json", "preprocessor_config.json"]


def raeume_karte(bericht: Bericht | None = None) -> float:
    """Den Speicher der Karte wirklich zurückgeben; liefert die Megabyte.

    torch behält freigewordenen Speicher in seinem Vorrat; für CTranslate2,
    das beim Treiber holt, bleibt er belegt - bei `medium` genug, dass der
    Erkenner danach nicht mehr lädt. Aufgerufen nur beim Wechsel zwischen
    Lernen und Messen, denn danach muss torch seinen Vorrat neu holen.
    """
    gc.collect()
    try:
        import torch
    except ImportError:  # pragma: no cover - hängt am Abbild
        return 0.0
    if not torch.cuda.is_available():
        return 0.0
    vorher = torch.cuda.memory_reserved()
    torch.cuda.empty_cache()
    frei = (vorher - torch.cuda.memory_reserved()) / 1e6
    if bericht is not None and frei > 1.0:
        bericht.sage(f"  Karte freigegeben: {frei:.0f} MB")
    return frei


def wandle_um(gewichte: Path, ziel: Path, bericht: Bericht) -> None:
    """Nach CTranslate2 - das Format, das faster-whisper lädt.

    „schreiben" und die Auswertung laufen über faster-whisper
    (`wortlaut/whisper/local.py`).
    """
    from ctranslate2.converters import TransformersConverter

    bericht.stufe("umwandeln")
    fehlend = [name for name in BEIZULEGEN if not (gewichte / name).is_file()]
    if fehlend:
        # Sonst sähe der falsche Zerteiler aus wie ein misslungenes Training.
        raise RuntimeError(f"Zum Umwandeln fehlt: {', '.join(fehlend)}")

    TransformersConverter(
        str(gewichte), copy_files=BEIZULEGEN, load_as_float16=True
    ).convert(str(ziel), quantization="float16", force=True)


def _median(werte: list[float]) -> float | None:
    """Der Median - eine Faltung, die aus der Reihe fällt, entscheidet nicht mit."""
    da = sorted(wert for wert in werte if wert is not None)
    if not da:
        return None
    mitte = len(da) // 2
    return da[mitte] if len(da) % 2 else (da[mitte - 1] + da[mitte]) / 2


def _gewaehltes_tempo(gelernt: list[dict[str, Any]], auftrag: dict[str, Any]) -> float | None:
    """Der Faktor, mit dem das Endmodell rechnet.

    Gesucht: das Minimum der zusammengelegten Kurve. Geschätzt: das Mittel,
    auf eine Viertelstufe gerundet. Sonst ist der Wert überall derselbe.
    """
    faktoren = [float(k["tempo"]) for k in gelernt if k.get("tempo") is not None]
    if not faktoren:
        return None
    gewaehlt = laeufe.tempowahl_aus(auftrag)
    if gewaehlt == laeufe.TEMPO_GESCHAETZT:
        # Das Mittel: Über Summen gerechnet sind Ausreißer nicht zu erwarten.
        return tempowahl.auf_stufe(sum(faktoren) / len(faktoren))
    if gewaehlt != laeufe.TEMPO_OPTIMAL:
        return _median(faktoren)
    bester, _punkte = tempowahl.zusammengelegt(gelernt)
    return bester if bester is not None else _median(faktoren)


def kreuzvalidiere(
    verzeichnis: Path, datenverzeichnis: Path, auftrag: dict[str, Any], bericht: Bericht
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Sechs Trainings, sechs Messungen - und was das Endmodell daraus mitnimmt.

    Danach ist jede Aufnahme einmal von einem Modell gehört worden, das sie
    nicht kannte. Nach jeder Faltung wird sofort weggeräumt.
    """
    from .bewerten import bewerte_faltung

    zeilen: list[dict[str, Any]] = []
    gelernt: list[dict[str, Any]] = []

    gewaehlt = laeufe.tempowahl_aus(auftrag)
    for faltung in range(laeufe.FALTUNGEN):
        bericht.faltung(faltung)
        bericht.sage(f"── Faltung {faltung + 1} von {laeufe.FALTUNGEN}")
        gewichte, ergebnis, kennzahlen = trainiere_geduldig(
            verzeichnis, datenverzeichnis, bericht, faltung=faltung
        )
        ct2 = verzeichnis / laeufe.GEWICHTE / f"ct2-faltung-{faltung}"
        wandle_um(gewichte, ct2, bericht)
        zeilen.extend(
            bewerte_faltung(
                verzeichnis,
                datenverzeichnis,
                ct2,
                auftrag,
                faltung,
                bericht,
                # Das Tempo dieser Faltung - gemessen wird, wie gelernt wurde.
                faktor=float(kennzahlen["tempo"]),
            )
        )
        gelernt.append({**kennzahlen, "faltung": faltung, "abschluss": ergebnis.als_dict()})
        if gewaehlt != laeufe.TEMPO_AUS:
            # Nach jeder Faltung der vorläufige Wert, als solcher markiert.
            bericht.merke(
                tempo=_gewaehltes_tempo(gelernt, auftrag),
                tempo_endgueltig=False,
            )
        # Sofort: Die nächste Faltung braucht Platte und Karte.
        raeume_karte(bericht)
        shutil.rmtree(gewichte.parent, ignore_errors=True)
        shutil.rmtree(verzeichnis / laeufe.ARBEITSSTAND / _name_fuer(faltung), ignore_errors=True)

    mitgenommen = {
        "durchgaenge": _median([float(k["durchgaenge"]) for k in gelernt]),
        # Der Horizont der Lernrate, damit das Endmodell auf derselben Rampe läuft.
        "plan": _median([float(k["plan_durchgaenge"]) for k in gelernt]),
        "alpha": _median([k["alpha"] for k in gelernt if k["alpha"] is not None]),
        # Beim Suchen das Minimum der zusammengelegten Kurve (`_gewaehltes_tempo`).
        "tempo": _gewaehltes_tempo(gelernt, auftrag),
        # Die gemittelte Kurve samt Standardfehler je Stützstelle.
        "tempokurve": tempowahl.zusammengelegt(gelernt)[1],
        "faltungen": gelernt,
    }
    bericht.sage(
        f"Aus den Faltungen: {mitgenommen['durchgaenge']:.1f} Durchgänge"
        + (f", α = {mitgenommen['alpha']:.2f}" if mitgenommen["alpha"] is not None else "")
        + (
            f", Tempo = {mitgenommen['tempo']:.2f}"
            if gewaehlt != laeufe.TEMPO_AUS and mitgenommen["tempo"] is not None
            else ""
        )
    )
    bericht.ereignis(
        art="kreuzvalidierung",
        faltungen=laeufe.FALTUNGEN,
        zeilen=len(zeilen),
        durchgaenge=mitgenommen["durchgaenge"],
        alpha=mitgenommen["alpha"],
        tempo=mitgenommen["tempo"],
    )
    if gewaehlt != laeufe.TEMPO_AUS and mitgenommen["tempo"] is not None:
        # Jetzt endgültig - der Wert des Endmodells.
        bericht.merke(tempo=float(mitgenommen["tempo"]), tempo_endgueltig=True)
    return zeilen, mitgenommen


def pruefe_karte(datenverzeichnis: Path, auftrag: dict[str, Any], bericht: Bericht) -> None:
    """Vor dem Lauf: Ollama entladen, die Karte melden, auf genug Platz warten."""
    from apps.lernen.backend.config import einstellungen

    konfiguration = einstellungen()
    bericht.stufe("karte")
    karte.entlade_ollama(konfiguration.ollama_url, bericht)
    diese = melde_karte(datenverzeichnis, bericht)
    if diese is None:
        return
    bedarf = kartenplan.bedarf_mb(
        laeufe.kurzname(str(auftrag["basismodell"])), str(auftrag["methode"])
    )
    karte.warte_auf_platz(bedarf, frei_mb, bericht)


class Angehalten(BaseException):
    """Der Läufer hat angehalten (`laeufer._fuehre_aus`, SIGTERM).

    Eine `BaseException`, damit kein `except Exception` unterwegs (etwa
    `karte.mit_geduld`) das Anhalten schluckt.
    """


def _halt_bei_sigterm(_signal: int, _rahmen: object) -> None:
    raise Angehalten


def main(argumente: list[str]) -> int:
    signal.signal(signal.SIGTERM, _halt_bei_sigterm)
    if argumente == ["--karte"]:
        from apps.lernen.backend.config import einstellungen

        diese = melde_karte(einstellungen().data_dir)
        print(f"Karte gemeldet: {diese.name}, {diese.speicher_mb:.0f} MB" if diese else "Keine Karte.")
        return 0
    if len(argumente) != 1:
        print(__doc__)
        return 2

    verzeichnis = Path(argumente[0]).resolve()
    auftrag = laeufe.lies_json(verzeichnis / laeufe.AUFTRAG)
    if auftrag is None:
        print(f"Kein Auftrag in {verzeichnis}")
        return 2

    # `data/snapshots/<job_id>/` - zwei Ebenen hoch liegt das Datenverzeichnis.
    datenverzeichnis = verzeichnis.parents[1]
    bericht = Bericht(verzeichnis)
    begonnen = time.monotonic()

    try:
        pruefe_karte(datenverzeichnis, auftrag, bericht)

        # Beim Kern zuerst die Wahl - erst danach steht fest, worauf gelernt wird.
        from .bewerten import vervollstaendige_kern

        vervollstaendige_kern(verzeichnis, datenverzeichnis, auftrag, bericht)

        # Erst die Messung, dann der Stand, der ausgeliefert wird.
        zeilen, mitgenommen = kreuzvalidiere(verzeichnis, datenverzeichnis, auftrag, bericht)

        bericht.faltung(None)
        bericht.sage("── Endmodell: lernt auf allem, was da ist")
        gewichte, ergebnis, kennzahlen = trainiere_geduldig(
            verzeichnis, datenverzeichnis, bericht, faltung=None, vorgaben=mitgenommen
        )

        from .bewerten import gib_frei

        version = gib_frei(
            verzeichnis, datenverzeichnis, gewichte, auftrag, bericht, ergebnis,
            zeilen=zeilen, mitgenommen=mitgenommen, zuschnitt=kennzahlen.get("zuschnitt"),
        )
    except Angehalten:
        bericht.sage("Angehalten auf Wunsch.")
        bericht.abgebrochen()
        return 3
    except Exception as ursache:  # noqa: BLE001 - was immer torch wirft
        import traceback

        traceback.print_exc()
        bericht.gescheitert(f"{type(ursache).__name__}: {ursache}")
        return 1
    finally:
        # Auf jedem Weg - sonst füllen gescheiterte Läufe die Platte. Einen
        # erschlagenen Prozess übernimmt der Läufer (`laeufer.einmal`).
        entfernt = laeufe.raeume_zwischenstaende_auf(verzeichnis)
        if entfernt:
            bericht.sage(f"Aufgeräumt: {', '.join(entfernt)}")

    bericht.sage(f"Fertig in {(time.monotonic() - begonnen) / 60:.1f} Minuten: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
