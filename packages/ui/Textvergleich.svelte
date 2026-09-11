<script lang="ts">
  /**
   * Vorlage und Erkennung in **einer** Zeile: unverändertes normal, Fehlendes
   * grau durchgestrichen, Hinzugekommenes farbig und fett.
   *
   * Zwei Absätze untereinander wären die naheliegende Darstellung und die
   * unbrauchbare: Wer zwei fast gleiche Sätze vergleicht, findet den einen
   * abweichenden Buchstaben nicht. Hier steht er als Einziges hervorgehoben da.
   *
   * Die Auszeichnung trägt nie allein die Farbe: Durchgestrichen und fett
   * sagen dasselbe noch einmal, und `<del>`/`<ins>` sagen es auch einer
   * Vorlesestimme. Wer Farben nicht unterscheiden kann - oder sie unter
   * „Darstellung" gerade auf etwas Eigenes gestellt hat -, sieht den
   * Unterschied trotzdem.
   */
  import { vergleiche } from './diff';

  let { vorlage, erkannt }: { vorlage: string; erkannt: string } = $props();

  const stuecke = $derived(vergleiche(vorlage, erkannt));
</script>

<p class="vergleich">
  {#each stuecke as stueck, nummer (nummer)}
    {#if stueck.art === 'gleich'}<span>{stueck.text}</span>
    {:else if stueck.art === 'weg'}<del title="fehlt in der Erkennung">{stueck.text}</del>
    {:else}<ins title="zusätzlich erkannt">{stueck.text}</ins>{/if}
  {/each}
</p>

<style>
  /* `pre-wrap`, damit ein gestrichenes Leerzeichen sichtbar bleibt: Ohne das
     fiele es mit dem nächsten zusammen, und der Strich wäre weg. */
  .vergleich {
    margin: 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    line-height: 1.55;
  }

  del {
    color: var(--gedaempft);
    text-decoration: line-through;
    /* Ein gestrichenes Leerzeichen braucht Breite, sonst zeigt es nichts. */
    text-decoration-thickness: 2px;
  }

  ins {
    color: var(--fehler);
    font-weight: 700;
    text-decoration: none;
    /* Ein Hauch Hinterlegung, damit auch ein einzelnes Zeichen auffällt -
       fett allein trägt bei einem Buchstaben zu wenig. */
    background: color-mix(in srgb, var(--fehler) 12%, transparent);
    border-radius: 0.15rem;
  }
</style>
