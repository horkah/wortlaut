"""Ein Trainingslauf - das, was auf der Karte passiert.

    python -m apps.lernen.training.finetune data/snapshots/job_01J8…

Aufgerufen vom Läufer (`laeufer.py`), der die Warteschlange beobachtet. Das
Argument ist ein Laufverzeichnis (`wortlaut/laeufe.py`): Darin steht der
Auftrag, darin steht das Manifest, und dorthin wird geschrieben, was daraus
wird.

**Warum ein eigener Prozess je Lauf.** Ein Feintuning belegt Speicher auf der
Karte, und PyTorch gibt ihn nach einem Abbruch nicht immer zuverlässig zurück.
Ein Prozess, der endet, gibt alles zurück - das ist der einzige Aufräumweg, auf
den man sich verlassen kann. Außerdem überlebt der Läufer damit einen Lauf, der
sich an einem kaputten Modell verschluckt.

**Wem `zustand.json` gehört.** Diesem Prozess, und nur ihm. Der Läufer schreibt
darin ausschließlich dann, wenn dieser Prozess gestorben ist, ohne etwas zu
sagen - sonst gäbe es zwei Schreiber und irgendwann einen Zustand, der von
beiden halb stammt.

**Was hier nicht entschieden wird.** Die Aufteilung in Lernen und Prüfen (die
steht im Manifest) und die Zahlen des Rezepts (die stehen in `rezepte/`). Diese
Datei setzt zusammen; sie hat keine eigene Meinung, die sich nicht ändern ließe,
ohne sie anzufassen.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from wortlaut import laeufe

from .daten import Proben, Stapler, zeilen_fuer

REZEPTE = Path(__file__).parent / "rezepte"
# Wie oft eine Zeile in die Lernkurve geschrieben wird. Jeder Schritt wäre bei
# tausend Schritten eine tausendzeilige Datei, die die Oberfläche im Takt
# einliest; alle zehn genügt für eine Kurve, die man ansieht.
LOG_ALLE = 10


def _rezeptpfad(methode: str) -> Path:
    return REZEPTE / f"whisper_{methode}.yaml"


class Bericht:
    """Der Draht nach draußen: Zustand, Fortschritt, Protokoll.

    Alles, was dieser Prozess über sich sagt, geht durch dieses Objekt. Eine
    Stelle, damit der Zustand nie halb geschrieben ist und die Oberfläche nie
    raten muss, was gerade läuft.
    """

    def __init__(self, verzeichnis: Path) -> None:
        self.verzeichnis = verzeichnis
        self.zustand: dict[str, Any] = {
            "status": laeufe.LAEUFT,
            "stufe": "vorbereiten",
            "begonnen": laeufe.jetzt(),
        }
        self._schreibe()

    def _schreibe(self) -> None:
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
        laeufe.haenge_an(
            self.verzeichnis / laeufe.FORTSCHRITT, {"zeit": laeufe.jetzt(), **felder}
        )

    def schritt(self, schritt: int, gesamt: int) -> None:
        """Der Balken. Im Zustand und nicht nur im Fortschritt: Die Liste der
        Läufe zeigt ihn, und sie soll dafür keine tausendzeilige Datei lesen."""
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

    def gescheitert(self, grund: str) -> None:
        self.zustand.update(
            {"status": laeufe.GESCHEITERT, "stufe": "", "beendet": laeufe.jetzt(), "fehler": grund}
        )
        self._schreibe()
        self.ereignis(art="fehler", text=grund)


def _rueckmeldung(bericht: Bericht):
    """Ein Trainer-Rückruf, der aus Verlusten eine Kurve macht.

    Innen definiert, weil er `transformers` braucht - und das soll erst geladen
    werden, wenn wirklich trainiert wird. Ein Import von torch kostet Sekunden
    und mehrere hundert Megabyte; ein Läufer, der nur wartet, soll ihn nicht
    bezahlen.
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
            bericht.ereignis(
                art="validierung",
                schritt=int(zustand.global_step),
                epoche=round(float(zustand.epoch or 0.0), 3),
                verlust=round(float(metrics.get("eval_loss", 0.0)), 5),
            )

    return Kurve()


