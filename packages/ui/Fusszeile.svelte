<script lang="ts">
  /**
   * Der Seitenfuß: eine Zeile, die sagt, welcher Stand hier läuft (`bau.ts`).
   *
   * Bewusst leise und ganz unten - wer sie nicht braucht, soll sie nicht
   * bemerken. „Ganz unten" heißt: am Fuß des Fensters, nicht bloß am Ende des
   * Inhalts - bei kurzem Inhalt bleibt sonst darüber eine Lücke, die wie ein
   * Fehler aussieht. Das erledigt `main { flex: 1 }` in `app.css`.
   */
  import { BAUDATUM, baudatumLesbar, lesbar } from './bau';

  /**
   * Der Stand kommt vom **Server**, nicht aus diesem Bündel.
   *
   * Im Bündel steht er nur so lange richtig, wie sich am Frontend etwas
   * ändert: Wird allein das Backend angefasst, bleiben die Frontend-Stufen
   * unverändert, BuildKit nimmt sie aus dem Zwischenspeicher - samt des
   * Datums darin. Der Seitenfuß zeigte dann tagelang dieselbe Uhrzeit,
   * während dreimal ausgerollt wurde.
   *
   * Gefragt wird `/gesundheit` - ohne Wächter, auf der Wurzel und damit aus
   * jeder App erreichbar (dieselbe Überlegung wie bei `wer.ts`). Bis die
   * Antwort da ist, und wenn sie ausbleibt, steht das Datum aus dem Bündel da:
   * In der Entwicklung gibt es kein Abbild, und dort ist es die richtige
   * Auskunft.
   */
  let vomServer = $state<string | null>(null);

  $effect(() => {
    fetch('/gesundheit')
      .then((antwort) => (antwort.ok ? antwort.json() : null))
      .then((antwort) => {
        const gemeldet = antwort?.stand;
        if (gemeldet && gemeldet !== 'Entwicklung') vomServer = gemeldet;
      })
      .catch(() => {
        // Keine Antwort ist keine Meldung wert - dann gilt das Bündeldatum.
      });
  });

  const gezeigt = $derived(vomServer ?? BAUDATUM);
  const geschrieben = $derived(vomServer ? lesbar(vomServer) : baudatumLesbar());
</script>

<footer class="fuss">
  <!-- Maschinenlesbar im `datetime`, lesbar im Text. -->
  App gebaut am: <time datetime={gezeigt}>{geschrieben}</time>
</footer>

<style>
  .fuss {
    margin: 3rem 0 1.25rem;
    text-align: center;
    font-size: 0.75rem;
    color: var(--gedaempft);
  }
</style>
