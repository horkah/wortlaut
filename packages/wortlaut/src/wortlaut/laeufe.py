"""Ein Trainingslauf als Verzeichnis - die Nahtstelle zwischen „lernen" und der GPU.

Trainiert wird nicht in dem Prozess, der die Oberfläche ausliefert. Das Modell
braucht torch, CUDA und einige Gigabyte Abbild; der Webdienst braucht das nie
und soll in Sekunden neu starten. Zwischen beiden liegt deshalb dasselbe, was
zwischen „schreiben" und „hören" liegt: keine direkte Aufrufkette, sondern
etwas Liegendes, das beide lesen können.

Hier ist das ein Verzeichnis je Auftrag:

    data/snapshots/<job_id>/
    ├── sprecher.txt          nur die Sprecher-ID - die Zusage an die Löschung
    ├── auftrag.json          was zu tun ist: Sprecher, Methode, Daten, Abschluss
    ├── manifest.jsonl        der Schnappschuss: je Zeile eine Trainingsprobe
    ├── zustand.json          was daraus geworden ist - vom Trainer geschrieben
    ├── fortschritt.jsonl     je Zeile ein Ereignis: Schritt, Verlust, Stufe
    ├── bewertung.jsonl       je Zeile eine Testaufnahme, vom fertigen Modell
    ├── protokoll.txt         die rohe Ausgabe, für den Fall, dass etwas fehlt
    ├── arbeitsstand/         Zwischenstände des Trainers - nur während des Laufs
    └── gewichte/             die Rohgewichte - nur bis zur Umwandlung

**Warum das Verzeichnis und nicht eine Tabelle der Auftrag ist.** Der Trainer
läuft in einem anderen Container. Er kann eine SQLite-Datei über das geteilte
Volume erreichen, aber dann gäbe es zwei Wahrheiten über denselben Lauf - die
Zeile und die Dateien - und irgendwann eine Zeile, die „läuft" sagt, während
nichts mehr läuft. So gibt es nur eine: Was der Trainer tut, steht dort, wo er
schreibt. Die Oberfläche liest mit.

**Warum `snapshots/` und nicht ein eigenes Verzeichnis.** Weil das Manifest
genau das ist, was der Entwurf einen Schnappschuss nennt: der eingefrorene
Stand des Korpus zum Zeitpunkt des Auftrags. Er ist der Grund, warum weiter
aufgenommen werden kann, während ein Training läuft, ohne dass das Ergebnis
unreproduzierbar wird. Der Arbeitsstand des Laufs daneben zu legen, macht aus
Auftrag, Daten und Ergebnis **eine** löschbare Einheit - und
`scripts/purge_speaker.py` findet sie bereits an der `sprecher.txt`, ohne das
Manifest deuten zu müssen.

**Warum die Warteschlange keine Datei ist.** Offen ist ein Auftrag, zu dem es
noch keinen `zustand.json` gibt. Eine zusätzliche Warteschlangendatei wäre ein
zweiter Ort, an dem dasselbe steht - und der erste, der bei einem Abbruch nicht
mehr stimmt.
"""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Dasselbe Verzeichnis, das `services/loeschung.py` bereits kennt und löscht.
SCHNAPPSCHUESSE = "snapshots"
SPRECHER_MARKE = "sprecher.txt"

AUFTRAG = "auftrag.json"
MANIFEST = "manifest.jsonl"
ZUSTAND = "zustand.json"
FORTSCHRITT = "fortschritt.jsonl"
BEWERTUNG = "bewertung.jsonl"
PROTOKOLL = "protokoll.txt"

# Die beiden Verzeichnisse, die nur während eines Laufs etwas zu sagen haben:
# der Arbeitsstand des Trainers (Zwischenstände samt Optimierer) und die
# Rohgewichte, aus denen der CTranslate2-Stand gerechnet wird. Beide wiegen
# Gigabyte, beide liest danach nichts mehr in diesem Projekt - und sie stehen
# hier und nicht im Trainer, weil zwei Seiten sie wegräumen müssen (siehe
# `raeume_zwischenstaende_auf`).
ARBEITSSTAND = "arbeitsstand"
GEWICHTE = "gewichte"
ZWISCHENSTAENDE = (ARBEITSSTAND, GEWICHTE)

