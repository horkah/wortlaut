"""Textquelle „LLM": Thema und Altersspanne → Vorlesetext.

Ein Adapter, ein Anbieter. Weitere Anbieter kommen als weitere Funktion in
`_ANBIETER` dazu; der Rest des Systems sieht nur `erzeuge_text()`.

Wichtig für den Datenschutz: Hier verlässt nur das *Thema* den Server, nie
Stimm- oder Personendaten. Der Schalter ist trotzdem bewusst gesetzt — ohne
`WORTLAUT_LLM_PROVIDER` bleibt die Quelle abgeschaltet.
"""

from __future__ import annotations

from dataclasses import dataclass

SYSTEMANWEISUNG = (
    "Du schreibst deutsche Vorlesetexte für Sprachaufnahmen. "
    "Antworte ausschließlich mit dem Text selbst: Fließtext in ganzen Sätzen, "
    "keine Überschriften, keine Aufzählungen, keine Formatierung, keine Anrede "
    "und keine Erklärung deiner Antwort. Verwende geläufige Wörter und Sätze von "
    "höchstens etwa zwanzig Wörtern, damit der Text gut sprechbar ist."
)


@dataclass(frozen=True)
class Auftrag:
    """Die Parameter, die später zur Nachvollziehbarkeit gespeichert werden."""

    thema: str
    altersspanne: str  # z. B. „8-12" oder „Erwachsene"
    umfang: int  # ungefähre Wortzahl


def erzeuge_text(
    auftrag: Auftrag,
    *,
    anbieter: str,
    api_schluessel: str,
    modell: str,
    basis_url: str = "",
) -> str:
    """Erzeugt einen Vorlesetext. Wirft `ValueError` bei unbekanntem Anbieter.

    Ob ein Schlüssel nötig ist, entscheidet der Anbieter selbst: „anthropic"
    verlangt einen, „openai" (Ollama & Verwandte) kommt lokal ohne aus.
    """
    if not anbieter:
        raise ValueError("Keine Textquelle konfiguriert (WORTLAUT_LLM_PROVIDER ist leer).")
    if anbieter not in _ANBIETER:
        raise ValueError(f"Unbekannter LLM-Anbieter: {anbieter!r}")
    return _ANBIETER[anbieter](
        auftrag, api_schluessel=api_schluessel, modell=modell, basis_url=basis_url
    ).strip()


def _nutzeranweisung(auftrag: Auftrag) -> str:
    return (
        f"Thema: {auftrag.thema}\n"
        f"Zielgruppe (Alter): {auftrag.altersspanne}\n"
        f"Umfang: etwa {auftrag.umfang} Wörter"
    )


def _openai(auftrag: Auftrag, *, api_schluessel: str, modell: str, basis_url: str) -> str:
    """Jeder Anbieter mit OpenAI-kompatibler Schnittstelle — dieselbe Funktion
    für Ollama (lokal), Groq, Gemini oder Mistral; sie unterscheiden sich nur
    in `basis_url` und (außer Ollama) im Schlüssel.
    """
    import httpx

    if not basis_url:
        raise ValueError("WORTLAUT_LLM_BASE_URL fehlt (z. B. http://ollama:11434/v1).")
    kopf = {"Authorization": f"Bearer {api_schluessel}"} if api_schluessel else {}
    try:
        antwort = httpx.post(
            f"{basis_url.rstrip('/')}/chat/completions",
            headers=kopf,
            json={
                "model": modell,
                "messages": [
                    {"role": "system", "content": SYSTEMANWEISUNG},
                    {"role": "user", "content": _nutzeranweisung(auftrag)},
                ],
                # Ollama deckelt sonst früh; großzügig am Umfang bemessen.
                "max_tokens": max(512, auftrag.umfang * 4),
            },
            # Beim ersten Aufruf lädt ein lokales Modell erst in den Speicher.
            timeout=300,
        )
    except httpx.HTTPError as fehler:
        raise ValueError(f"Textquelle nicht erreichbar: {fehler}") from fehler
    if antwort.status_code != 200:
        raise ValueError(
            f"Textquelle antwortete mit {antwort.status_code}: {antwort.text[:200]}"
        )
    daten = antwort.json()
    try:
        return daten["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as fehler:
        raise ValueError(f"Unerwartete Antwort der Textquelle: {str(daten)[:200]}") from fehler


def _anthropic(auftrag: Auftrag, *, api_schluessel: str, modell: str, basis_url: str = "") -> str:
    # `basis_url` bleibt hier ungenutzt: Alle Adapter haben dieselbe Signatur,
    # damit `erzeuge_text` sie ohne Sonderfall aufrufen kann. Die Adresse von
    # Claude steht fest.
    if not api_schluessel:
        raise ValueError("WORTLAUT_LLM_API_KEY fehlt.")
    # Erst hier importieren: wer die LLM-Quelle nicht nutzt, braucht das Paket
    # zur Laufzeit nicht zu laden.
    import anthropic

    klient = anthropic.Anthropic(api_key=api_schluessel)
    antwort = klient.messages.create(
        model=modell,
        # Großzügig bemessen: bei aktuellen Modellen zählt auch das Nachdenken
        # gegen dieses Budget, und ein abgeschnittener Text wäre unbrauchbar.
        max_tokens=8000,
        system=SYSTEMANWEISUNG,
        # Niedriger Aufwand genügt: Text schreiben ist keine Denksportaufgabe,
        # und die Antwort soll schnell da sein.
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": _nutzeranweisung(auftrag)}],
    )
    if antwort.stop_reason == "refusal":
        raise ValueError("Das Sprachmodell hat die Anfrage abgelehnt. Bitte Thema ändern.")
    return "\n\n".join(block.text for block in antwort.content if block.type == "text")


_ANBIETER = {"anthropic": _anthropic, "openai": _openai}
