<script lang="ts">
  /**
   * Was dasteht, wenn dieser Browser niemanden vorweisen kann.
   *
   * Ohne Zugang gäbe es hier nur abgewiesene Anfragen: kein Modell, keine
   * Sitzung, kein Diktat (siehe `backend/deps.py`). Ein Aufnahmeknopf, der
   * jedes Mal in einen Fehler läuft, wäre die schlechtere Antwort - also
   * steht hier der eine Schritt, der weiterführt.
   *
   * Der persönliche Link ist der übliche Weg und braucht niemanden, der tippt.
   * Das Feld unter „Zugangsdaten" ist der Ausweg für den Fall, dass jemand den
   * Zugang von Hand einsetzt.
   */
  import { ZUGANGSDATEN_PFAD } from '$ui/apps';
  import { gehZu } from '../lib/zustand.svelte';
</script>

<h2>Kein Zugang</h2>

<div class="karte">
  <p>
    Dieser Browser gehört noch zu niemandem. Was hier diktiert wird, gehört einem Menschen: Es
    läuft auf seinem Modell und geht in seinen Korpus zurück.
  </p>
  <p>
    Der persönliche Link, einmal geöffnet, genügt - derselbe wie bei „hören". Danach ist hier
    nichts mehr einzutragen.
  </p>
  <button class="knopf haupt" onclick={() => gehZu(ZUGANGSDATEN_PFAD)}>Zu den Zugangsdaten</button>
</div>