# ── Die Faltungen ───────────────────────────────────────────────────────────
#
# Sechsfache Kreuzvalidierung über **alle** Aufnahmen. Jede Aufnahme bekommt
# der Reihe nach eine Faltung - 1, 2, 3, 4, 5, 6, 1, 2, … -, und je Faltung
# läuft ein Training: gelernt wird auf den anderen fünf Sechsteln, gemessen auf
# diesem einen. Sechs Trainings später ist **jede** Aufnahme genau einmal von
# einem Modell gehört worden, das sie nie gesehen hat.
#
# **Was hier bis September 2026 stand, und warum es weg ist.** Ein festes
# Testdrittel, einmal vergeben und nie wieder angefasst. Der Gedanke war
# richtig, die Ausführung trug nicht: Bei einem Korpus von neun Aufnahmen
# bestand der Test aus dreien und die Validierung aus einer, und eine Zahl über
# drei Aufnahmen ist keine Auskunft, sondern ein Würfelwurf. Die Kreuzvalidierung
# beantwortet dieselbe Frage über den ganzen Korpus statt über ein Drittel.
#
# Wirklich unabhängige Testaufnahmen sind damit nicht ersetzt - sie werden
# eigens aufgenommen werden. Bis dahin steht hier kein Test, und das ist
# ehrlicher, als ein Sechstel so zu nennen.
#
# **Warum gerechnet und nicht gespeichert.** Die alte Zuteilung musste in einer
# Tabelle stehen, weil eine Aufnahme, die einmal geprüft hatte, nie wieder
# trainieren durfte - verschob sich ihr Platz, war die Messung entwertet. Diese
# Zusage gibt es nicht mehr: In fünf von sechs Faltungen trainiert jede
# Aufnahme ohnehin. Die Faltung folgt deshalb einfach der Reihenfolge des
# Korpus, steht in jedem Schnappschuss und braucht keine zweite Wahrheit
# daneben.
FALTUNGEN = 6


def faltung_fuer(nummer: int) -> int:
    """Welche Faltung der `nummer`-ten Aufnahme zusteht (ab 0)."""
    return nummer % FALTUNGEN


# ── Methoden und Datensätze ─────────────────────────────────────────────────
#
# Zwei Fragen, die sich nicht vermischen lassen, und deshalb zwei Achsen: Wie
# wird trainiert, und womit. Vier Kombinationen, vier Modelle - erst der
# Vergleich sagt, ob das Mehr an Daten oder das Mehr an Freiheit geholfen hat.
VOLL = "full"
LORA = "lora"
METHODEN = (VOLL, LORA)

# ── Grundmodelle ────────────────────────────────────────────────────────────
#
# Worauf feingetunt wird. `small` war lange das einzige und ist die Vorgabe
# geblieben: die kleinste Stufe, die ganze Sätze trifft, und dieselbe Reihe,
# gegen die „hören" schon misst.
#
# `medium` kommt seit September 2026 dazu - aber **nur mit LoRA**. Volles
# Feintuning von `medium` sprengt den Speicher einer 11-GB-Karte; es gar nicht
# erst anzubieten ist ehrlicher, als es nach zwei Stunden am Speicher scheitern
# zu lassen. Als LoRA-Variante war es in `docs/trainingsverfahren.md` schon als
# eigener Versuch vorgesehen: Das Grundmodell ist der stärkste Hebel überhaupt,
# und der Zusatz lässt es unangetastet.
def kurzname(basismodell: str) -> str:
    """`openai/whisper-medium` → `medium` - so heißt es überall in den Tabellen."""
    return basismodell.rsplit("/", 1)[-1].removeprefix("whisper-")


