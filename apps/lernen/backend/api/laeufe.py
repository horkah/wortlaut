"""Läufe beauftragen und ihnen zusehen.

Vier Wege, und sie teilen sich die Arbeit nach dem, wie oft sie gebraucht
werden - dieselbe Aufteilung wie in der Auswertung von „hören":

* `GET  /lernen/api/laeufe`          die Liste: je Lauf Auftrag und Stand.
  Sie wird abgefragt, solange die Seite offen ist, und trägt deshalb **keine**
  Kurven: Bei zwölf Läufen mit je tausend Schritten wäre das bei jedem Takt ein
  Vielfaches dessen, was gemeint ist.
* `GET  /lernen/api/laeufe/{id}`     ein Lauf im Einzelnen: Kurven, Bewertung,
  Vergleich mit der Baseline.
* `POST /lernen/api/laeufe`          einen Lauf beauftragen. **Der einzige Weg
  hier, der ein zweites Geheimnis verlangt** - den Trainerschlüssel, siehe
  `_pruefe_trainerschluessel`.
* `POST /lernen/api/laeufe/{id}/abbruch`  einen wartenden zurücknehmen.
* `DELETE /lernen/api/laeufe/{id}`   einen Lauf ersatzlos entfernen, samt dem
  Modell, das aus ihm entstand.

Gerechnet wird in keinem davon. Der Trainer ist ein anderer Container mit einer
Karte darin; hier entsteht nur das Verzeichnis, an dem er ihn erkennt (siehe
`wortlaut/laeufe.py`).
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from wortlaut import laeufe as lauf_layout, registry, streuung

from ..config import einstellungen
from ..deps import Korpus, SprecherId
from ..services import aufteilung, auftraege, vergleich

router = APIRouter(prefix="/lernen/api/laeufe", tags=["Läufe"])

# Der Kopf, in dem der Trainerschlüssel steht. Nicht `Authorization`: Dort
# liegt schon der Sprecherzugang, und aus ihm leitet der Server ab, wessen
# Modell entsteht (`deps.py`). Zwei Geheimnisse in einem Kopf hießen, das eine
# gegen das andere zu tauschen - und dann trainierte der Schlüssel für
# niemanden oder der Zugang ohne Erlaubnis.
SCHLUESSEL_KOPF = "X-Trainer-Key"


def _pruefe_trainerschluessel(
    x_trainer_key: Annotated[str | None, Header()] = None,
) -> None:
    """Wächter des einen teuren Weges: einen Lauf beauftragen.

    Ein Lauf belegt die Karte für Minuten bis Stunden, und er kostet Strom,
    Wärme und die Wartezeit aller anderen. Der Sprecherzugang allein reicht
    dafür nicht: Er ist an jeden ausgegeben, der aufnimmt, und er ist die
    Antwort auf „wessen Modell?", nicht auf „wer darf rechnen lassen?".

    Nicht gesetzt heißt abgeschaltet - kein Training für niemanden, auch nicht
    in der Entwicklung (die Begründung steht bei `trainer_key` in der
    `config.py`). Die Oberfläche fragt das vorher ab und zeigt den Knopf dann
    gar nicht erst (`bereit` und `hinweis` in der Liste).

    Zeitkonstant verglichen und über die UTF-8-Bytes, wie in „hören": Sonst
    verriete die Antwortzeit den Anfang des Schlüssels, und ein Umlaut darin
    ergäbe einen 500er statt eines sauberen 401.
    """
    erwartet = einstellungen().trainer_key
    if not erwartet:
        # 401 und nicht 403, weil „hören" es bei Verwaltung und Aufsicht
        # genauso hält: Eine abgeschaltete Tür ist eine, an der niemand
        # angemeldet ist. Zwei Fassungen derselben Absage wären zwei Wege
        # durch die Oberfläche.
        raise HTTPException(
            status_code=401,
            detail=(
                "Training ist abgeschaltet: Auf diesem Server ist kein "
                "Trainerschlüssel hinterlegt (WORTLAUT_TRAINER_KEY)."
            ),
        )
    vorgelegt = x_trainer_key or ""
    if not secrets.compare_digest(vorgelegt.encode("utf-8"), erwartet.encode("utf-8")):
        raise HTTPException(
            status_code=401,
            detail="Falscher oder fehlender Trainerschlüssel.",
        )


class WahlAntwort(BaseModel):
    """Eine Wahlmöglichkeit beim Beauftragen - Schlüssel, Name, Begründung."""

    schluessel: str
    name: str
    erklaerung: str


METHODEN = [
    WahlAntwort(
        schluessel=lauf_layout.VOLL,
        name="Volles Training",
        erklaerung=(
            "Alle Gewichte werden angepasst. Holt am meisten aus wenigen Stunden "
            "Sprache heraus und vergisst am ehesten, was das Modell vorher konnte."
        ),
    ),
    WahlAntwort(
        schluessel=lauf_layout.LORA,
        name="Feintuning (LoRA)",
        erklaerung=(
            "Nur ein kleiner Zusatz wird gelernt, das Grundmodell bleibt stehen. "
            "Schneller, genügsamer im Speicher und schwerer zu verderben."
        ),
    ),
]

DATENSAETZE = [
    WahlAntwort(
        schluessel=lauf_layout.NUR_ORIGINAL,
        name="Nur Originale",
        erklaerung="Jede Aufnahme einmal, so wie sie gesprochen wurde.",
    ),
    WahlAntwort(
        schluessel=lauf_layout.MIT_VARIANTEN,
        name="Mit Abwandlungen",
        erklaerung=(
            "Dazu die drei abgewandelten Fassungen jeder Aufnahme - viermal so "
            "viele Proben, und eine Chance, Pegel und Rauschen zu überhören."
        ),
    ),
]


ABSCHLUESSE = [
    WahlAntwort(
        schluessel=lauf_layout.ABSCHLUSS_BESTER,
        name="Bester Durchgang",
        erklaerung=(
            "Ausgeliefert wird der Zwischenstand mit dem besten Validierungsverlust - "
            "das Verfahren, nach dem alle bisherigen Stände entstanden sind."
        ),
    ),
    WahlAntwort(
        schluessel=lauf_layout.ABSCHLUSS_MITTEL,
        name="Beste Durchgänge gemittelt",
        erklaerung=(
            "Die besten drei Zwischenstände werden Gewicht für Gewicht gemittelt. "
            "Kostet keine Rechenzeit, nur Platz auf der Platte."
        ),
    ),
    WahlAntwort(
        schluessel=lauf_layout.ABSCHLUSS_INTERPOLIERT,
        name="Mit dem Grundmodell verrechnet",
        erklaerung=(
            "Der fertige Stand wird anteilig mit dem Grundmodell gemischt, damit er "
            "weniger vergisst. Der Anteil wird auf der Validierung gewählt, nie am Test."
        ),
    ),
    WahlAntwort(
        schluessel=lauf_layout.ABSCHLUSS_BEIDES,
        name="Beides",
        erklaerung="Erst mitteln, dann mit dem Grundmodell verrechnen.",
    ),
]


AUGMENTIERUNGEN = [
    WahlAntwort(
        schluessel=lauf_layout.AUG_KEINE,
        name="Keine",
        erklaerung=(
            "Jede Probe so, wie sie im Schnappschuss steht - das Verfahren, "
            "nach dem alle bisherigen Stände entstanden sind."
        ),
    ),
    WahlAntwort(
        schluessel=lauf_layout.AUG_MASKEN,
        name="Masken (SpecAugment)",
        erklaerung=(
            "Zeit- und Frequenzbalken ins Spektrogramm. Das Modell lernt, aus dem "
            "Rest zu schließen, statt sich auf einzelne Bänder zu verlassen. "
            "Kostet praktisch nichts."
        ),
    ),
    WahlAntwort(
        schluessel=lauf_layout.AUG_UMGEBUNG,
        name="Masken, Raum und Rauschen",
        erklaerung=(
            "Dazu ein gewürfelter Raum und ein gewürfeltes Grundgeräusch - der "
            "Abstand zum Mikrofon, die Wand dahinter, der Lüfter."
        ),
    ),
    WahlAntwort(
        schluessel=lauf_layout.AUG_VOLL,
        name="Dazu Tempo",
        erklaerung=(
            "Zusätzlich schneller und langsamer gesprochen. Kann helfen oder "
            "schaden: Bei dysarthrischer Sprache ist das Tempo selbst ein Merkmal "
            "des Sprechers. Deshalb eine eigene Stufe - damit man es misst."
        ),
    ),
]


DAUERN = [
    WahlAntwort(
        schluessel=lauf_layout.DAUER_FEST,
        name="Feste Zahl Durchgänge",
        erklaerung=(
            "So viele Durchgänge, wie im Rezept stehen - das Verfahren, nach dem "
            "alle bisherigen Stände entstanden sind."
        ),
    ),
    WahlAntwort(
        schluessel=lauf_layout.DAUER_GEDULDIG,
        name="Bis nichts mehr besser wird",
        erklaerung=(
            "Eine weit höhere Obergrenze, und Schluss, sobald die Validierung "
            "mehrere Durchgänge lang nicht mehr besser wird. Kostet Rechenzeit "
            "und nie Güte: Ausgeliefert wird ohnehin der beste Durchgang."
        ),
    ),
]


TEMPI = [
    WahlAntwort(
        schluessel=lauf_layout.TEMPO_WIE_EINGESTELLT,
        name="Wie im Profil eingestellt",
        erklaerung=(
            "Die Geschwindigkeit, die für diesen Sprecher in „hören\u201c unter "
            "Verwaltung steht - dieselbe, mit der auch gemessen und diktiert wird."
        ),
    ),
    WahlAntwort(
        schluessel=lauf_layout.TEMPO_OPTIMAL,
        name="Beste suchen (0,8 bis 3,0)",
        erklaerung=(
            "Sucht vor jeder Faltung die Geschwindigkeit, bei der das unveränderte "
            "Grundmodell diesen Sprecher am besten versteht, und trainiert damit. "
            "Kostet etwa eine Minute je Faltung. Der gefundene Faktor steht "
            "hinterher beim Lauf - wie das Gewicht α."
        ),
    ),
]


class GrundmodellAntwort(BaseModel):
    """Ein Grundmodell zur Wahl - und was es verträgt.

    `methoden` steht dabei, damit die Oberfläche die unmögliche Kombination
    gar nicht erst anbietet: Volles Feintuning von `medium` sprengt den
    Speicher der Karte, und es nach zwei Stunden am Speicher scheitern zu
    lassen wäre die schlechtere Auskunft.
    """

    schluessel: str
    name: str
    erklaerung: str
    methoden: list[str]


def _grundmodelle() -> list[GrundmodellAntwort]:
    konfiguration = einstellungen()
    beschreibung = {
        "small": (
            "244 Millionen Gewichte. Schnell, genügsam, und die Reihe, gegen die "
            "\u201eh\u00f6ren\u201c seit jeher misst."
        ),
        "medium": (
            "769 Millionen Gewichte - dreimal so groß und deutlich besser im "
            "Ausgangspunkt. Nur mit LoRA: Volles Feintuning sprengt die Karte. "
            "Rechnet spürbar länger."
        ),
    }
    antworten = []
    for modell in konfiguration.grundmodelle():
        kurz = lauf_layout.kurzname(modell)
        antworten.append(
            GrundmodellAntwort(
                schluessel=modell,
                name=f"whisper-{kurz}",
                erklaerung=beschreibung.get(kurz, f"Grundmodell {kurz}."),
                methoden=list(lauf_layout.methoden_fuer(modell)),
            )
        )
    return antworten


class Bestellung(BaseModel):
    methode: str
    daten: str
    # Die dritte Achse, mit Vorgabe: Eine Bestellung ohne dieses Feld ist
    # dieselbe Bestellung wie vor September 2026.
    abschluss: str = lauf_layout.ABSCHLUSS_BESTER
    # Die vierte Achse, ebenfalls mit Vorgabe.
    augmentierung: str = lauf_layout.AUG_KEINE
    # Die fünfte Achse, ebenfalls mit Vorgabe.
    dauer: str = lauf_layout.DAUER_FEST
    # Die sechste, und die einzige, die etwas sucht statt etwas zu setzen.
    tempowahl: str = lauf_layout.TEMPO_WIE_EINGESTELLT
    # Worauf trainiert wird. Leer heißt: die Vorgabe des Servers - ein Auftrag
    # von einem Aufrufer, der diese Achse nicht kennt, bleibt derselbe Auftrag.
    grundmodell: str = ""


class StandHinweis(BaseModel):
    """Was an einem Lauf hängt, bevor ihn jemand löscht.

    Die Oberfläche fragt damit nicht noch einmal beim Server nach, was
    verschwinden würde - sie hat es schon, als sie die Liste holte, und kann
    es in die Sicherheitsabfrage schreiben.
    """

    version: str
    freigegeben: bool


class LaufAntwort(BaseModel):
    job_id: str
    sprecher_id: str
    methode: str
    daten: str
    # Was am Ende mit den Gewichten geschah. Ein Lauf von vor dieser Achse hat
    # das Feld nicht im Auftrag stehen und heißt hier `bester` - das ist keine
    # Annahme, sondern genau das, was damals gerechnet wurde.
    abschluss: str
    # Womit die Trainingsproben abgewandelt wurden. Ein Lauf von vor dieser
    # Achse heißt hier `keine` - genau das, was damals gerechnet wurde.
    augmentierung: str
    # Wie lange trainiert wurde. Ein Lauf von vor dieser Achse heißt `fest`.
    dauer: str
    # Ob die Geschwindigkeit gesucht wurde oder die des Profils galt.
    tempowahl: str = lauf_layout.TEMPO_WIE_EINGESTELLT
    # Die Geschwindigkeit, mit der dieser Lauf wirklich gerechnet hat. Bei
    # `optimal` der gefundene Median über die Faltungen, sonst der Wert aus dem
    # Profil, wie er beim Beauftragen dastand. `null`, solange die Suche noch
    # läuft - dann ist es schlicht noch nicht entschieden.
    tempo: float | None = None
    basismodell: str
    erstellt: str
    status: str
    # Woran gerade gearbeitet wird: laden, training, export, bewertung.
    stufe: str
    # 0 bis 1, aus Schritt und Schrittzahl - `null`, solange der Trainer noch
    # nicht gesagt hat, wie viele es werden.
    anteil: float | None
    aufnahmen: int
    zeilen: dict[str, int]
    version: str | None
    # Der kurze Code des Standes, der aus diesem Lauf entstand - dieselbe
    # Kennung wie in der Modelltafel und in „schreiben"
    # (`registry.kurzkennung`). `null`, solange kein Stand da ist.
    kennung: str | None = None
    fehler: str | None
    # Der Modellstand, der aus diesem Lauf hervorging - `null`, solange keiner
    # entstanden ist. Er ginge beim Löschen mit.
    stand: StandHinweis | None
    # Ob sich dieser Lauf löschen lässt. Ein rechnender nicht: In sein
    # Verzeichnis schreibt gerade ein anderer Container. Ein hängender schon -
    # dort schreibt seit einer Viertelstunde niemand mehr.
    loeschbar: bool
    # Sagt `laeuft`, rührt sich aber nicht mehr (`wortlaut/laeufe.py`). Die
    # Ansicht zeigt das statt eines Fortschrittsbalkens, der so tut, als käme
    # gleich der nächste Schritt.
    haengt: bool
    # Seit wann nichts mehr geschrieben wurde, in Sekunden - nur bei `laeuft`
    # eine Auskunft, sonst `null`. Damit die Ansicht „seit 20 Minuten" sagen
    # kann und nicht bloß „hängt".
    stillstand_s: float | None


class PunktAntwort(BaseModel):
    schritt: int
    epoche: float
    verlust: float | None = None
    lernrate: float | None = None
    wer: float | None = None


class GegenueberAntwort(BaseModel):
    mass: str
    baseline: float | None
    trainiert: float | None
    besser: bool | None
    anzahl: int
    # Alles Weitere nur, wenn `?intervall=` es angefordert hat. `besser` sagt,
    # wer vorn liegt; `unterschied` sagt, ob das mehr ist als Zufall - Differenz
    # (trainiert minus Baseline) mit Bereich und p-Wert, gepaart auf denselben
    # Aufnahmen gerechnet.
    unterschied: dict | None = None
    bereich_baseline: dict | None = None
    bereich_trainiert: dict | None = None


class EinzelAntwort(BaseModel):
    lauf: LaufAntwort
    methoden: list[WahlAntwort]
    datensaetze: list[WahlAntwort]
    abschluesse: list[WahlAntwort]
    augmentierungen: list[WahlAntwort]
    dauern: list[WahlAntwort]
    tempi: list[WahlAntwort]
    grundmodelle: list[GrundmodellAntwort]
    kurve_training: list[PunktAntwort]
    kurve_validierung: list[PunktAntwort]
    # fassung -> die Maße, jeweils vorher und nachher
    vergleich: dict[str, list[GegenueberAntwort]]
    protokoll: str
    # Welche Blockart gerechnet wurde: `aus`, `aufnahme` oder `einheit`.
    intervall: str = streuung.AUS
    streuung_marke: str = ""


class ListeAntwort(BaseModel):
    laeufe: list[LaufAntwort]
    methoden: list[WahlAntwort]
    datensaetze: list[WahlAntwort]
    abschluesse: list[WahlAntwort]
    augmentierungen: list[WahlAntwort]
    dauern: list[WahlAntwort]
    tempi: list[WahlAntwort]
    grundmodelle: list[GrundmodellAntwort]
    basismodell: str
    # Wie viele Faltungen ein Lauf rechnet. Vom Server, damit die Oberfläche
    # die Sechs nicht ein zweites Mal kennt.
    faltungen: int
    # Ob überhaupt beauftragt werden kann, und wenn nicht, warum. Es sind zwei
    # Gründe, aus denen nicht: zu wenige Aufnahmen - oder kein hinterlegter
    # Trainerschlüssel, dann kann es auf diesem Server niemand.
    bereit: bool
    hinweis: str
    # Ob die Oberfläche nach dem Trainerschlüssel fragen muss. Der Server sagt
    # es, statt dass die Seite es errät: Sonst stünde die Regel zweimal da, und
    # die Kopie in der Oberfläche wäre die, die niemand prüft.
    schluessel_noetig: bool
    # Wie viele brauchbare Aufnahmen es inzwischen gibt, und wie viele davon
    # der jüngste durchgelaufene Lauf noch nicht kannte.
    #
    # Es gibt hier ausdrücklich **keine** Automatik, die daraufhin selbst
    # trainiert: Ein Lauf belegt die Karte für Minuten bis Stunden und
    # entsteht aus einem Schnappschuss, der festhalten soll, worauf ein Modell
    # gelernt hat. Von selbst angestoßen wüsste hinterher niemand mehr, welche
    # Aufnahmen in welchem Stand stecken - und zwei Läufe, die sich eine Karte
    # teilen, wären zusammen langsamer als nacheinander. Dieselbe Überlegung
    # wie beim Lauf der Auswertung in „hören": Wer messen will, sagt es.
    #
    # Was die Zahl stattdessen tut: Sie macht sichtbar, wann es sich lohnt.
    aufnahmen_jetzt: int
    aufnahmen_neu: int


def _anteil(lauf: lauf_layout.Lauf) -> float | None:
    gesamt = lauf.zustand.get("schritte_gesamt")
    schritt = lauf.zustand.get("schritt")
    if not gesamt or schritt is None:
        return None
    return min(1.0, float(schritt) / float(gesamt))


def _stand_zu(lauf: lauf_layout.Lauf) -> StandHinweis | None:
    datenverzeichnis = einstellungen().data_dir
    stand = registry.stand_zu_lauf(datenverzeichnis, lauf.sprecher_id, lauf.job_id)
    if stand is None:
        return None
    return StandHinweis(
        version=str(stand.get("id", "/")).split("/", 1)[-1],
        # Aus der Freigabe und nicht aus dem `status` des Manifests: Seit auch
        # ein Grundmodell freigegeben sein kann, ist die Freigabedatei die
        # Auskunft darüber, was gilt (siehe `wortlaut/registry.py`).
        freigegeben=registry.freigegeben(datenverzeichnis, lauf.sprecher_id)
        == str(stand.get("id", "")),
    )


def _als_antwort(lauf: lauf_layout.Lauf) -> LaufAntwort:
    return LaufAntwort(
        job_id=lauf.job_id,
        sprecher_id=lauf.sprecher_id,
        methode=str(lauf.auftrag.get("methode", "")),
        daten=str(lauf.auftrag.get("daten", "")),
        abschluss=str(lauf.auftrag.get("abschluss") or lauf_layout.ABSCHLUSS_BESTER),
        augmentierung=str(lauf.auftrag.get("augmentierung") or lauf_layout.AUG_KEINE),
        dauer=str(lauf.auftrag.get("dauer") or lauf_layout.DAUER_FEST),
        tempowahl=str(lauf.auftrag.get("tempowahl") or lauf_layout.TEMPO_WIE_EINGESTELLT),
        tempo=_tempo_des_laufs(lauf),
        basismodell=str(lauf.auftrag.get("basismodell", "")),
        erstellt=str(lauf.auftrag.get("erstellt", "")),
        status=lauf.status,
        stufe=str(lauf.zustand.get("stufe", "")),
        anteil=_anteil(lauf),
        aufnahmen=int(lauf.auftrag.get("aufnahmen", 0)),
        zeilen=dict(lauf.auftrag.get("zeilen", {})),
        version=lauf.zustand.get("version"),
        kennung=(
            registry.kurzkennung(str(lauf.zustand["version"]))
            if lauf.zustand.get("version")
            else None
        ),
        fehler=lauf.zustand.get("fehler"),
        stand=_stand_zu(lauf),
        loeschbar=lauf.status != lauf_layout.LAEUFT or lauf.haengt,
        haengt=lauf.haengt,
        stillstand_s=(
            round(lauf.stillstand_s) if lauf.status == lauf_layout.LAEUFT else None
        ),
    )


def _tempo_des_laufs(lauf: lauf_layout.Lauf) -> float | None:
    """Mit welcher Geschwindigkeit dieser Lauf wirklich gerechnet hat.

    Bei `wie_eingestellt` ist es der Wert, der beim Beauftragen im Profil
    stand - eingefroren im Auftrag, damit ein späteres Umstellen des Profils
    nicht rückwirkend behauptet, dieser Lauf sei ein anderer gewesen.

    Bei `optimal` ist es der Median der Faktoren, die die sechs Faltungen
    gefunden haben - dieselbe Art, wie das Endmodell auch die Durchgänge und
    das α mitnimmt. Solange die Faltungen laufen, steht er noch nicht fest;
    dann ist es `None`, und die Ansicht sagt „wird gesucht" statt einer Zahl,
    die sie noch gar nicht hat.
    """
    gewaehlt = lauf.zustand.get("tempo")
    if gewaehlt is not None:
        return float(gewaehlt)
    if str(lauf.auftrag.get("tempowahl") or "") == lauf_layout.TEMPO_OPTIMAL:
        return None
    return float(lauf.auftrag.get("tempo", 1.0))


def _hole(sprecher: str, job_id: str) -> lauf_layout.Lauf:
    lauf = lauf_layout.lies_lauf(einstellungen().data_dir, job_id)
    # Ein fremder Lauf ist hier schlicht unbekannt: Die Kennung stammt aus dem
    # Zugang, und wer nach einem anderen Verzeichnis fragt, hat dort nichts
    # verloren - auch nicht die Auskunft, dass es existiert.
    if lauf is None or lauf.sprecher_id != sprecher:
        raise HTTPException(status_code=404, detail="Unbekannter Lauf.")
    return lauf


@router.get("", response_model=ListeAntwort)
def liste(korpus: Korpus, sprecher: SprecherId) -> ListeAntwort:
    konfiguration = einstellungen()
    proben = aufteilung.proben(korpus)
    genug = aufteilung.genug(proben)
    # Ohne hinterlegten Schlüssel ist diese Seite eine Leseseite: Die Läufe von
    # früher bleiben sichtbar, beauftragen kann hier niemand mehr.
    erlaubt = bool(konfiguration.trainer_key)
    alle = lauf_layout.alle_laeufe(konfiguration.data_dir, sprecher)

    # Der jüngste Lauf, der wirklich durchgelaufen ist. Ein abgebrochener oder
    # gescheiterter sagt nichts darüber, was ein Modell kennt.
    fertige = [lauf for lauf in alle if lauf.status == lauf_layout.FERTIG]
    zuletzt = int(fertige[-1].auftrag.get("aufnahmen", 0)) if fertige else 0

    return ListeAntwort(
        laeufe=[_als_antwort(lauf) for lauf in reversed(alle)],
        aufnahmen_jetzt=len(proben),
        # Nie negativ: Wer Aufnahmen löscht, hat nicht „minus drei neue".
        aufnahmen_neu=max(0, len(proben) - zuletzt),
        methoden=METHODEN,
        datensaetze=DATENSAETZE,
        abschluesse=ABSCHLUESSE,
        augmentierungen=AUGMENTIERUNGEN,
        dauern=DAUERN,
        tempi=TEMPI,
        grundmodelle=_grundmodelle(),
        basismodell=konfiguration.lernen_basismodell,
        faltungen=lauf_layout.FALTUNGEN,
        bereit=genug and erlaubt,
        schluessel_noetig=erlaubt,
        # Der Schlüssel zuerst: Wer ohnehin nicht trainieren darf, soll nicht
        # erst Aufnahmen sammeln, um dann vor derselben Wand zu stehen.
        hinweis=(
            ""
            if genug and erlaubt
            else "Auf diesem Server ist kein Trainerschlüssel hinterlegt - "
            "hier lässt sich kein Training anstoßen."
            if not erlaubt
            else f"Sechsfache Kreuzvalidierung braucht mindestens "
            f"{lauf_layout.FALTUNGEN} Aufnahmen - sie kommen aus \u201ehören\u201c."
        ),
    )


@router.post(
    "",
    response_model=LaufAntwort,
    status_code=201,
    dependencies=[Depends(_pruefe_trainerschluessel)],
)
def beauftrage(
    bestellung: Bestellung, korpus: Korpus, sprecher: SprecherId
) -> LaufAntwort:
    """Einen Lauf beauftragen - der einzige Weg, der den Trainerschlüssel verlangt.

    Er steht vor allen anderen Prüfungen, und zwar mit Absicht: Wer nicht
    trainieren darf, soll nicht erfahren, wie viele Aufnahmen im Korpus eines
    Sprechers liegen oder ob eine Methode diesen Server kennt.
    """
    if bestellung.methode not in lauf_layout.METHODEN:
        raise HTTPException(status_code=400, detail=f"Unbekannte Methode: {bestellung.methode}")
    if bestellung.daten not in lauf_layout.DATENSAETZE:
        raise HTTPException(status_code=400, detail=f"Unbekannter Datensatz: {bestellung.daten}")
    if bestellung.abschluss not in lauf_layout.ABSCHLUESSE:
        raise HTTPException(
            status_code=400, detail=f"Unbekannter Abschluss: {bestellung.abschluss}"
        )
    if bestellung.augmentierung not in lauf_layout.AUGMENTIERUNGEN:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannte Augmentierung: {bestellung.augmentierung}",
        )
    if bestellung.dauer not in lauf_layout.DAUERN:
        raise HTTPException(status_code=400, detail=f"Unbekannte Dauer: {bestellung.dauer}")
    if bestellung.tempowahl not in lauf_layout.TEMPI:
        raise HTTPException(
            status_code=400, detail=f"Unbekannte Tempowahl: {bestellung.tempowahl}"
        )

    konfiguration = einstellungen()
    grundmodell = bestellung.grundmodell or konfiguration.lernen_basismodell
    if grundmodell not in konfiguration.grundmodelle():
        raise HTTPException(
            status_code=400, detail=f"Unbekanntes Grundmodell: {grundmodell}"
        )
    # Die eine Kombination, die es nicht gibt. Sie hier abzuweisen kostet
    # nichts; sie zuzulassen kostete zwei Stunden und endete am Speicher.
    erlaubte = lauf_layout.methoden_fuer(grundmodell)
    if bestellung.methode not in erlaubte:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{lauf_layout.kurzname(grundmodell)} lässt sich nur mit "
                f"{', '.join(erlaubte)} trainieren - volles Feintuning sprengt "
                "den Speicher der Karte."
            ),
        )
    proben = aufteilung.proben(korpus)
    if not aufteilung.genug(proben):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Für sechsfache Kreuzvalidierung braucht es mindestens "
                f"{lauf_layout.FALTUNGEN} brauchbare Aufnahmen - vorhanden sind "
                f"{len(proben)}."
            ),
        )

    lauf = auftraege.beauftrage(
        konfiguration.data_dir,
        korpus,
        proben,
        auftraege.Auftrag(
            sprecher_id=sprecher,
            methode=bestellung.methode,
            daten=bestellung.daten,
            abschluss=bestellung.abschluss,
            augmentierung=bestellung.augmentierung,
            dauer=bestellung.dauer,
            tempowahl=bestellung.tempowahl,
            basismodell=grundmodell,
        ),
    )
    return _als_antwort(lauf)


@router.get("/{job_id}", response_model=EinzelAntwort)
def einzeln(
    job_id: str, korpus: Korpus, sprecher: SprecherId, intervall: str = streuung.AUS
) -> EinzelAntwort:
    """Kurven, Bewertung und Vergleich zu einem Lauf.

    `intervall` legt neben jedes Gegenüber den gepaarten Abstand samt Bereich
    und p-Wert (`wortlaut/streuung.py`). Ohne den Parameter kommt genau die
    Antwort von vorher: Die Zahlen ändern sich nicht, es kommt nur eine
    Auskunft darüber dazu, wie weit sie tragen.
    """
    if intervall not in streuung.BLOCKARTEN:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannte Blockart. Zur Wahl stehen: {', '.join(streuung.BLOCKARTEN)}.",
        )
    lauf = _hole(sprecher, job_id)
    kurven = auftraege.lernkurve(lauf)
    protokoll = lauf.verzeichnis / lauf_layout.PROTOKOLL
    return EinzelAntwort(
        lauf=_als_antwort(lauf),
        methoden=METHODEN,
        datensaetze=DATENSAETZE,
        abschluesse=ABSCHLUESSE,
        augmentierungen=AUGMENTIERUNGEN,
        dauern=DAUERN,
        tempi=TEMPI,
        grundmodelle=_grundmodelle(),
        kurve_training=[PunktAntwort(**_punkt(zeile)) for zeile in kurven["training"]],
        kurve_validierung=[PunktAntwort(**_punkt(zeile)) for zeile in kurven["validierung"]],
        vergleich={
            fassung: [
                GegenueberAntwort(
                    mass=eintrag.mass,
                    baseline=eintrag.baseline,
                    trainiert=eintrag.trainiert,
                    besser=eintrag.besser,
                    anzahl=eintrag.anzahl,
                    unterschied=eintrag.unterschied,
                    bereich_baseline=eintrag.bereich_baseline,
                    bereich_trainiert=eintrag.bereich_trainiert,
                )
                for eintrag in eintraege
            ]
            for fassung, eintraege in vergleich.je_fassung(lauf, korpus, intervall).items()
        },
        # Nur das Ende: Wer ein Protokoll liest, sucht den letzten Satz vor dem
        # Abbruch, nicht den ersten des Ladevorgangs.
        protokoll=protokoll.read_text(encoding="utf-8")[-4000:] if protokoll.is_file() else "",
        intervall=intervall,
        streuung_marke=(
            streuung.Verfahren(blockart=intervall).marke if intervall != streuung.AUS else ""
        ),
    )


def _punkt(zeile: dict) -> dict:
    """Nur die Felder, die die Kurve kennt - der Trainer darf mehr schreiben."""
    return {
        "schritt": int(zeile.get("schritt", 0)),
        "epoche": float(zeile.get("epoche", 0.0)),
        "verlust": zeile.get("verlust"),
        "lernrate": zeile.get("lernrate"),
        "wer": zeile.get("wer"),
    }


class GeloeschtAntwort(BaseModel):
    job_id: str
    # Die Version des mitgelöschten Modellstands; leer, wenn es keinen gab.
    version: str
    war_freigegeben: bool


@router.delete("/{job_id}", response_model=GeloeschtAntwort)
def loeschen(job_id: str, sprecher: SprecherId) -> GeloeschtAntwort:
    """Einen Lauf ersatzlos entfernen - samt dem Modell, das aus ihm entstand.

    Ersatzlos heißt ersatzlos: Es gibt keinen Papierkorb und keinen Weg
    zurück. Die Sicherheitsabfrage steht in der Oberfläche und nennt vorher,
    was verschwindet (`frontend/src/routes/Training.svelte`); hier wird nur
    noch getan, was bestätigt wurde.

    Warum das Modell mitgeht und die Aufteilung nicht, steht in
    `services/auftraege.py`.
    """
    _hole(sprecher, job_id)  # 404, wenn er einem anderen gehört
    try:
        geloescht = auftraege.loesche(einstellungen().data_dir, sprecher, job_id)
    except LookupError as ursache:
        raise HTTPException(status_code=404, detail="Unbekannter Lauf.") from ursache
    except RuntimeError as ursache:
        raise HTTPException(status_code=409, detail=str(ursache)) from ursache

    return GeloeschtAntwort(
        job_id=geloescht.job_id,
        version=geloescht.version,
        war_freigegeben=geloescht.war_freigegeben,
    )


@router.post("/{job_id}/abbruch", response_model=LaufAntwort)
def abbrechen(job_id: str, sprecher: SprecherId) -> LaufAntwort:
    lauf = _hole(sprecher, job_id)
    if not auftraege.brich_ab(einstellungen().data_dir, job_id):
        raise HTTPException(
            status_code=409,
            detail="Dieser Lauf wartet nicht mehr - zurücknehmen lässt sich nur ein wartender.",
        )
    return _als_antwort(_hole(sprecher, job_id))
