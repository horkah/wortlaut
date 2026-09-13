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
import math
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from wortlaut import laeufe

from . import abschluss as abschlussrechnung
from . import klangwandel
from .daten import Proben, Stapler, zeilen_fuer

REZEPTE = Path(__file__).parent / "rezepte"
# Der Keim des Laufs. Er steht hier und nicht nur in den Trainerargumenten,
# weil ihn seit der Augmentierung zwei Seiten brauchen: der Trainer für seine
# Startgewichte und der Wandler für seinen Würfel (`klangwandel.py`).
KEIM = 20260912
# Wie oft eine Zeile in die Lernkurve geschrieben wird. Jeder Schritt wäre bei
# tausend Schritten eine tausendzeilige Datei, die die Oberfläche im Takt
# einliest; alle zehn genügt für eine Kurve, die man ansieht.
LOG_ALLE = 10

# Wie viel eines Laufs höchstens Warmlauf sein darf. Der Wert im Rezept steht
# als Schrittzahl da und passt für einen Korpus mit hunderten Proben; bei einem
# sehr kleinen wäre der Warmlauf länger als der ganze Lauf (siehe `trainiere`).
WARMLAUF_ANTEIL = 0.2


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
            # Nur die Prüfung je Durchgang gehört in die Kurve. Der Abschluss
            # misst danach noch mehrfach am selben Schritt (siehe
            # `abschluss.py`) - unter eigenem Präfix, und daran ist er hier zu
            # erkennen. Ohne diese Zeile stünde ein halbes Dutzend Punkte
            # übereinander, alle mit Verlust null.
            if "eval_loss" not in metrics:
                return
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


