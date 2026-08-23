<script lang="ts">
  /**
   * Der Seitenfuß: eine Zeile, die sagt, welcher Stand hier läuft (`bau.ts`).
   *
   * Bewusst leise und ganz unten - wer sie nicht braucht, soll sie nicht
   * bemerken. „Ganz unten" heißt: am Fuß des Fensters, nicht bloß am Ende des
   * Inhalts - bei kurzem Inhalt bleibt sonst darüber eine Lücke, die wie ein
   * Fehler aussieht. Das erledigt `main { flex: 1 }` in `app.css`.
   */
  import { BAUDATUM, baudatumLesbar } from './bau';
</script>

<footer class="fuss">
  <!-- Maschinenlesbar im `datetime`, lesbar im Text. -->
  App gebaut am: <time datetime={BAUDATUM}>{baudatumLesbar()}</time>
</footer>

<style>
  .fuss {
    margin: 3rem 0 1.25rem;
    text-align: center;
    font-size: 0.75rem;
    color: var(--gedaempft);
  }
</style>