# Grundmodelle, die für volles Feintuning zu groß sind. Nicht der Karte wegen
# allein: Auch die Rechenzeit wächst mit dem Quadrat der Aufmerksamkeit, und
# ein volles `medium` wäre auf dieser Karte kein Nachmittag mehr.
NUR_MIT_ZUSATZ = ("medium", "large", "large-v2", "large-v3")


def methoden_fuer(basismodell: str) -> tuple[str, ...]:
    """Welche Methoden dieses Grundmodell verträgt - `lora` allein bei den großen."""
    return (LORA,) if kurzname(basismodell) in NUR_MIT_ZUSATZ else METHODEN


NUR_ORIGINAL = "original"
MIT_VARIANTEN = "augmentiert"
DATENSAETZE = (NUR_ORIGINAL, MIT_VARIANTEN)

# ── Der Abschluss ───────────────────────────────────────────────────────────
#
# Die dritte Achse: was am Ende mit den Gewichten geschieht, wenn die Schleife
# durch ist. Sie fasst das Training nicht an - sie entscheidet nur, welcher
# Stand aus einem gelaufenen Training ausgeliefert wird.
#
# **Warum das eine Wahl ist und keine stille Verbesserung.** Beides sind
# Standardhandgriffe mit erwartetem Gewinn, und beide könnten schlicht immer
# laufen. Dann aber wäre jeder Vergleich mit einem Stand von vorher ein
# Vergleich zweier Rezepte, von dem niemand mehr wüsste, welche Hälfte gewirkt
# hat. Also: eine weitere Achse in derselben Vergleichstafel, und `bester` ist
# und bleibt genau das, was dieses Projekt bisher gerechnet hat.
#
# `bester`        Der beste Zwischenstand der Validierung - das Verfahren von
#                 vorher, Gewicht für Gewicht.
# `mittel`        Die besten Zwischenstände elementweise gemittelt („Model
#                 Soup"). Kostet keine Trainingszeit, nur Platz auf der Platte.
# `interpoliert`  Der beste Stand, anteilig mit dem Grundmodell verrechnet
#                 (WiSE-FT): θ = α·θ_grund + (1−α)·θ_fein. α wird auf der
#                 Validierung gewählt - nie auf dem Testdrittel.
# `beides`        Erst mitteln, dann interpolieren.
ABSCHLUSS_BESTER = "bester"
ABSCHLUSS_MITTEL = "mittel"
ABSCHLUSS_INTERPOLIERT = "interpoliert"
ABSCHLUSS_BEIDES = "beides"
ABSCHLUESSE = (
    ABSCHLUSS_BESTER,
    ABSCHLUSS_MITTEL,
    ABSCHLUSS_INTERPOLIERT,
    ABSCHLUSS_BEIDES,
)


def mittelt(abschluss: str) -> bool:
    """Ob dieser Abschluss mehrere Zwischenstände mittelt."""
    return abschluss in (ABSCHLUSS_MITTEL, ABSCHLUSS_BEIDES)


def interpoliert(abschluss: str) -> bool:
    """Ob dieser Abschluss gegen das Grundmodell interpoliert."""
    return abschluss in (ABSCHLUSS_INTERPOLIERT, ABSCHLUSS_BEIDES)


# ── Die Augmentierung im Training ───────────────────────────────────────────
#
# Die vierte Achse: womit die Trainingsproben abgewandelt werden, während
# gelernt wird. Gerechnet wird das im Trainer und nirgends abgelegt - was
# gewürfelt ist, ist in jedem Durchgang ein anderes, und eine Datei wäre hier
# nicht die Ersparnis, sondern der Verlust (`training/klangwandel.py`).
#
# Nicht zu verwechseln mit `daten`: Das sagt, **welche abgelegten Fassungen**
# einer Aufnahme als eigene Zeilen ins Manifest kommen - also womit trainiert
# wird. Hier steht, **was mit einer Zeile geschieht**, wenn sie geladen wird.
#
# `keine`      Die Probe, wie sie im Manifest steht. Die Vorgabe und das
#              Verfahren von vorher.
# `masken`     SpecAugment: Zeit- und Frequenzbalken ins Spektrogramm.
# `umgebung`   Dazu Raum und Rauschen auf der Welle.
# `voll`       Dazu Tempo - bei dysarthrischer Sprache die einzige der vier,
#              die auch schaden kann, und deshalb eine eigene Stufe.
AUG_KEINE = "keine"
AUG_MASKEN = "masken"
AUG_UMGEBUNG = "umgebung"
AUG_VOLL = "voll"
AUGMENTIERUNGEN = (AUG_KEINE, AUG_MASKEN, AUG_UMGEBUNG, AUG_VOLL)


