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

import gc
import json
import math
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from wortlaut import laeufe, sprachen, stille, tempo, vorbereitung

from . import abschluss as abschlussrechnung
from . import tempowahl
from . import klangwandel
from .daten import Proben, Stapler, zeilen_fuer_faltung

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


def _rezept_fuer(methode: str, basismodell: str) -> dict[str, Any]:
    """Das Rezept dieser Methode, mit den Abweichungen dieses Grundmodells darüber.

    Ein Rezept je Methode und nicht je Kombination: Lernrate, Durchgänge und
    LoRA-Rang hängen daran, wie trainiert wird, nicht woran. Was am Grundmodell
    hängt, ist der Platz auf der Karte - `medium` ist dreimal so groß wie
    `small`, und derselbe Stapel passt nicht mehr. Genau dafür steht
    `je_grundmodell` in der YAML-Datei, und nur dafür.
    """
    rezept = yaml.safe_load(_rezeptpfad(methode).read_text(encoding="utf-8"))
    abweichungen = (rezept.get("je_grundmodell") or {}).get(laeufe.kurzname(basismodell), {})
    return {**rezept, **abweichungen}


class Bericht:
    """Der Draht nach draußen: Zustand, Fortschritt, Protokoll.

    Alles, was dieser Prozess über sich sagt, geht durch dieses Objekt. Eine
    Stelle, damit der Zustand nie halb geschrieben ist und die Oberfläche nie
    raten muss, was gerade läuft.
    """

    def __init__(self, verzeichnis: Path, spuren: bool = True) -> None:
        self.verzeichnis = verzeichnis
        # **Ohne Spuren redet dieser Bericht nur.** Ein Lauf, der nachgezogen
        # wird (`nachziehen.py`), rührt den alten Lauf nicht an: Der ist fertig
        # und bleibt es, seine Kurven gehören zu den Faltungen von damals, und
        # ein zweites Training darübergeschrieben wäre eine Kurve, die zwei
        # Läufe zeigt und keinen erklärt.
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

        Für das, was ein Lauf **herausgefunden** hat und nicht bloß tut: die
        gewählte Geschwindigkeit etwa. Im Zustand und nicht nur im Fortschritt,
        weil die Liste es neben jedem Lauf zeigt und dafür keine
        tausendzeilige Datei lesen soll - dieselbe Überlegung wie bei
        `faltung`.
        """
        self.zustand.update(felder)
        self._schreibe()

    def faltung(self, nummer: int | None) -> None:
        """Welche der sieben Trainings gerade läuft - für den Balken der Liste.

        `None` ist das Endmodell. Es steht im Zustand und nicht nur im
        Fortschritt, weil die Übersicht es zeigt und dafür keine
        tausendzeilige Datei lesen soll.
        """
        self.zustand["faltung"] = nummer
        self.zustand["faltungen_gesamt"] = laeufe.FALTUNGEN
        self.zustand["schritt"] = 0
        self._schreibe()
        self.ereignis(art="faltung", nummer=nummer)

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


def _name_fuer(faltung: int | None) -> str:
    """Wie das Verzeichnis einer Faltung heißt - `endmodell`, wenn keine."""
    return "endmodell" if faltung is None else f"faltung-{faltung}"


def _halt_nach(ziel: float, bericht):
    """Ein Rückruf, der nach `ziel` Durchgängen Schluss macht - Plan unberührt.

    Das Gegenstück zum frühen Abbruch der Faltungen, nur ohne Kriterium: Das
    Endmodell hat nichts zurückgehalten, woran „wird nicht mehr besser" zu
    erkennen wäre. Es weiß aber aus den sechs Läufen davor, **wann** es so weit
    war, und hört genau dort auf - auf derselben Rampe, an derselben Stelle.

    Ein kleineres `num_train_epochs` täte es nicht: Es verschöbe den ganzen
    Lernratenverlauf (siehe `trainiere`). Innen definiert wie `_rueckmeldung`,
    und aus demselben Grund.
    """
    from transformers import TrainerCallback

    class Haltestelle(TrainerCallback):
        def __init__(self) -> None:
            self.gesagt = False

        def on_epoch_end(self, args, zustand, steuerung, **weiteres):
            if float(zustand.epoch or 0.0) >= ziel - 1e-6:
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

    Ohne Steuergröße gibt es keinen besten - dann ist es die Zahl, die gelaufen
    ist. Das trifft nur das Endmodell, und dort ist die Zahl ohnehin von außen
    gesetzt.
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

    **Einmal je Faltung, und einmal für das Endmodell.** `faltung` sagt, welches
    Sechstel des Korpus draußen bleibt: Gelernt wird auf den anderen fünf,
    gesteuert und gemessen auf diesem einen. `faltung = None` ist das
    Endmodell - es lernt auf allem, wird an nichts gemessen und ist der Stand,
    der später in „schreiben" diktiert.

    **`vorgaben` ist das Wissen aus den Faltungen.** Das Endmodell hat keine
    Validierung, kann also weder seine Durchgangszahl noch sein α selbst
    finden. Beides bringt es aus den sechs Läufen davor mit - der Median über
    die Faltungen. Genau dafür ist die Kreuzvalidierung da.

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
    # Die eine Kombination, die es nicht gibt - hier noch einmal geprüft und
    # nicht nur in der API. Ein Auftrag kann von Hand im Verzeichnis liegen,
    # und zwei Stunden zu rechnen, um dann am Speicher zu scheitern, ist die
    # schlechteste aller Auskünfte.
    if methode not in laeufe.methoden_fuer(basismodell):
        raise RuntimeError(
            f"{laeufe.kurzname(basismodell)} lässt sich nur mit "
            f"{', '.join(laeufe.methoden_fuer(basismodell))} trainieren."
        )
    rezept = _rezept_fuer(methode, basismodell)

    bericht.stufe("laden")
    bericht.sage(f"Rezept: {rezept['name']} · Grundmodell: {basismodell}")

    # Die Sprache steht im Korpus; hier genügt, dass sie fest gesetzt ist:
    # Ein Modell, das die Sprache erst erkennen muss, verschenkt bei kurzen
    # Sätzen Genauigkeit an eine Frage, deren Antwort feststeht.
    # Der Rückfall gilt Aufträgen, die älter sind als das Feld - seit
    # `services/auftraege.py` schreibt jeder neue Lauf seine Sprache selbst.
    sprache = str(auftrag.get("sprache") or sprachen.VORGABE)
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

    # Und noch ein Erbstück in derselben Ecke: Die `config.json` von Whisper
    # führt Erzeugungsparameter mit, die dort seit Jahren nicht mehr hingehören
    # - `max_length`, `suppress_tokens`, `begin_suppress_tokens`. Sie stehen
    # richtig in der `generation_config`, und `save_pretrained` räumt sie beim
    # Sichern von selbst um. Dabei warnt es, und zwar bei **jedem**
    # Zwischenstand: Bei sechs Faltungen mit bis zu sechzig Durchgängen ist das
    # ein Protokoll, in dem die Warnung häufiger steht als die Verlustkurve.
    #
    # Schlimmer als laut ist, wie es umräumt: Es setzt den Wert aus der
    # `config` ungeprüft über den der `generation_config`. Bei `small` sind die
    # beiden nicht gleich - dort führt die `config` 86 zu unterdrückende Marken
    # und die `generation_config` 88, und die zwei zusätzlichen sind
    # `<|translate|>` und `<|transcribe|>`. Der ältere, kürzere Stand gewinnt,
    # und die umgewandelten Stände dieses Projekts tragen entsprechend 86.
    #
    # Ausgewirkt hat sich das nie: faster-whisper stellt die Liste bei jedem
    # Aufruf aus dem Zerteiler neu zusammen und übergibt sie ausdrücklich
    # (`get_suppressed_tokens`), womit die Zahl im Stand überschrieben wird -
    # nachgemessen sind es zur Laufzeit 88, beide Marken dabei. Es bleibt
    # trotzdem eine Stelle, an der zwei Quellen dasselbe behaupten sollen und
    # es nicht tun, und die stille Auflösung geht zugunsten der falschen aus.
    #
    # Hier fällt die falsche weg, statt sie zu überschreiben: Was in der
    # `generation_config` steht, ist richtig und bleibt unangetastet.
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
        )
        if rezept.get("gradientensparsam", False):
            # Beim Gradientensparen hängt der Rückwärtsgang an der Eingabe des
            # ersten Blocks. Bei LoRA ist alles davor eingefroren, sie verlangt
            # also keinen Gradienten - und ohne diesen Griff bekommt der Zusatz
            # gar keinen. Das ist der bekannte stille Fehlschlag von LoRA mit
            # Gradientensparen: Es läuft durch und lernt nichts.
            modell.enable_input_require_grads()
        trainierbar = sum(p.numel() for p in modell.parameters() if p.requires_grad)
        gesamt = sum(p.numel() for p in modell.parameters())
        bericht.sage(f"LoRA: {trainierbar:,} von {gesamt:,} Gewichten werden gelernt")

    korpuswurzel = datenverzeichnis / corpus.sprecher_relpfad(sprecher_id)
    # Der Wandler steht **nur** an den Lernproben. Das zurückgehaltene Sechstel
    # steuert den Lauf - es sagt, welcher Durchgang der beste war und welches α
    # gewinnt; eine Steuergröße, die in jedem Durchgang anders klingt, misst
    # den Würfel statt das Modell (siehe `klangwandel.py`).
    wandler = klangwandel.Wandler(
        stufe=abwandlung,
        einstellungen=klangwandel.einstellungen_aus(rezept),
        keim=KEIM + (faltung or 0),
    )
    lernzeilen, messzeilen = zeilen_fuer_faltung(
        verzeichnis, faltung, str(auftrag.get("daten") or laeufe.NUR_ORIGINAL), korpuswurzel
    )
    # Der Tempofaktor steht im Auftrag und nicht im Rezept: Er ist kein
    # Verfahrensparameter, sondern der Zustand, in dem der Korpus betrachtet
    # wird (`services/auftraege.py`). Vorgespult wird beim ersten Zugriff je
    # Datei und dann nicht wieder; das Zwischenlager geht mit dem Lauf.
    faktor = float(auftrag.get("tempo", tempo.VORGABE))
    tempoergebnis: tempowahl.Ergebnis | None = None
    gewaehlt = laeufe.tempowahl_aus(auftrag)

    if gewaehlt == laeufe.TEMPO_GESCHAETZT:
        # Gerechnet und nicht gesucht: aus Textlänge und Aufnahmedauer dieser
        # Faltung. Kostet keine Erkennung (siehe `tempowahl.aus_dauern`).
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
            # Das Endmodell sucht nicht noch einmal: Es übernimmt, worauf sich
            # die sechs Faltungen geeinigt haben - wie bei den Durchgängen und
            # beim α auch.
            faktor = float(vorgaben["tempo"])
            bericht.sage(f"Tempo aus den Faltungen übernommen: Faktor {faktor:g}")
        else:
            # Gesucht wird auf den **Lernzeilen** dieser Faltung. Die Messzeilen
            # anzufassen hieße, die Wahl an Daten zu treffen, an denen später
            # gemessen wird (siehe `tempowahl.py`).
            tempoergebnis = tempowahl.waehle(
                lernzeilen, korpuswurzel, basismodell, sprache, bericht, faltung
            )
            faktor = tempoergebnis.faktor
            if tempoergebnis.hinweis:
                bericht.sage(f"  {tempoergebnis.hinweis}")

    # Ob die Ränder fallen. Fehlt der Schlüssel, ist es ein Auftrag von vor
    # dieser Achse, und dann fällt nichts (`wortlaut/stille.py`).
    schneiden = stille.gilt(auftrag.get("stille"))
    # **Je Zustand ein eigenes Fach.** Der Zwischenspeicher liegt beim Lauf und
    # nicht bei der Faltung, denn zwei Faltungen mit demselben Faktor sollen
    # dieselbe Datei benutzen. Bei `optimal` sucht sich aber **jede Faltung
    # ihren eigenen** Faktor - und fand dann die vorgespulte Datei der Faltung
    # davor vor, die zu einem anderen Faktor gehörte. Sie lernte auf 2,0,
    # während im Protokoll 3,0 stand: der unauffälligste denkbare Fehler.
    zwischenlager = (
        verzeichnis / laeufe.VORGESPULT / vorbereitung.marke(faktor, schneiden)
        if vorbereitung.noetig(faktor, schneiden)
        else None
    )
    if tempo.vorspulen_noetig(faktor):
        bericht.sage(f"Vorgespult: Faktor {faktor:g} - Tonhöhe bleibt")
    if schneiden:
        bericht.sage(
            f"Ränder geschnitten: Stille vorn und hinten weg, {stille.RAND_S:g} s bleiben stehen"
        )

    lern = Proben(
        lernzeilen, korpuswurzel, ausleser, zerteiler, wandler, faktor, zwischenlager, schneiden
    )
    pruef = Proben(
        messzeilen, korpuswurzel, ausleser, zerteiler, None, faktor, zwischenlager, schneiden
    )
    bericht.sage(f"Proben: {len(lern)} zum Lernen, {len(pruef)} zum Steuern")
    if wandler.taetig:
        bericht.sage(f"Augmentierung: {abwandlung} (nur auf den Lernproben)")
    if not len(lern):
        raise RuntimeError("Das Manifest enthält keine Trainingsprobe.")

    # Das Endmodell hat nichts zurückgehalten und damit keine Steuergröße. Es
    # ist nicht das Modell, das beurteilt wird - beurteilt haben die sechs
    # Faltungen davor -, sondern das, das ausgeliefert wird.
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
    # Der **Plan** ist der Horizont, über den die Lernrate läuft; `halt` ist,
    # wo aufgehört wird. Für eine Faltung fallen beide zusammen: Sie plant über
    # ihre Obergrenze und hört auf, wenn die Geduld aufgebraucht ist.
    plan = float(
        rezept.get("epochen_hoechstens", rezept["epochen"]) if geduldig else rezept["epochen"]
    )
    halt: float | None = None
    if vorgaben and vorgaben.get("durchgaenge"):
        # **Das Endmodell übernimmt beides, nicht nur die Zahl.**
        #
        # Es nahm bisher allein die Durchgangszahl mit (den Median des besten
        # Durchgangs der sechs Faltungen) und baute seinen Lernratenplan in
        # genau diesen Horizont neu. Gemessen an einem Lauf vom 13. September:
        # Eine Faltung plante über acht Durchgänge, wärmte 50 Schritte lang an,
        # erreichte ihre Spitze bei Durchgang 2,1 und fiel danach flach ab -
        # ihr bester Stand lag bei Durchgang 2, also gerade am Ende des
        # Warmlaufs. Das Endmodell bekam „2,0 Durchgänge", hatte damit 68
        # Schritte, kürzte den Warmlauf auf 14, war bei Durchgang 0,6 auf der
        # Spitze und bei 1,8 schon wieder bei einem Fünftel davon.
        #
        # Gleiche Epochenzahl, anderer Lauf - und das Ergebnis war ein Stand,
        # der ausfranst: Er erkennt den ersten Satz und redet dann weiter
        # (`docs/lernen.md`). Deshalb erbt das Endmodell jetzt den Horizont der
        # Faltungen und hört an der Stelle auf, an der sie am besten standen.
        # Dieselbe Rampe, dieselbe Neigung, derselbe Punkt darauf.
        plan = float(vorgaben.get("plan") or vorgaben["durchgaenge"])
        halt = float(vorgaben["durchgaenge"])
        geduldig = False
        bericht.sage(
            f"Aus den Faltungen übernommen: Plan über {plan:.1f} Durchgänge, "
            f"Schluss nach {halt:.1f} - derselbe Lernratenverlauf wie dort."
        )
    durchgaenge = plan

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

    # Je Faltung ein eigener Arbeitsstand. Sie liegen nacheinander da und nicht
    # nebeneinander - was eine Faltung hinterlässt, räumt `main` weg, bevor die
    # nächste anfängt (beim vollen Training wären sieben Stände sonst sieben
    # Gigabyte).
    ausgabe = verzeichnis / laeufe.ARBEITSSTAND / _name_fuer(faltung)
    sparsam = bool(rezept.get("gradientensparsam", False))
    argumente = Seq2SeqTrainingArguments(
        output_dir=str(ausgabe),
        per_device_train_batch_size=int(rezept["stapel"]),
        per_device_eval_batch_size=int(rezept["stapel"]),
        gradient_accumulation_steps=int(rezept["akkumulation"]),
        # Aktivierungen nicht aufheben, sondern beim Rückwärtsgang neu rechnen.
        #
        # Rechnerisch ändert das nichts: Es kommen dieselben Gradienten heraus,
        # nur wird der Vorwärtsgang je Block ein zweites Mal ausgeführt, statt
        # seine Zwischenergebnisse aufzuheben. Deshalb ist es keine weitere
        # Achse, sondern eine Frage des Platzes - und steht im Rezept unter
        # `je_grundmodell`, wo die anderen Platzfragen auch stehen.
        #
        # Gemessen an `medium` mit LoRA und Stapel 8: 9,3 GB ohne, 2,3 GB mit.
        # Und entgegen der Erwartung nicht langsamer, sondern schneller (125 ms
        # je Probe ohne, 68 ms mit) - bei 9,3 GB auf einer Karte mit 10,75 GB
        # nutzbarem Speicher stößt der Vorrat von torch dauernd an die Decke
        # und muss beim Treiber nachfordern, und das kostet mehr als die
        # zweite Rechnung. Bei `small` bleibt es aus: Dort ist der Platz nicht
        # knapp, und dann ist die Neuberechnung tatsächlich nur Aufwand.
        gradient_checkpointing=sparsam,
        # Ohne `use_reentrant=False` schweigt torch nicht nur, es warnt bei
        # jedem Schritt - und die ältere Fassung verträgt sich schlecht damit,
        # dass bei LoRA fast alle Gewichte eingefroren sind.
        gradient_checkpointing_kwargs={"use_reentrant": False} if sparsam else None,
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

    rueckrufe: list[Any] = [_rueckmeldung(bericht)]
    if halt is not None:
        rueckrufe.append(_halt_nach(halt, bericht))
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
        alpha_vorgabe=(vorgaben or {}).get("alpha"),
    )

    bericht.stufe("sichern")
    gewichte = verzeichnis / laeufe.GEWICHTE / _name_fuer(faltung)
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

    # Was diese Faltung gelernt hat und das Endmodell später mitnimmt: bei
    # welchem Durchgang sie am besten stand und welches α gewonnen hat.
    kennzahlen: dict[str, Any] = {
        "durchgaenge": _bester_durchgang(trainer, durchgaenge, hat_pruefung),
        # Der Horizont, über den die Lernrate lief. Das Endmodell erbt ihn -
        # ohne ihn wäre „zwei Durchgänge" eine Zahl ohne den Lauf, aus dem sie
        # stammt (siehe oben).
        "plan_durchgaenge": plan,
        "alpha": ergebnis.alpha,
        "tempo": faktor,
        "tempowahl": tempoergebnis.als_dict() if tempoergebnis is not None else None,
    }

    # Die Karte räumen, bevor jemand anders sie braucht. Ausdrücklich `del`
    # und nicht bloß das Ende der Funktion: Was hier hängt, ist das Modell samt
    # Optimiererzustand, und solange der Trainer noch darauf zeigt, gibt auch
    # `raeume_karte` nichts her (siehe dort).
    del trainer, modell
    raeume_karte(bericht)

    return gewichte, ergebnis, kennzahlen


# Was neben den umgewandelten Gewichten liegen muss, damit faster-whisper den
# Stand wirklich laden kann. Der Zerteiler ist der wichtigere der beiden: Fehlt
# `tokenizer.json`, greift faster-whisper still auf den von `whisper-tiny`
# zurück - kein Fehler, keine Warnung, nur schlechterer Text.
BEIZULEGEN = ["tokenizer.json", "preprocessor_config.json"]


def raeume_karte(bericht: Bericht | None = None) -> float:
    """Den Speicher der Karte wirklich zurückgeben; liefert die Megabyte.

    **Warum das nötig ist, obwohl niemand mehr auf das Modell zeigt.** torch
    gibt freigewordenen Kartenspeicher nicht an den Treiber zurück, sondern
    behält ihn in einem eigenen Vorrat - eine sinnvolle Entscheidung, denn der
    nächste Trainingsschritt will ihn ohnehin gleich wieder. Für torch selbst
    ist der Speicher damit frei; für jeden anderen ist er belegt.

    Genau das ist im September 2026 passiert. Eine Faltung auf `medium` lief
    durch, der Stand war gesichert und umgewandelt - und beim Laden des
    Erkenners stand da `CUDA failed with error out of memory`. Die Karte war
    nicht voll: Sie war voll aus Sicht von CTranslate2, das seinen Speicher
    beim Treiber holt und nicht bei torch. Gemessen waren es 1,7 GB allein für
    die eingefrorenen Gewichte; mit Optimierer, Gradienten und Aktivierungen
    ist es ein Vielfaches davon.

    Bei `small` ging es gut, und das ist der Grund, warum es so lange
    unbemerkt blieb: Ein kleinerer Vorrat lässt genug übrig. Die Grenze lag
    also nicht bei „passt das Modell auf die Karte", sondern bei „passen beide
    gleichzeitig darauf" - und die zweite Frage stellt sich nie, wenn man sie
    nicht stellt.

    Kostenlos ist der Aufruf nicht: Der nächste Trainingsschritt muss sich
    seinen Vorrat neu vom Treiber holen. Deshalb steht er an den zwei Stellen,
    an denen wirklich gewechselt wird - nach dem Lernen und nach dem Messen -
    und nicht in der Schleife.
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


