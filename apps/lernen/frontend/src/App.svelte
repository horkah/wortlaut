<script lang="ts">
  /**
   * Was „lernen" an eigenen Ansichten hat - der Rahmen darum steht in
   * `$ui/Rahmen.svelte` und ist in jeder App derselbe, samt Menü.
   *
   * Drei Reiter (`REITER` in `$ui/apps`), und ihre Reihenfolge ist der Weg
   * durch die Arbeit: nachsehen, wie die Aufnahmen aufgeteilt sind, ein
   * Training beauftragen und ihm zusehen, und am Ende entscheiden, welches
   * Modell gelten soll.
   *
   * Die letzte davon - „Modelle" - ist zugleich die Ansicht, auf der auch
   * „schreiben" und „hören" landen, wenn dort jemand auf das Modell klickt.
   * Sie liegt hier, weil hier die Stände entstehen; sie zeigt aber alles, was
   * dieser Mensch laden kann, die unveränderten Grundmodelle eingeschlossen.
   */
  import Rahmen from '$ui/Rahmen.svelte';
  import Zugangsdaten from '$ui/Zugangsdaten.svelte';
  import { MODELLE_PFAD } from '$ui/apps';
  import { lage, laufAusRoute } from './lib/zustand.svelte';
  import Aufteilung from './routes/Aufteilung.svelte';
  import Training from './routes/Training.svelte';
  import Lauf from './routes/Lauf.svelte';
  import Modelle from './routes/Modelle.svelte';

  const ANSICHTEN = {
    '/aufteilung': Aufteilung,
    '/training': Training,
    [MODELLE_PFAD]: Modelle,
  };

  // Nur ein Sprecher hat hier etwas zu sehen: Ein Modell gehört zu genau einem
  // Menschen, und der Korpus, auf dem es lernt, hängt am Zugang. Wer anders
  // hier ist, sieht die Zugangsdaten - dort steht, wer er ist, und wie er es
  // ändert; die Sprecherliste findet er danach im Menü.
  const spricht = $derived(lage.art === 'sprecher');

  // Ein einzelner Lauf gehört zu „Training": Er ist keine eigene Ansicht in
  // der Reihe, sondern das, was hinter einem Klick darin liegt.
  const imLauf = $derived(!!laufAusRoute(lage.route));
</script>

<Rahmen
  app="lernen"
  ansichten={spricht ? ANSICHTEN : {}}
  ansicht={!spricht ? Zugangsdaten : imLauf ? Lauf : null}
  markiert={imLauf ? '/training' : undefined}
/>