def _trainerklasse():
    """Ein Trainer, der Proben nach ihrem Gewicht zählt.

    Korrekturen aus „schreiben" sind schwächere Daten: Ihr Text ist keine
    Vorgabe, sondern eine vom Menschen abgenickte Maschinenausgabe. Sie
    gleichrangig einzuspeisen hieße, dem Modell seine eigenen Fehler
    anzutrainieren. Das Gewicht steht je Zeile im Manifest; hier wird es
    angewandt - der Verlust je Probe mal ihr Gewicht, dann gemittelt.

    Das geht nicht ohne eigene Verlustrechnung: Der Trainer von `transformers`
    mittelt über alle Marken des Stapels und kennt keine Proben.
    """
    import torch
    from transformers import Seq2SeqTrainer

    class GewichtetesTraining(Seq2SeqTrainer):
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
            # Je Probe: Summe der Markenverluste geteilt durch ihre Markenzahl.
            # Ohne das zählte ein langer Satz mehr als ein kurzer, und das
            # Gewicht aus dem Manifest ginge darin unter.
            je_probe = (je_marke * gilt).sum(dim=1) / gilt.sum(dim=1).clamp(min=1)
            gewichte = gewichte.to(je_probe.device, je_probe.dtype)
            verlust = (je_probe * gewichte).sum() / gewichte.sum().clamp(min=1e-8)
            return (verlust, ausgabe) if return_outputs else verlust

    return GewichtetesTraining


def trainiere(verzeichnis: Path, datenverzeichnis: Path, bericht: Bericht) -> Path:
    """Das Training selbst; gibt das Verzeichnis mit den fertigen Gewichten zurück."""
    import torch
    from transformers import (
        Seq2SeqTrainingArguments,
        WhisperFeatureExtractor,
        WhisperForConditionalGeneration,
        WhisperTokenizerFast,
    )
    from wortlaut import corpus

    auftrag = laeufe.lies_json(verzeichnis / laeufe.AUFTRAG) or {}
    methode = str(auftrag["methode"])
    basismodell = str(auftrag["basismodell"])
    sprecher_id = str(auftrag["sprecher_id"])
    rezept = yaml.safe_load(_rezeptpfad(methode).read_text(encoding="utf-8"))

    bericht.stufe("laden")
    bericht.sage(f"Rezept: {rezept['name']} · Grundmodell: {basismodell}")

    # Die Sprache steht im Korpus; hier genügt, dass sie fest gesetzt ist:
    # Ein Modell, das die Sprache erst erkennen muss, verschenkt bei kurzen
    # Sätzen Genauigkeit an eine Frage, deren Antwort feststeht.
    sprache = str(auftrag.get("sprache") or "de")
    ausleser = WhisperFeatureExtractor.from_pretrained(basismodell)
    # Ausdrücklich der schnelle Zerteiler, und das ist keine
    # Geschwindigkeitsfrage: Nur er schreibt beim Sichern eine `tokenizer.json`,
    # und genau diese Datei sucht faster-whisper später neben dem umgewandelten
    # Modell. Fehlt sie, lädt es still den Zerteiler von `whisper-tiny` und
    # liefert Text, der aussieht, als hätte das Training nichts gebracht.
    zerteiler = WhisperTokenizerFast.from_pretrained(
        basismodell, language=sprache, task="transcribe"
    )
    modell = WhisperForConditionalGeneration.from_pretrained(basismodell)

    # Whisper bringt „erzwungene" Marken für Sprache und Aufgabe mit. Beim
    # Feintuning stören sie: Sie stehen schon in den Marken des Zerteilers, und
    # doppelt gesetzt lernt das Modell eine Folge, die es nie erzeugen soll.
    modell.generation_config.language = sprache
    modell.generation_config.task = "transcribe"
    modell.generation_config.forced_decoder_ids = None
    modell.config.forced_decoder_ids = None

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
        )
        trainierbar = sum(p.numel() for p in modell.parameters() if p.requires_grad)
        gesamt = sum(p.numel() for p in modell.parameters())
        bericht.sage(f"LoRA: {trainierbar:,} von {gesamt:,} Gewichten werden gelernt")

    korpuswurzel = datenverzeichnis / corpus.sprecher_relpfad(sprecher_id)
    lern = Proben(zeilen_fuer(verzeichnis, {laeufe.TRAIN}), korpuswurzel, ausleser, zerteiler)
    pruef = Proben(
        zeilen_fuer(verzeichnis, {laeufe.VALIDIERUNG}), korpuswurzel, ausleser, zerteiler
    )
    bericht.sage(f"Proben: {len(lern)} zum Lernen, {len(pruef)} zum Steuern")
    if not len(lern):
        raise RuntimeError("Das Manifest enthält keine Trainingsprobe.")

    ausgabe = verzeichnis / "arbeitsstand"
    argumente = Seq2SeqTrainingArguments(
        output_dir=str(ausgabe),
        per_device_train_batch_size=int(rezept["stapel"]),
        per_device_eval_batch_size=int(rezept["stapel"]),
        gradient_accumulation_steps=int(rezept["akkumulation"]),
        learning_rate=float(rezept["lernrate"]),
        warmup_steps=int(rezept["warmlauf_schritte"]),
        num_train_epochs=float(rezept["epochen"]),
        weight_decay=float(rezept.get("gewichtsverfall", 0.0)),
        max_grad_norm=float(rezept.get("gradientenbegrenzung", 1.0)),
        fp16=bool(rezept.get("fp16", True)) and torch.cuda.is_available(),
        logging_steps=LOG_ALLE,
        # Je Durchgang einmal prüfen - das ist der Takt, in dem die zweite
        # Kurve entsteht. Fehlt die Validierung (zu kleiner Korpus), gibt es
        # nichts zu prüfen und der Lauf läuft ohne sie durch.
        eval_strategy="epoch" if len(pruef) else "no",
        save_strategy="no",
        # Der Bericht ist der einzige Draht nach draußen; Tensorboard und
        # dergleichen schrieben ins Leere.
        report_to=[],
        # Vier Ladefäden je Karte wären hier Verwaltungsaufwand ohne Nutzen:
        # Eine kurze WAV-Datei zu lesen dauert weniger als ein Schritt.
        dataloader_num_workers=2,
        remove_unused_columns=False,
        label_names=["labels"],
        seed=20260912,
    )

    trainer = _trainerklasse()(
        model=modell,
        args=argumente,
        train_dataset=lern,
        eval_dataset=pruef if len(pruef) else None,
        data_collator=Stapler(zerteiler),
        callbacks=[_rueckmeldung(bericht)],
    )

    bericht.stufe("training")
    trainer.train()

    bericht.stufe("sichern")
    gewichte = verzeichnis / "gewichte"
    if methode == laeufe.LORA:
        # Zusammengerechnet und nicht als Zusatz gespeichert: Was danach kommt,
        # ist die Umwandlung nach CTranslate2, und die kennt kein LoRA. Ein
        # Modell, das nur mit peft zu laden wäre, könnte „schreiben" nicht
        # benutzen - und dann wäre der ganze Lauf ohne Ziel.
        modell = modell.merge_and_unload()
    modell.save_pretrained(gewichte, safe_serialization=True)
    # Zerteiler und Merkmalsausleser daneben: Die Umwandlung nimmt beide mit
    # (siehe `wandle_um`), und ohne sie ist der Stand kein vollständiges Modell,
    # sondern ein Satz Gewichte.
    zerteiler.save_pretrained(gewichte)
    ausleser.save_pretrained(gewichte)
    return gewichte