def _median(werte: list[float]) -> float | None:
    """Der Median - die Zahl, mit der die Faltungen mehrheitlich einverstanden sind.

    Nicht das Mittel: Eine Faltung, die aus der Reihe fällt, soll die
    Entscheidung nicht mitnehmen. Bei sechs Werten ist das der Durchschnitt der
    beiden mittleren.
    """
    da = sorted(wert for wert in werte if wert is not None)
    if not da:
        return None
    mitte = len(da) // 2
    return da[mitte] if len(da) % 2 else (da[mitte - 1] + da[mitte]) / 2


def _gewaehltes_tempo(gelernt: list[dict[str, Any]], auftrag: dict[str, Any]) -> float | None:
    """Der Faktor, mit dem das Endmodell rechnet.

    Bei `optimal` das Minimum der zusammengelegten Kurve; sonst der Median
    dessen, was die Faltungen benutzt haben - und das ist bei jedem anderen
    Verfahren ohnehin überall derselbe Wert.
    """
    faktoren = [float(k["tempo"]) for k in gelernt if k.get("tempo") is not None]
    if not faktoren:
        return None
    gewaehlt = laeufe.tempowahl_aus(auftrag)
    if gewaehlt == laeufe.TEMPO_GESCHAETZT:
        # Das Mittel der sechs geschätzten Faktoren, wieder auf eine
        # Viertelstufe gerundet. Der Median wäre hier zu grob: Sechs Werte, die
        # alle nah beieinanderliegen, mitteln sich sauber, und ein Ausreißer
        # ist bei einer Rechnung über Summen ohnehin nicht zu erwarten.
        return tempowahl.auf_stufe(sum(faktoren) / len(faktoren))
    if gewaehlt != laeufe.TEMPO_OPTIMAL:
        return _median(faktoren)
    bester, _punkte = tempowahl.zusammengelegt(gelernt)
    return bester if bester is not None else _median(faktoren)