# ── Wie lange trainiert wird ────────────────────────────────────────────────
#
# Die fünfte Achse, und sie kommt aus einem Befund: Bei einem sehr kleinen
# Korpus war die Validierungskurve am letzten Durchgang noch im Fallen. Die
# Zahl der Durchgänge im Rezept ist als **Obergrenze** gedacht - „zu hoch
# kostet Rechenzeit, zu niedrig kostet Güte". Zu niedrig war sie hier, und
# gemerkt hat es niemand, weil ein Lauf, der am Ende noch besser wird, genauso
# aussieht wie einer, der fertig ist.
#
# `fest`       Die Zahl aus dem Rezept, ohne Rücksicht auf die Kurve. Die
#              Vorgabe und das Verfahren von vorher.
# `geduldig`   Eine weit höhere Obergrenze, und Schluss ist, wenn die
#              Validierung mehrere Durchgänge lang nicht mehr besser wird.
#              Ausgeliefert wird ohnehin der beste Durchgang - die Geduld
#              kostet also Rechenzeit und niemals Güte.
DAUER_FEST = "fest"
DAUER_GEDULDIG = "geduldig"
DAUERN = (DAUER_FEST, DAUER_GEDULDIG)


# Der Zustand eines Laufs, wie ihn `zustand.json` nennt.
WARTET = "wartet"
LAEUFT = "laeuft"
FERTIG = "fertig"
GESCHEITERT = "gescheitert"
ABGEBROCHEN = "abgebrochen"

# Ab wann ein Lauf, der `laeuft` sagt, als hängend gilt: eine Viertelstunde
# ohne ein geschriebenes Byte. Siehe `Lauf.haengt` - die Zahl steht hier, weil
# sie eine Aussage über dieses Verzeichnis ist und nicht über die Ansicht, die
# sie zeigt.
STILLSTAND_S = 15 * 60


def jetzt() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def wurzel(datenverzeichnis: Path) -> Path:
    return datenverzeichnis / SCHNAPPSCHUESSE


def lauf_verzeichnis(datenverzeichnis: Path, job_id: str) -> Path:
    return wurzel(datenverzeichnis) / job_id


def raeume_zwischenstaende_auf(verzeichnis: Path) -> list[str]:
    """Arbeitsstand und Rohgewichte eines Laufs löschen; gibt zurück, was wegging.

    Gerufen von zwei Seiten, und das ist Absicht. Der rechnende Prozess tut es
    selbst, sobald er fertig oder gescheitert ist (`finetune.main`) - das ist
    der gewöhnliche Weg, und er sagt es auch ins Protokoll. Der Läufer tut es
    danach noch einmal (`laeufer.einmal`), und der deckt den Fall, den der
    erste nicht decken kann: einen Prozess, den der Kern erschlagen hat, weil
    der Speicher der Karte oder die Platte nicht mehr reichte. Dann läuft kein
    `finally` mehr.

    Genau so ist dieses Projekt einmal auf eine volle Platte gelaufen: ein
    abgebrochener Lauf, dessen `arbeitsstand/checkpoint-63` mit 1,8 GB
    Optimierer liegen blieb. Ein Rest dieser Größe je Abbruch füllt die Platte,
    und die volle Platte bringt den nächsten Lauf aus demselben Grund um.

    Zweimal zu löschen ist kein Fehler: Was schon weg ist, wird übergangen.
    """
    entfernt: list[str] = []
    for name in ZWISCHENSTAENDE:
        pfad = verzeichnis / name
        if pfad.is_dir():
            shutil.rmtree(pfad, ignore_errors=True)
            entfernt.append(name)
    return entfernt


