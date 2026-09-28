"""Was am Ende mit den Gewichten geschieht - nach der Schleife, vor dem Sichern.

Zwei Handgriffe ohne zusätzliches Training, außerhalb der Trainingsschleife:

* **Mittelung** („Model Soup"): die besten Zwischenstände elementweise
  gemittelt. Sie liegen in derselben Verlustmulde; das Mittel ist meist etwas
  robuster und kostet zur Laufzeit nichts.
* **Interpolation mit dem Grundmodell** (WiSE-FT): θ = α·θ_grund + (1−α)·θ_fein -
  katastrophales Vergessen als Regler, eingestellt nach dem Training.

Beides ist eine Achse des Auftrags, keine stille Rezeptänderung, damit die
Tafel zeigt, was wirkt; `bester` lässt den besten Durchgang unverändert.

**α wird an der Steuergröße gewählt** (`steuerung.py`), derselben Größe, an
der `load_best_model_at_end` den besten Durchgang erkennt: dem
Validierungsverlust oder, bei `wer`, der frei dekodierten WER - dann kostet
jedes α eine Dekodierung. In einer Faltung ist die Validierung die
zurückgehaltene Faltung selbst.

**Nie schlechter als der Anfang.** α = 0 steht im Raster, doch bei `beides`
beginnt die Interpolation beim gemittelten Stand. Deshalb merkt sich der
Abschluss den Stand, mit dem er anfängt, und stellt ihn wieder her, wenn er am
Ende schlechter dasteht; `zurueckgenommen` steht dann am Stand.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from wortlaut import laeufe

# Wie die Zwischenstände des Trainers heißen: `checkpoint-<schritt>`.
STAND_PRAEFIX = "checkpoint-"

# Wo die Gewichte eines Zwischenstandes stehen können: bei LoRA der Zusatz
# allein, sonst das ganze Modell; `.bin` schreiben manche `transformers`-Fassungen.
GEWICHTSDATEIEN = (
    "adapter_model.safetensors",
    "model.safetensors",
    "pytorch_model.bin",
)

# Wie viele Zwischenstände gemittelt werden, wenn das Rezept nichts sagt.
STAENDE = 3

# Welche Anteile des Grundmodells versucht werden, wenn das Rezept nichts sagt.
# Bis zur Hälfte - hilft mehr, taugte das Training nicht.
ALPHAS = (0.0, 0.1, 0.2, 0.3, 0.5)


@dataclass(frozen=True)
class Ergebnis:
    """Was der Abschluss getan hat - für Protokoll, Fortschritt und Registry.

    Steht neben dem Modellstand, damit sein α nachzusehen ist.
    """

    art: str
    # Die Steuergröße, in der alle `verlust_*` stehen: `loss` oder `wer`.
    mass: str = "loss"
    # Die gemittelten Zwischenstände, bei ihrem Namen (`checkpoint-63`).
    staende: tuple[str, ...] = ()
    # Der gewählte Anteil des Grundmodells; `None` ohne Interpolation.
    alpha: float | None = None
    # Die Steuergröße vor und nach dem Abschluss.
    verlust_vorher: float | None = None
    verlust_nachher: float | None = None
    # Nach der Mittelung, vor der Interpolation - zeigt bei `beides`, was wirkte.
    verlust_mittel: float | None = None
    # Je versuchtem α sein Verlust - die Kurve hinter der Wahl.
    versuche: tuple[tuple[float, float], ...] = ()
    # Ob der Abschluss am Ende zurückgenommen wurde, weil er nicht half.
    zurueckgenommen: bool = False
    # Warum weniger geschah als bestellt.
    hinweis: str = ""

    def als_dict(self) -> dict[str, Any]:
        return {
            "art": self.art,
            "mass": self.mass,
            "staende": list(self.staende),
            "alpha": self.alpha,
            "verlust_vorher": self.verlust_vorher,
            "verlust_nachher": self.verlust_nachher,
            "verlust_mittel": self.verlust_mittel,
            "zurueckgenommen": self.zurueckgenommen,
            "versuche": [list(paar) for paar in self.versuche],
            "hinweis": self.hinweis,
        }


@dataclass
class _Sammler:
    """Was während des Abschlusses zusammenkommt - innen, damit außen ein `Ergebnis` steht."""

    art: str
    mass: str = "loss"
    staende: list[str] = field(default_factory=list)
    alpha: float | None = None
    verlust_vorher: float | None = None
    verlust_nachher: float | None = None
    verlust_mittel: float | None = None
    zurueckgenommen: bool = False
    versuche: list[tuple[float, float]] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)

    def fertig(self) -> Ergebnis:
        return Ergebnis(
            art=self.art,
            mass=self.mass,
            staende=tuple(self.staende),
            alpha=self.alpha,
            verlust_vorher=self.verlust_vorher,
            verlust_nachher=self.verlust_nachher,
            verlust_mittel=self.verlust_mittel,
            zurueckgenommen=self.zurueckgenommen,
            versuche=tuple(self.versuche),
            hinweis=" ".join(self.hinweise),
        )


def pruefe(art: str) -> str:
    """Die bestellte Art, oder ein Fehler - und zwar sofort, nicht nach Stunden."""
    if art not in laeufe.ABSCHLUESSE:
        raise RuntimeError(
            f"Unbekannter Abschluss: {art}. Zur Wahl stehen: {', '.join(laeufe.ABSCHLUESSE)}."
        )
    return art


def staende_aus(rezept: dict[str, Any]) -> int:
    """Wie viele Zwischenstände gemittelt werden sollen - mindestens zwei."""
    gewuenscht = int((rezept.get("abschluss") or {}).get("staende", STAENDE))
    return max(2, gewuenscht)


def alphas_aus(rezept: dict[str, Any]) -> tuple[float, ...]:
    """Das α-Raster des Rezepts; die Null kommt dazu, falls sie fehlt."""
    roh = (rezept.get("abschluss") or {}).get("alphas") or ALPHAS
    werte = sorted({round(float(wert), 4) for wert in roh} | {0.0})
    return tuple(wert for wert in werte if 0.0 <= wert < 1.0)


def zu_behalten(art: str, rezept: dict[str, Any]) -> int:
    """Wie viele Zwischenstände auf der Platte bleiben müssen (`save_total_limit`).

    Einer ohne Mittelung, sonst so viele, wie gemittelt werden.
    """
    return staende_aus(rezept) if laeufe.mittelt(art) else 1


# ── Zwischenstände lesen ────────────────────────────────────────────────────


def _verluste(trainer, mass: str = "loss") -> dict[int, float]:
    """Schritt → Steuergröße (`eval_loss`, `eval_wer`), aus dem Protokoll des Trainers."""
    schluessel = f"eval_{mass}"
    gefunden: dict[int, float] = {}
    for zeile in trainer.state.log_history:
        if schluessel in zeile and "step" in zeile:
            gefunden[int(zeile["step"])] = float(zeile[schluessel])
    return gefunden


def beste_staende(trainer, arbeitsstand: Path, anzahl: int, mass: str = "loss") -> list[Path]:
    """Die besten noch vorhandenen Zwischenstände, bester zuerst.

    „Noch vorhanden" ist die halbe Arbeit: Der Trainer räumt nach
    `save_total_limit` auf, und was weg ist, ist weg. Deshalb wird hier nicht
    aus dem Protokoll geschlossen, welche es geben müsste, sondern nachgesehen,
    welche es gibt.
    """
    if not arbeitsstand.is_dir():
        return []
    verluste = _verluste(trainer, mass)
    vorhanden: list[tuple[float, int, Path]] = []
    for pfad in arbeitsstand.iterdir():
        if not pfad.is_dir() or not pfad.name.startswith(STAND_PRAEFIX):
            continue
        try:
            schritt = int(pfad.name.rsplit("-", 1)[-1])
        except ValueError:
            continue
        if schritt not in verluste or _gewichtsdatei(pfad) is None:
            continue
        vorhanden.append((verluste[schritt], schritt, pfad))
    vorhanden.sort(key=lambda eintrag: (eintrag[0], eintrag[1]))
    return [pfad for _, _, pfad in vorhanden[:anzahl]]


def _gewichtsdatei(stand: Path) -> Path | None:
    for name in GEWICHTSDATEIEN:
        pfad = stand / name
        if pfad.is_file():
            return pfad
    return None


def _lies_gewichte(stand: Path) -> dict[str, Any]:
    """Die Gewichte eines Zwischenstandes, auf dem Prozessor."""
    import torch

    pfad = _gewichtsdatei(stand)
    if pfad is None:
        raise RuntimeError(f"Kein Gewichtsstand in {stand}")
    if pfad.suffix == ".safetensors":
        from safetensors.torch import load_file

        return load_file(str(pfad), device="cpu")
    return torch.load(str(pfad), map_location="cpu", weights_only=True)


# ── Mittelung ───────────────────────────────────────────────────────────────


def mittle(modell, staende: list[Path], ist_lora: bool) -> None:
    """Die Gewichte dieser Zwischenstände elementweise mitteln und einsetzen.

    Gerechnet wird auf dem Prozessor und in `float32`: Ein Mittel aus drei
    halbgenauen Summanden verlöre im letzten Bit mehr, als die Mittelung
    einbringt, und die Karte hat nach einem Training Besseres zu tun.

    **Bei LoRA wird der Zusatz gemittelt, nicht das verschmolzene Modell.** Das
    ist nicht dasselbe - B·A ist in B und A zusammen nicht linear -, es ist
    aber das, was sich ohne einen zweiten Satz voller Gewichte rechnen lässt,
    und es ist das übliche Vorgehen. Ob es taugt, sagt die Vergleichstafel.
    """
    import torch

    summe: dict[str, torch.Tensor] = {}
    for stand in staende:
        for name, wert in _lies_gewichte(stand).items():
            if not torch.is_floating_point(wert):
                continue
            teil = wert.to(torch.float32)
            summe[name] = teil if name not in summe else summe[name] + teil
    if not summe:
        raise RuntimeError("Die Zwischenstände enthalten keine Gewichte zum Mitteln.")

    gemittelt = {name: wert / len(staende) for name, wert in summe.items()}
    _setze_gewichte(modell, gemittelt, ist_lora)


def _setze_gewichte(modell, gewichte: dict[str, Any], ist_lora: bool) -> None:
    """Gewichte in ein Modell zurückschreiben - bei LoRA über peft.

    Über peft, weil der Zusatz unter anderen Namen gesichert wird, als er im
    Modell heißt (`…lora_A.weight` gegen `…lora_A.default.weight`). Ein
    `load_state_dict` träfe damit nichts und meldete es nicht einmal.
    """
    if ist_lora:
        from peft import set_peft_model_state_dict

        set_peft_model_state_dict(modell, gewichte)
        return
    fehlt = modell.load_state_dict(gewichte, strict=False)
    # `proj_out.weight` teilt sich bei Whisper die Gewichte mit der
    # Einbettung und steht deshalb in keiner Sicherung - das ist keiner der
    # Fälle, vor denen zu warnen wäre. Unerwartete Namen dagegen schon: Dann
    # passt der Stand nicht zum Modell.
    if getattr(fehlt, "unexpected_keys", None):
        raise RuntimeError(f"Fremde Gewichte im Zwischenstand: {fehlt.unexpected_keys[:3]}")


# ── Interpolation mit dem Grundmodell ───────────────────────────────────────


def _lora_zusaetze(modell) -> list[Any]:
    """Die B-Matrizen des LoRA-Zusatzes - die Stellschraube der Interpolation.

    Der Zusatz ist B·A, und beide starten so, dass anfangs nichts dazukommt.
    Wer B mit (1−α) malnimmt, nimmt den ganzen Zusatz mit (1−α) mal - und das
    ist **genau** die Interpolation: θ_grund + (1−α)·Δ. Für LoRA ist WiSE-FT
    damit kein Näherungsverfahren, sondern eine Multiplikation.
    """
    return [
        gewicht
        for name, gewicht in modell.named_parameters()
        if "lora_B" in name and gewicht.dim() >= 2
    ]


def _grundgewichte(basismodell: str) -> dict[str, Any]:
    """Die Gewichte des unveränderten Grundmodells, auf dem Prozessor."""
    from transformers import WhisperForConditionalGeneration

    grund = WhisperForConditionalGeneration.from_pretrained(basismodell)
    return {name: wert.detach().to("cpu") for name, wert in grund.state_dict().items()}


def interpoliere(
    modell,
    basismodell: str,
    alphas: Iterable[float],
    messe: Callable[[], float],
    ist_lora: bool,
    sage: Callable[[str], None],
    name: str = "Validierungsverlust",
) -> tuple[float, list[tuple[float, float]]]:
    """α auf der Validierung wählen und das Modell darauf einstellen.

    Gibt das gewählte α und alle Versuche zurück. Der Reihe nach: jedes α
    einstellen, die Steuergröße messen, das beste behalten - und zum
    Schluss noch einmal einstellen, damit das Modell den Stand trägt, der
    gewonnen hat.
    """
    import torch

    with torch.no_grad():
        if ist_lora:
            zusaetze = _lora_zusaetze(modell)
            urstand = [gewicht.detach().clone() for gewicht in zusaetze]

            def stelle_ein(alpha: float) -> None:
                for gewicht, urspruenglich in zip(zusaetze, urstand, strict=True):
                    gewicht.copy_(urspruenglich * (1.0 - alpha))
        else:
            grund = _grundgewichte(basismodell)
            eigen = modell.state_dict()
            # `.clone()`: Auf dem Prozessor gibt `.to("cpu")` denselben Speicher
            # zurück, und jedes α rechnete auf dem vorigen weiter.
            # Nur, was dieselbe Form hat - im gekürzten Fenster ist die feste
            # Positionseinbettung des Encoders kürzer (`fenster.py`).
            fein = {
                name: wert.detach().to("cpu", torch.float32).clone()
                for name, wert in eigen.items()
                if name in grund
                and torch.is_floating_point(wert)
                and grund[name].shape == wert.shape
            }

            def stelle_ein(alpha: float) -> None:
                for name, feingetunt in fein.items():
                    ziel = eigen[name]
                    gemischt = alpha * grund[name].to(torch.float32) + (1.0 - alpha) * feingetunt
                    ziel.copy_(gemischt.to(ziel.dtype))

        versuche: list[tuple[float, float]] = []
        for alpha in alphas:
            stelle_ein(alpha)
            verlust = messe()
            versuche.append((alpha, verlust))
            sage(f"  α = {alpha:.2f} · {name} {verlust:.5f}")

        bestes = min(versuche, key=lambda paar: paar[1])[0]
        stelle_ein(bestes)
    return bestes, versuche


# ── Der ganze Abschluss ─────────────────────────────────────────────────────


def fuehre_aus(
    art: str,
    modell,
    trainer,
    rezept: dict[str, Any],
    basismodell: str,
    arbeitsstand: Path,
    hat_pruefung: bool,
    bericht,
    alpha_vorgabe: float | None = None,
    mass: str = "loss",
) -> Ergebnis:
    """Den bestellten Abschluss rechnen; gibt zurück, was dabei herauskam.

    Das Modell wird dabei an Ort und Stelle verändert - danach steht in ihm
    der Stand, der gesichert und ausgeliefert wird.

    Das Endmodell hält nichts zurück und hat damit kein Maß. Es wendet das α
    der Faltungen an (`alpha_vorgabe`); die Mittelung entfällt, denn sie wählt
    unter Zwischenständen.

    `mass` ist die Steuergröße des Trainings (`steuerung.Pruefplan.mass`).
    """
    sammler = _Sammler(art=art, mass=mass)
    name = "Validierungs-WER" if mass == "wer" else "Validierungsverlust"
    if art == laeufe.ABSCHLUSS_BESTER:
        return sammler.fertig()

    if not hat_pruefung:
        if alpha_vorgabe is not None and laeufe.interpoliert(art):
            bericht.stufe("abschluss")
            _nur_interpolieren(modell, basismodell, float(alpha_vorgabe), bericht)
            sammler.alpha = float(alpha_vorgabe)
            sammler.hinweise.append(
                f"α = {float(alpha_vorgabe):.2f} aus den Faltungen übernommen, ohne "
                "eigene Messung. Gemittelt wurde nicht - dafür fehlt das Maß."
            )
            bericht.sage(sammler.hinweise[-1])
        else:
            sammler.hinweise.append(
                "Ohne Steuergröße nicht gerechnet - der Stand bleibt, wie er ist."
            )
            bericht.sage("Abschluss übersprungen: nichts zurückgehalten, nichts zu messen.")
        return sammler.fertig()

    bericht.stufe("abschluss")
    messe = _messer(trainer, mass)
    sammler.verlust_vorher = messe()
    bericht.sage(f"{name} vor dem Abschluss: {sammler.verlust_vorher:.5f}")

    ist_lora = _ist_lora(modell)
    # Der Anfangsstand, auf dem Prozessor - bei vollem Training ein Gigabyte,
    # der Preis dafür, dass der Abschluss nicht schaden kann.
    anfangsstand = _abzug(modell)

    if laeufe.mittelt(art):
        anzahl = staende_aus(rezept)
        staende = beste_staende(trainer, arbeitsstand, anzahl, mass)
        if len(staende) < 2:
            sammler.hinweise.append(
                "Weniger als zwei Zwischenstände auf der Platte - nicht gemittelt."
            )
            bericht.sage("Mittelung übersprungen: es liegt nur ein Zwischenstand.")
        else:
            sammler.staende = [pfad.name for pfad in staende]
            bericht.sage(f"Gemittelt über: {', '.join(sammler.staende)}")
            mittle(modell, staende, ist_lora)
            sammler.verlust_mittel = messe()
            bericht.sage(f"{name} nach der Mittelung: {sammler.verlust_mittel:.5f}")

    if laeufe.interpoliert(art):
        alpha, versuche = interpoliere(
            modell,
            basismodell,
            alphas_aus(rezept),
            messe,
            ist_lora,
            bericht.sage,
            name,
        )
        sammler.alpha = alpha
        sammler.versuche.extend(versuche)
        bericht.sage(f"Gewählt: α = {alpha:.2f} Grundmodell")

    sammler.verlust_nachher = messe()
    bericht.sage(f"{name} nach dem Abschluss: {sammler.verlust_nachher:.5f}")

    # Schlechter als der Anfang: zurücknehmen und es am Stand vermerken.
    if sammler.verlust_nachher > sammler.verlust_vorher:
        _einspielen(modell, anfangsstand)
        sammler.zurueckgenommen = True
        sammler.hinweise.append(
            f"Zurückgenommen: Der Abschluss lag mit {sammler.verlust_nachher:.5f} über "
            f"den {sammler.verlust_vorher:.5f} des besten Durchgangs. Ausgeliefert wird "
            "dieser."
        )
        bericht.sage(sammler.hinweise[-1])
        sammler.verlust_nachher = sammler.verlust_vorher
    anfangsstand.clear()

    ergebnis = sammler.fertig()
    # `art` heißt im Fortschritt die Art des Ereignisses; welcher Abschluss
    # gemeint ist, steht daneben als `verfahren`.
    felder = ergebnis.als_dict()
    bericht.ereignis(art="abschluss", verfahren=felder.pop("art"), **felder)
    return ergebnis


def _abzug(modell) -> dict[str, Any]:
    """Eine Kopie der Gewichte auf dem Prozessor - der Stand, zu dem es zurückgeht."""
    import torch

    with torch.no_grad():
        return {
            name: wert.detach().to("cpu").clone()
            for name, wert in modell.state_dict().items()
            if torch.is_floating_point(wert)
        }


def _einspielen(modell, stand: dict[str, Any]) -> None:
    """Den Abzug zurückschreiben - an Ort und Stelle, ohne das Modell zu tauschen."""
    import torch

    with torch.no_grad():
        eigen = modell.state_dict()
        for name, wert in stand.items():
            ziel = eigen.get(name)
            if ziel is not None:
                ziel.copy_(wert.to(ziel.device, ziel.dtype))


def _nur_interpolieren(modell, basismodell: str, alpha: float, bericht) -> None:
    """Ein gegebenes α anwenden, ohne zu messen - der Weg des Endmodells."""
    import torch

    ist_lora = _ist_lora(modell)
    with torch.no_grad():
        if ist_lora:
            for gewicht in _lora_zusaetze(modell):
                gewicht.mul_(1.0 - alpha)
        else:
            grund = _grundgewichte(basismodell)
            eigen = modell.state_dict()
            for name, wert in eigen.items():
                if (
                    name not in grund
                    or not torch.is_floating_point(wert)
                    or grund[name].shape != wert.shape
                ):
                    continue
                gemischt = alpha * grund[name].to(torch.float32) + (1.0 - alpha) * wert.detach().to(
                    "cpu", torch.float32
                )
                wert.copy_(gemischt.to(wert.dtype))
    bericht.sage(f"Mit dem Grundmodell verrechnet: α = {alpha:.2f} (aus den Faltungen)")


def _ist_lora(modell) -> bool:
    """Ob in diesem Modell ein LoRA-Zusatz steckt - gefragt, nicht geraten."""
    return any("lora_" in name for name, _ in modell.named_parameters())


def _messer(trainer, mass: str = "loss") -> Callable[[], float]:
    """Ein Aufruf, der die Steuergröße zurückgibt - Verlust oder WER.

    Mit eigenem Präfix, damit diese Messungen nicht in der Lernkurve landen:
    Dort steht der Verlust je Durchgang, und ein halbes Dutzend Punkte am
    selben Schritt machte aus der Kurve einen Strich (siehe die Rückmeldung in
    `finetune.py`, die Zeilen ohne `eval_loss` übergeht).
    """

    def messe() -> float:
        gemessen = trainer.evaluate(metric_key_prefix="abschluss")
        return float(gemessen.get(f"abschluss_{mass}", 0.0))

    return messe