def kreuzvalidiere(
    verzeichnis: Path, datenverzeichnis: Path, auftrag: dict[str, Any], bericht: Bericht
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Sechs Trainings, sechs Messungen - und was das Endmodell daraus mitnimmt.

    Je Faltung wird auf fünf Sechsteln gelernt und auf dem sechsten gemessen.
    Danach ist **jede** Aufnahme genau einmal von einem Modell gehört worden,
    das sie nie gesehen hat; die Zeilen daraus sind die Zahl dieses Laufs.

    Weggeräumt wird nach jeder Faltung sofort. Sieben Stände des vollen
    Trainings nebeneinander wären sieben Gigabyte, und gebraucht wird immer nur
    der eine, der gerade misst.
    """
    from .bewerten import bewerte_faltung

    zeilen: list[dict[str, Any]] = []
    gelernt: list[dict[str, Any]] = []

    gewaehlt = laeufe.tempowahl_aus(auftrag)
    for faltung in range(laeufe.FALTUNGEN):
        bericht.faltung(faltung)
        bericht.sage(f"── Faltung {faltung + 1} von {laeufe.FALTUNGEN}")
        gewichte, ergebnis, kennzahlen = trainiere(
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
                # Der Faktor **dieser** Faltung und nicht der des Auftrags: Bei
                # `optimal` hat sie sich einen eigenen gesucht, und gemessen
                # werden muss auf dem Klang, auf dem gelernt wurde.
                faktor=float(kennzahlen["tempo"]),
            )
        )
        gelernt.append({**kennzahlen, "faltung": faltung, "abschluss": ergebnis.als_dict()})
        if gewaehlt != laeufe.TEMPO_AUS:
            # Nach **jeder** Faltung, nicht erst nach allen sechs.
            #
            # Der Median steht endgültig erst am Ende fest - die Übersicht sagte
            # deshalb über den ganzen Lauf hinweg „Tempo wird gesucht", auch als
            # längst fünf Faltungen einen Faktor gefunden hatten. Das ist keine
            # Auskunft, sondern ein Platzhalter, der sich als eine ausgibt.
            #
            # Gemeldet wird der Median dessen, was bis hierher gefunden wurde,
            # und dazu, dass er noch vorläufig ist. Eine Zahl, die sich noch
            # ändern kann, ist mehr wert als keine - solange dransteht, dass sie
            # es kann.
            bericht.merke(
                tempo=_gewaehltes_tempo(gelernt, auftrag),
                tempo_endgueltig=False,
            )
        # Sofort und nicht am Ende: Die nächste Faltung braucht den Platz.
        # Das gilt für die Platte und für die Karte gleichermaßen - der
        # Erkenner ist in `bewerte_faltung` schon freigegeben, hier kommt zurück,
        # was torch sich beim Messen sonst noch genommen hat.
        raeume_karte(bericht)
        shutil.rmtree(gewichte.parent, ignore_errors=True)
        shutil.rmtree(verzeichnis / laeufe.ARBEITSSTAND / _name_fuer(faltung), ignore_errors=True)

    mitgenommen = {
        "durchgaenge": _median([float(k["durchgaenge"]) for k in gelernt]),
        # Der Horizont der Faltungen, damit das Endmodell auf derselben Rampe
        # läuft und nicht auf einer, die in seine Epochenzahl gestaucht wurde.
        "plan": _median([float(k["plan_durchgaenge"]) for k in gelernt]),
        "alpha": _median([k["alpha"] for k in gelernt if k["alpha"] is not None]),
        # Nicht der Median der sechs Sieger, sondern das Minimum der
        # **zusammengelegten** Kurve (siehe `tempowahl.zusammengelegt`): Eine
        # einzelne Faltung hört zu wenige Aufnahmen, als dass ihr Sieger mehr
        # wäre als Zufall - übereinandergelegt sind dieselben Kurven glatt.
        "tempo": _gewaehltes_tempo(gelernt, auftrag),
        # Die gemittelte Kurve samt Standardfehler je Stützstelle. Ohne sie ist
        # der Faktor darüber nicht zu beurteilen.
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
        # Jetzt steht er fest: derselbe Wert, mit dem gleich das Endmodell
        # trainiert wird.
        bericht.merke(tempo=float(mitgenommen["tempo"]), tempo_endgueltig=True)
    return zeilen, mitgenommen


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
        # Erst die Messung, dann der Stand, der ausgeliefert wird. Sieben
        # Trainings also, und das ist der Preis dafür, dass die Zahl über den
        # ganzen Korpus geht statt über ein Drittel.
        zeilen, mitgenommen = kreuzvalidiere(verzeichnis, datenverzeichnis, auftrag, bericht)

        bericht.faltung(None)
        bericht.sage("── Endmodell: lernt auf allem, was da ist")
        gewichte, ergebnis, _ = trainiere(
            verzeichnis, datenverzeichnis, bericht, faltung=None, vorgaben=mitgenommen
        )

        from .bewerten import gib_frei

        version = gib_frei(
            verzeichnis, datenverzeichnis, gewichte, auftrag, bericht, ergebnis,
            zeilen=zeilen, mitgenommen=mitgenommen,
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
