<script lang="ts">
  /**
   * Die gemeinsamen Geräteeinstellungen — Mikrofon, Stimme, Tempo.
   *
   * Der Zugang dieser Instanz (Verwalter- und Aufsichtstoken) steht nicht
   * hier, sondern unter „Zugangsdaten" (`ZUGANGSDATEN_PFAD`, siehe
   * `Zugangsdaten.svelte`): ein eigener Menüpunkt, aus demselben Grund wie
   * „Darstellung" — wer ein Mikrofon einmisst, blättert nicht an einem
   * Formular für Serverzugänge vorbei.
   */
  import Gemeinsam from '$ui/Einstellungen.svelte';
</script>

<Gemeinsam />