def trainiere(
    verzeichnis: Path, datenverzeichnis: Path, bericht: Bericht
) -> tuple[Path, abschlussrechnung.Ergebnis]:
    """Das Training selbst; gibt die fertigen Gewichte und den Abschluss zurück.

    Der Abschluss ist die dritte Achse eines Laufs (`abschluss.py`): was mit
    den Gewichten geschieht, wenn die Schleife durch ist. Er steht im Auftrag,
    und ohne Angabe ist er `bester` - das Verfahren von vorher.
    """
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
    # Vor dem Laden geprüft und nicht erst am Ende gebraucht: Ein Tippfehler im
    # Auftrag soll in Sekunden auffallen und nicht nach zwei Stunden Rechnen.
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
    # Der Wandler steht **nur** an den Lernproben. Die Validierung steuert den
    # Lauf - sie sagt, welcher Durchgang der beste war und welches α gewinnt;
    # eine Validierung, die in jedem Durchgang anders klingt, misst den Würfel
    # statt das Modell (siehe `klangwandel.py`).
    wandler = klangwandel.Wandler(
        stufe=abwandlung,
        einstellungen=klangwandel.einstellungen_aus(rezept),
        keim=KEIM,
    )
    lern = Proben(
        zeilen_fuer(verzeichnis, {laeufe.TRAIN}), korpuswurzel, ausleser, zerteiler, wandler
    )
    pruef = Proben(
        zeilen_fuer(verzeichnis, {laeufe.VALIDIERUNG}), korpuswurzel, ausleser, zerteiler
    )
    bericht.sage(f"Proben: {len(lern)} zum Lernen, {len(pruef)} zum Steuern")
    if wandler.taetig:
        bericht.sage(f"Augmentierung: {abwandlung} (nur auf den Lernproben)")
    if not len(lern):
        raise RuntimeError("Das Manifest enthält keine Trainingsprobe.")

    # Ohne Validierungsproben lässt sich nicht sagen, welcher Durchgang der
    # beste war - dann bleibt nur der letzte, und die Zahl der Durchgänge ist
    # wieder eine Wette. Das trifft nur sehr kleine Korpora; ab einem Dutzend
    # Aufnahmen gibt es eine Validierung (siehe `wortlaut/laeufe.py`).
    hat_pruefung = len(pruef) > 0

    # Wie viele Durchgänge, und wann Schluss ist.
    #
    # `geduldig` braucht eine Validierung: Ohne sie gibt es nichts, woran „wird
    # nicht mehr besser" zu erkennen wäre. Ein zu kleiner Korpus fällt deshalb
    # auf `fest` zurück und bekommt es gesagt - weiterzulaufen, bis irgendetwas
    # passiert, wäre kein Verfahren, sondern eine Hoffnung.
    geduldig = dauer == laeufe.DAUER_GEDULDIG and hat_pruefung
    if dauer == laeufe.DAUER_GEDULDIG and not hat_pruefung:
        bericht.sage(
            "Geduldig nicht möglich: Ohne Validierungsproben gibt es kein "
            "Kriterium. Es gilt die feste Zahl Durchgänge."
        )
    durchgaenge = float(
        rezept.get("epochen_hoechstens", rezept["epochen"]) if geduldig else rezept["epochen"]
    )

    # Der Warmlauf, gedeckelt auf einen Anteil des Laufs.
    #
    # Er stand bisher als feste Schrittzahl im Rezept, und das ging bei jedem
    # Korpus gut, der groß genug war. Bei einem sehr kleinen ging es schief:
    # Neun Aufnahmen ergaben 24 Schritte bei einem Warmlauf von 50 - die
    # Lernrate erreichte nie mehr als die Hälfte ihres Wertes, der ganze Lauf
    # war Rampe. Gemessen an Schritt 20: 3,2e-4 statt 1e-3.
    #
    # Der Deckel greift nur dort. Ein Lauf über 396 Schritte behält seine 50
    # (20 % wären 79), er rechnet also Gewicht für Gewicht wie vorher.
    je_durchgang = max(
        1, math.ceil(len(lern) / (int(rezept["stapel"]) * int(rezept["akkumulation"])))
    )
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

    ausgabe = verzeichnis / laeufe.ARBEITSSTAND
    argumente = Seq2SeqTrainingArguments(
        output_dir=str(ausgabe),
        per_device_train_batch_size=int(rezept["stapel"]),
        per_device_eval_batch_size=int(rezept["stapel"]),
        gradient_accumulation_steps=int(rezept["akkumulation"]),
        learning_rate=float(rezept["lernrate"]),
        warmup_steps=warmlauf,
        num_train_epochs=durchgaenge,
        weight_decay=float(rezept.get("gewichtsverfall", 0.0)),
        max_grad_norm=float(rezept.get("gradientenbegrenzung", 1.0)),
        fp16=bool(rezept.get("fp16", True)) and torch.cuda.is_available(),
        logging_steps=LOG_ALLE,
        # Je Durchgang einmal prüfen - das ist der Takt, in dem die zweite
        # Kurve entsteht. Fehlt die Validierung (zu kleiner Korpus), gibt es
        # nichts zu prüfen und der Lauf läuft ohne sie durch.
        eval_strategy="epoch" if hat_pruefung else "no",
        # Je Durchgang sichern und am Ende den **besten** nehmen, nicht den
        # letzten.
        #
        # Das ist die wichtigste Zeile dieses Rezepts. Bei wenigen hundert
        # kurzen Sätzen dreht die Validierungskurve irgendwo in der Mitte und
        # steigt danach wieder: Das Modell lernt die Trainingssätze auswendig.
        # Wer den letzten Durchgang nimmt, liefert genau dieses Modell aus -
        # und die Zahl der Durchgänge im Rezept wird zu einer Wette, die man
        # je Korpus neu abschließen müsste. So ist sie nur noch eine
        # Obergrenze: Es wird ausgeliefert, was auf der Validierung am besten
        # war, und zu lange zu trainieren kostet Rechenzeit statt Güte.
        #
        # `save_total_limit=1` hält den Platzbedarf in Grenzen - zusammen mit
        # dem besten liegen höchstens zwei Zwischenstände auf der Platte, beim
        # vollen Training je knapp drei Gigabyte. Sie verschwinden mit dem
        # `arbeitsstand`, sobald der Lauf endet - durchgelaufen oder
        # gescheitert (siehe `main`).
        #
        # Wer mittelt, braucht mehr davon: Ein Zwischenstand, den der Trainer
        # schon weggeräumt hat, lässt sich nicht mehr wiegen. Dafür fällt dann
        # der Optimierer aus den Sicherungen (`save_only_model`) - er wiegt
        # zwei Drittel eines Zwischenstandes, und dieses Projekt setzt einen
        # Lauf nie fort. Ohne Mittelung bleibt beides, wie es war.
        save_strategy="epoch" if hat_pruefung else "no",
        save_total_limit=abschlussrechnung.zu_behalten(art, rezept),
        save_only_model=laeufe.mittelt(art),
        load_best_model_at_end=hat_pruefung,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        # Der Bericht ist der einzige Draht nach draußen; Tensorboard und
        # dergleichen schrieben ins Leere.
        report_to=[],
        # Vier Ladefäden je Karte wären hier Verwaltungsaufwand ohne Nutzen:
        # Eine kurze WAV-Datei zu lesen dauert weniger als ein Schritt.
        dataloader_num_workers=2,
        remove_unused_columns=False,
        label_names=["labels"],
        seed=KEIM,
    )

    rueckrufe = [_rueckmeldung(bericht)]
    if geduldig:
        from transformers import EarlyStoppingCallback

        geduld = int(rezept.get("geduld", 5))
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
    )

    bericht.stufe("training")
    trainer.train()

    # Ob die Geduld gereicht hat oder die Obergrenze gebunden hat. Das ist die
    # Auskunft, die dem Lauf von Femke gefehlt hat: Eine Kurve, die am Ende
    # noch fällt, sieht aus wie eine, die fertig ist.
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
        # Sichtbar machen, welcher Durchgang gewonnen hat: Steht er weit vor
        # dem letzten, war die Obergrenze zu hoch angesetzt - und das ist eine
        # Auskunft über das Rezept, nicht über diesen einen Lauf.
        bericht.sage(
            f"Bester Durchgang: {Path(trainer.state.best_model_checkpoint).name} "
            f"· Validierungsverlust {trainer.state.best_metric:.5f}"
        )
        bericht.ereignis(
            art="bester",
            schritt=int(Path(trainer.state.best_model_checkpoint).name.rsplit("-", 1)[-1]),
            verlust=round(float(trainer.state.best_metric), 5),
        )

    # Der Abschluss: Was jetzt noch mit den Gewichten geschieht, bevor sie
    # gesichert werden. Bei `bester` geschieht nichts - dann steht hier
    # derselbe Stand wie vor dieser Zeile (siehe `abschluss.py`).
    ergebnis = abschlussrechnung.fuehre_aus(
        art=art,
        modell=modell,
        trainer=trainer,
        rezept=rezept,
        basismodell=basismodell,
        arbeitsstand=ausgabe,
        hat_pruefung=hat_pruefung,
        bericht=bericht,
    )

    bericht.stufe("sichern")
    gewichte = verzeichnis / laeufe.GEWICHTE
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
    return gewichte, ergebnis


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
        gewichte, ergebnis = trainiere(verzeichnis, datenverzeichnis, bericht)

        from .bewerten import bewerte_und_gib_frei

        version = bewerte_und_gib_frei(
            verzeichnis, datenverzeichnis, gewichte, auftrag, bericht, ergebnis
        )
    except Exception as ursache:  # noqa: BLE001 - was immer torch wirft
        import traceback

        traceback.print_exc()
        bericht.gescheitert(f"{type(ursache).__name__}: {ursache}")
        return 1
    finally:
        # Auf beiden Wegen, und deshalb hier und nicht am Ende des guten. Ein
        # gescheiterter Lauf ließ bis eben den halben Arbeitsstand samt
        # Optimierer liegen - beim vollen Training knapp drei Gigabyte, die
        # niemand mehr liest und die niemand wegräumt, eben weil der Lauf
        # schiefging. Nach genügend Fehlläufen ist die Platte voll, und dann
        # scheitert auch der gesunde Lauf.
        #
        # Was ein `finally` nicht kann, ist der erschlagene Prozess: kein
        # Python läuft mehr, das hier ankäme. Diesen Fall nimmt der Läufer
        # (`laeufer.einmal`), der den Unterprozess überlebt.
        entfernt = laeufe.raeume_zwischenstaende_auf(verzeichnis)
        if entfernt:
            bericht.sage(f"Aufgeräumt: {', '.join(entfernt)}")

    bericht.sage(f"Fertig in {(time.monotonic() - begonnen) / 60:.1f} Minuten: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
