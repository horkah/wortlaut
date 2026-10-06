<script lang="ts">
  /**
   * Der eine Papierkorb der ganzen Familie: wo immer ein einzelner Eintrag
   * gelöscht oder verworfen wird - ein Lauf in „lernen", eine Textquelle, eine
   * Aufnahme in „Meine Daten" und in der Einsicht. Ein Sinnbild, ein Strich,
   * ein Verhalten; wer es einmal kennt, erkennt es überall.
   *
   * Sammelaktionen mit Zahl („Löschen (3)") bleiben beschriftete Knöpfe: Dort
   * ist die Zahl die Auskunft, und die trägt kein Sinnbild.
   *
   * Beschriftet für Vorlesestimmen (`label`), denn ein Sinnbild allein sagt
   * nichts.
   */
  let {
    title,
    label,
    disabled = false,
    onclick,
  }: { title: string; label: string; disabled?: boolean; onclick: () => void } = $props();
</script>

<button class="papierkorb" {title} aria-label={label} {disabled} {onclick}>
  <!-- Strich und Maß stehen als Attribute, nicht nur im Stylesheet: Die
       Linien haben keine Fläche, ein reiner `fill` zeichnet also nichts.
       Bliebe das CSS einmal aus, wäre der Knopf unsichtbar statt unschön. -->
  <svg
    viewBox="0 0 24 24"
    width="18"
    height="18"
    fill="none"
    stroke="currentColor"
    stroke-width="1.75"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path
      d="M4 7h16M9.5 7V5.5A1.5 1.5 0 0 1 11 4h2a1.5 1.5 0 0 1 1.5 1.5V7M6 7l.8 11.2A2 2 0 0 0 8.8 20h6.4a2 2 0 0 0 2-1.8L18 7M10 11v5M14 11v5"
    />
  </svg>
</button>

<style>
  /* Leise, bis man darauf zeigt: Der Weg hinaus soll zu finden, aber nicht das
     Auffälligste sein. Die Fläche ist trotzdem groß genug für einen Daumen. */
  .papierkorb {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: none;
    width: 2.2rem;
    height: 2.2rem;
    padding: 0;
    border: 1px solid transparent;
    border-radius: 0.35rem;
    background: none;
    color: var(--gedaempft);
    cursor: pointer;
  }

  .papierkorb:hover:not(:disabled),
  .papierkorb:focus-visible {
    color: var(--fehler);
    border-color: var(--rand);
  }

  .papierkorb:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }
</style>
