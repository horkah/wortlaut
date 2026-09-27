<script lang="ts">
  /**
   * Was „lernen" an eigenen Ansichten hat - der Rahmen darum steht in
   * `$ui/Rahmen.svelte` und ist in jeder App derselbe, samt Menü.
   *
   * Die Reiter (`REITER` in `$ui/apps`) folgen dem Weg durch die Arbeit:
   * Aufteilung, Training, Modelle. „Modelle" ist auch das Ziel eines Klicks
   * auf das Modell in „schreiben" und „hören" - samt Grundmodellen.
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