def lies_json(pfad: Path) -> dict[str, Any] | None:
    """Eine JSON-Datei, oder `None`, wenn sie fehlt oder halb geschrieben ist.

    Halb geschrieben kommt vor: Der Trainer schreibt, während die Oberfläche
    liest. Ein Fehler ist das nicht - beim nächsten Takt steht sie vollständig
    da. Ein 500er dagegen wäre einer.
    """
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def schreibe_json(pfad: Path, inhalt: dict[str, Any]) -> None:
    """Erst daneben, dann an die Stelle: Ein Leser sieht nie die Hälfte."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    entwurf = pfad.with_suffix(f"{pfad.suffix}.neu")
    entwurf.write_text(json.dumps(inhalt, ensure_ascii=False, indent=2), encoding="utf-8")
    entwurf.replace(pfad)


def haenge_an(pfad: Path, zeile: dict[str, Any]) -> None:
    """Eine Zeile an eine JSONL-Datei - der Weg, auf dem Fortschritt entsteht."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with pfad.open("a", encoding="utf-8") as datei:
        datei.write(json.dumps(zeile, ensure_ascii=False) + "\n")
        # Ohne das steht der Fortschritt im Puffer des Trainers, während die
        # Oberfläche daneben eine leere Datei liest und behauptet, es gehe
        # nicht voran.
        datei.flush()


def lies_zeilen(pfad: Path) -> list[dict[str, Any]]:
    """Eine JSONL-Datei als Liste; unvollständige letzte Zeile wird übergangen."""
    if not pfad.is_file():
        return []
    zeilen = []
    for roh in pfad.read_text(encoding="utf-8").splitlines():
        try:
            zeilen.append(json.loads(roh))
        except ValueError:
            # Die letzte Zeile kann halb geschrieben sein, während gerechnet
            # wird. Sie kommt beim nächsten Lesen vollständig.
            continue
    return zeilen


@dataclass(frozen=True)
class Lauf:
    """Ein Auftrag samt dem, was daraus geworden ist - alles aus Dateien gelesen."""

    job_id: str
    verzeichnis: Path
    auftrag: dict[str, Any]
    zustand: dict[str, Any]

    @property
    def sprecher_id(self) -> str:
        return str(self.auftrag.get("sprecher_id", ""))

    @property
    def status(self) -> str:
        return str(self.zustand.get("status", WARTET))

    @property
    def offen(self) -> bool:
        """Noch zu rechnen - das ist die ganze Warteschlange."""
        return self.status == WARTET

    @property
    def stillstand_s(self) -> float:
        """Wie lange dieser Lauf schon nichts mehr geschrieben hat, in Sekunden.

        Der Puls eines Laufs sind seine Dateien. Ein rechnender Trainer
        schreibt fortwährend: Fortschritt, Protokoll, Zustand. Hört das auf,
        während der Zustand `laeuft` sagt, dann rechnet entweder nichts mehr,
        oder es rechnet und kommt nicht voran - von außen ist das dasselbe.

        **Warum über die Dateien und nicht über den Prozess.** Weil er in einem
        anderen Container steckt. Der Webdienst sieht ihn nicht und soll ihn
        auch nicht sehen: Zwischen Oberfläche und Karte liegt ein Verzeichnis
        und kein Netzwerkweg - das ist die Grundentscheidung dieses Teils
        (`training/laeufer.py`). Was durch dieses Verzeichnis nicht zu
        erfahren ist, ist hier nicht zu erfahren.

        Für einen Lauf, der nie angefangen hat, zählt der Auftrag: Auch er ist
        eine Datei, und sein Alter ist dann das richtige Maß.
        """
        juengste = 0.0
        for name in (FORTSCHRITT, PROTOKOLL, ZUSTAND, AUFTRAG):
            datei = self.verzeichnis / name
            try:
                juengste = max(juengste, datei.stat().st_mtime)
            except OSError:
                continue
        if juengste == 0.0:
            return 0.0
        return max(0.0, time.time() - juengste)

    @property
    def haengt(self) -> bool:
        """Sagt `laeuft`, rührt sich aber nicht mehr.

        Das kommt auf zwei Wegen zustande, und beide enden gleich:

        * Der Prozess ist tot, ohne es sagen zu können - der Trainer-Container
          wurde neu gestartet, die Maschine ist neu gestartet, der Kern hat
          ihn erschlagen. `laeufer._nacharbeit` fängt das sonst ab, kommt aber
          selbst nicht mehr dazu, wenn es ihn mit erwischt hat.
        * Der Prozess lebt und kommt nicht voran.

        Von außen ist beides dasselbe, und für den Menschen davor auch: Da
        steht ein Lauf bei 3 % und bewegt sich nicht. Genau das soll dastehen,
        statt eines Fortschrittsbalkens, der Zuversicht vortäuscht.

        **Warum die Grenze so weit liegt.** Ein Lauf darf still sein. Das
        Umwandeln nach CTranslate2 schreibt minutenlang nichts, und seit der
        Trainer auf eine belegte Karte wartet, sind es bis zu neun Minuten am
        Stück (`training/bewerten.py`). Die Grenze muss darüber liegen, sonst
        heißt „hängt" irgendwann nur noch „ist gerade beschäftigt" - und eine
        Warnung, die auch im Normalfall angeht, liest bald niemand mehr.
        """
        return self.status == LAEUFT and self.stillstand_s > STILLSTAND_S