# Was neben den umgewandelten Gewichten liegen muss, damit faster-whisper den
# Stand wirklich laden kann. Der Zerteiler ist der wichtigere der beiden: Fehlt
# `tokenizer.json`, greift faster-whisper still auf den von `whisper-tiny`
# zurück - kein Fehler, keine Warnung, nur schlechterer Text.
BEIZULEGEN = ["tokenizer.json", "preprocessor_config.json"]


def wandle_um(gewichte: Path, ziel: Path, bericht: Bericht) -> None:
    """Nach CTranslate2 - das Format, das faster-whisper lädt.

    Ohne diesen Schritt wäre der Stand ein Verzeichnis voller Gewichte, das
    niemand in diesem Projekt benutzen kann: „schreiben" und die Auswertung
    laufen beide über faster-whisper (siehe `wortlaut/whisper/local.py`).
    """
    from ctranslate2.converters import TransformersConverter

    bericht.stufe("umwandeln")
    fehlend = [name for name in BEIZULEGEN if not (gewichte / name).is_file()]
    if fehlend:
        # Lieber hier abbrechen als einen Stand ausliefern, der mit dem
        # falschen Zerteiler arbeitet: Der Fehler wäre sonst erst am Ergebnis
        # zu sehen, und dort sähe er aus wie ein misslungenes Training.
        raise RuntimeError(f"Zum Umwandeln fehlt: {', '.join(fehlend)}")

    TransformersConverter(
        str(gewichte), copy_files=BEIZULEGEN, load_as_float16=True
    ).convert(str(ziel), quantization="float16", force=True)


def main(argumente: list[str]) -> int:
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
        gewichte = trainiere(verzeichnis, datenverzeichnis, bericht)

        from .bewerten import bewerte_und_gib_frei

        version = bewerte_und_gib_frei(
            verzeichnis, datenverzeichnis, gewichte, auftrag, bericht
        )
    except Exception as ursache:  # noqa: BLE001 - was immer torch wirft
        import traceback

        traceback.print_exc()
        bericht.gescheitert(f"{type(ursache).__name__}: {ursache}")
        return 1

    bericht.sage(f"Fertig in {(time.monotonic() - begonnen) / 60:.1f} Minuten: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
