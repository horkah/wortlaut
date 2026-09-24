<script lang="ts">
  /**
   * Der Knopf, der einen Lauf löscht - auf der Karte unter „Training" und in
   * der Einzelansicht derselbe.
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
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6" />
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