def lies_lauf(datenverzeichnis: Path, job_id: str) -> Lauf | None:
    verzeichnis = lauf_verzeichnis(datenverzeichnis, job_id)
    auftrag = lies_json(verzeichnis / AUFTRAG)
    if auftrag is None:
        return None
    return Lauf(
        job_id=job_id,
        verzeichnis=verzeichnis,
        auftrag=auftrag,
        # Fehlt der Zustand, hat noch niemand angefangen: Genau das ist „wartet".
        zustand=lies_json(verzeichnis / ZUSTAND) or {"status": WARTET},
    )


def alle_laeufe(datenverzeichnis: Path, sprecher_id: str = "") -> list[Lauf]:
    """Alle Läufe, älteste zuerst; leerer Sprecher heißt: alle.

    Sortiert nach Kennung, und die ist zeitlich sortierbar (siehe `ids.py`) -
    die Reihenfolge im Verzeichnis ist damit die Reihenfolge der Aufträge.
    """
    if not wurzel(datenverzeichnis).is_dir():
        return []
    laeufe = (
        lies_lauf(datenverzeichnis, eintrag.name)
        for eintrag in sorted(wurzel(datenverzeichnis).iterdir())
        if eintrag.is_dir()
    )
    return [
        lauf
        for lauf in laeufe
        if lauf is not None and (not sprecher_id or lauf.sprecher_id == sprecher_id)
    ]


def naechster_offener(datenverzeichnis: Path) -> Lauf | None:
    """Der älteste Auftrag, den noch niemand angefasst hat.

    Einer nach dem anderen, über alle Sprecher: Es gibt eine GPU, und zwei
    Läufe darauf wären zusammen langsamer als nacheinander - dieselbe
    Überlegung wie bei der Auswertung in „hören".
    """
    for lauf in alle_laeufe(datenverzeichnis):
        if lauf.offen:
            return lauf
    return None


def manifestzeilen(verzeichnis: Path) -> Iterator[dict[str, Any]]:
    """Die Proben eines Schnappschusses, Zeile für Zeile.

    Als Strom und nicht als Liste: Das Manifest kann bei vielen Aufnahmen und
    mehreren Fassungen je Aufnahme lang werden, und der Trainer braucht immer nur
    die nächste.
    """
    pfad = verzeichnis / MANIFEST
    if not pfad.is_file():
        return
    with pfad.open(encoding="utf-8") as datei:
        for roh in datei:
            if roh.strip():
                yield json.loads(roh)
