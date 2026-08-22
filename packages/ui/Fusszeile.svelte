<script lang="ts">
  /**
   * Der Seitenfuß: eine Zeile, die sagt, welcher Stand hier läuft.
   *
   * Bewusst leise und ganz unten — das ist keine Information für die Arbeit,
   * sondern für den Zweifel: „Sehe ich gerade die neue Fassung?" Wer sie nicht
   * braucht, soll sie nicht bemerken.
   */
  import { BAUDATUM, baudatumLesbar } from './bau';
</script>

<footer class="fuss">
  <!-- Maschinenlesbar im `datetime`, lesbar im Text. -->
  Stand: <time datetime={BAUDATUM}>{baudatumLesbar()}</time>
</footer>

<style>
  .fuss {
    margin: 3rem 0 1.25rem;
    text-align: center;
    font-size: 0.75rem;
    color: var(--gedaempft);
  }
</style>
