<script lang="ts">
  /**
   * Was dasteht, wenn dieser Browser niemanden vorweisen kann - dieselbe
   * Ansicht in jeder App.
   *
   * Ohne Zugang gibt keine API etwas her (`backend/deps.py`); hier steht der
   * eine Schritt, der weiterführt - einmal für alle Apps, denn der Zugang
   * gilt überall (`zugang.ts`).
   *
   * Der persönliche Link ist der übliche Weg und verlangt niemandem etwas zu
   * tippen ab. Das Feld unter „Zugangsdaten" ist der Ausweg für den, der einen
   * Zugang von Hand einsetzt - und zugleich der einzige Weg in Verwaltung und
   * Aufsicht, aus jeder App (`Zugangsdaten.svelte`).
   *
   * Eingehängt wird sie vom Rahmen (`Rahmen.svelte`), nicht von den Apps.
   */
  import { ZUGANGSDATEN_PFAD } from './apps';
  import { gehZu } from './route';
</script>

<h2>Kein Zugang</h2>

<div class="karte">
  <p>Bitte den persönlichen Link öffnen.</p>
  <button class="knopf haupt" onclick={() => gehZu(ZUGANGSDATEN_PFAD)}>Zu den Zugangsdaten</button>
</div>
