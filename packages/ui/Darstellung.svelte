<script lang="ts">
  /**
   * Farben, Schriftart und Schriftgrößen - eine eigene Ansicht neben
   * `Einstellungen.svelte`.
   *
   * Warum getrennt: siehe `DARSTELLUNG_PFAD` in `apps.ts`. Die Werte selbst,
   * ihre Vorgaben und wie sie auf die App wirken, stehen in
   * `einstellungen.svelte.ts`; hier steht nur die Bedienung dazu.
   */
  import PinSchloss from './PinSchloss.svelte';
  import PromptView from './PromptView.svelte';
  import { SCHALTBARE_APPS, SCHALTBARE_MENUEPUNKTE, type Schaltbar } from './apps';
  import {
    einstellungen,
    setzeDarstellungZurueck,
    setzeFarbe,
    setzeGrundschrift,
    setzeSchrift,
    setzeSchriftart,
    setzeSichtbar,
    FARBEN,
    GRUNDSCHRIFT_SPANNE,
    SCHRIFT_SPANNE,
    SCHRIFTARTEN,
  } from './einstellungen.svelte';

  const PROBE = 'Am Montag gehe ich zum Markt und kaufe frisches Brot.';

  // Zwei Abschnitte, weil es zwei Ebenen sind - dieselben zwei, die die
  // Kopfleiste zeigt: oben die App, dahinter im Menüknopf ihre Punkte.
  const ABSCHNITTE: { titel: string; hinweis: string; eintraege: Schaltbar[] }[] = [
    {
      titel: 'Apps in der Kopfleiste',
      hinweis:
        'Die Reiter ganz oben. Ausgeblendet ist eine App nur aus der Leiste verschwunden, nicht abgeschaltet - ihre Adresse gilt weiter.',
      eintraege: SCHALTBARE_APPS,
    },
    {
      titel: 'Punkte im Menü',
      hinweis:
        'Was hinter dem Menüknopf steht. Zwei Punkte bleiben: „Meine Daten“, weil dort die PIN vergeben wird, und „Darstellung“, weil hier die Schalter liegen.',
      eintraege: SCHALTBARE_MENUEPUNKTE,
    },
  ];
</script>

<PinSchloss>
  <h2>Farben</h2>
  <p class="gedaempft">
    Wirkt sofort und in jeder App - dieser Browser merkt sich die Wahl, wie bei Mikrofon und Stimme
    auch.
  </p>

  {#each FARBEN as farbe (farbe.schluessel)}
    <label class="farbe">
      <span>{farbe.name}</span>
      <div class="reihe">
        <input
          type="color"
          value={einstellungen.farben[farbe.schluessel]}
          oninput={(ereignis) => setzeFarbe(farbe.schluessel, ereignis.currentTarget.value)}
        />
        <input
          type="text"
          class="hex"
          value={einstellungen.farben[farbe.schluessel]}
          spellcheck="false"
          onchange={(ereignis) => setzeFarbe(farbe.schluessel, ereignis.currentTarget.value)}
        />
      </div>
    </label>
  {/each}

  <h2>Schriftart</h2>
  <label>
    <span>Schriftart der Oberfläche</span>
    <select
      value={einstellungen.schriftart}
      onchange={(ereignis) => setzeSchriftart(ereignis.currentTarget.value)}
    >
      {#each SCHRIFTARTEN as schriftart (schriftart.wert)}
        <option value={schriftart.wert}>{schriftart.name}</option>
      {/each}
    </select>
  </label>

  <h2>Schriftgröße</h2>
  <label>
    <span>Grundschriftgröße der Oberfläche - {einstellungen.grundschriftPx} px</span>
    <input
      type="range"
      class="schieber"
      min={GRUNDSCHRIFT_SPANNE.min}
      max={GRUNDSCHRIFT_SPANNE.max}
      step={GRUNDSCHRIFT_SPANNE.schritt}
      value={einstellungen.grundschriftPx}
      oninput={(ereignis) => setzeGrundschrift(Number(ereignis.currentTarget.value))}
    />
  </label>
  <p class="gedaempft">Betrifft Knöpfe, Beschriftungen und Fließtext - alles außer der Vorlage unten.</p>

  <label>
    <span>Schriftgröße der Vorlage - {einstellungen.schriftRem.toFixed(1)} rem</span>
    <input
      type="range"
      class="schieber"
      min={SCHRIFT_SPANNE.min}
      max={SCHRIFT_SPANNE.max}
      step={SCHRIFT_SPANNE.schritt}
      value={einstellungen.schriftRem}
      oninput={(ereignis) => setzeSchrift(Number(ereignis.currentTarget.value))}
    />
  </label>
  <p class="gedaempft">
    Der Satz, der beim Sprechen und beim Diktieren groß in der Mitte steht (siehe „hören" und
    „schreiben").
  </p>

  <div class="karte">
    <PromptView vorher={null} aktuell={{ id: 'probe', text: PROBE }} nachher={null} schriftRem={einstellungen.schriftRem} />
  </div>

  <h2>Sichtbar in der Leiste</h2>
  <p class="gedaempft">
    Was nie gebraucht wird, muss auch nicht dastehen. Gilt wie Farbe und Schrift für diesen Browser
    und damit für alle Apps darin.
  </p>

  {#each ABSCHNITTE as abschnitt (abschnitt.titel)}
    <h3>{abschnitt.titel}</h3>
    <p class="gedaempft">{abschnitt.hinweis}</p>
    <ul class="schalter">
      {#each abschnitt.eintraege as eintrag (eintrag.schluessel)}
        <li>
          <!-- Beschriftung links, Schalter rechts: Der Finger findet die Reihe
               am Namen und trifft den Schalter dort, wo er in jeder Zeile
               steht. Das ganze `label` ist die Trefffläche, nicht nur das
               Kästchen. -->
          <label>
            <span class="name">{eintrag.text}</span>
            <input
              type="checkbox"
              role="switch"
              checked={einstellungen.sichtbar[eintrag.schluessel]}
              disabled={eintrag.fest}
              title={eintrag.grund ?? (einstellungen.sichtbar[eintrag.schluessel] ? 'Wird angezeigt' : 'Ist ausgeblendet')}
              onchange={(ereignis) => setzeSichtbar(eintrag.schluessel, ereignis.currentTarget.checked)}
            />
          </label>
          {#if eintrag.grund}
            <p class="grund">{eintrag.grund}</p>
          {/if}
        </li>
      {/each}
    </ul>
  {/each}

  <h2>Zurücksetzen</h2>
  <p class="gedaempft">
    Setzt Farben, Schriftart, Schriftgrößen und die Sichtbarkeit auf die Vorgaben zurück - danach
    steht jeder Punkt wieder in der Leiste.
  </p>
  <button class="knopf" onclick={setzeDarstellungZurueck}>Auf Vorgaben zurücksetzen</button>
</PinSchloss>

<style>
  /* Eine Zeile je Punkt: Name links, Schalter rechts, Trennlinie dazwischen.
     Eine Liste und keine Folge von `label`-Zeilen, weil es eine Liste ist -
     die Vorlesestimme sagt dann auch, wie lang sie ist. */
  .schalter {
    list-style: none;
    margin: 0 0 1rem;
    padding: 0;
    border: 1px solid var(--rand);
    border-radius: 0.5rem;
    background: #fff;
  }

  .schalter li + li {
    border-top: 1px solid var(--rand);
  }

  .schalter label {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin: 0;
    padding: 0.7rem 0.9rem;
    cursor: pointer;
  }

  .schalter label:has(input:disabled) {
    cursor: default;
  }

  /* Das Stylesheet macht `label > span` klein und grau - hier ist es der
     Name der Zeile und damit die Hauptsache. */
  .schalter .name {
    display: block;
    margin: 0;
    font-size: 1rem;
    color: var(--text);
  }

  .schalter .grund {
    margin: -0.4rem 0 0;
    padding: 0 0.9rem 0.7rem;
    font-size: 0.8rem;
    color: var(--gedaempft);
  }

  /* Der Schalter selbst: ein Kästchen ohne Kästchen. `appearance: none` nimmt
     ihm das Aussehen des Systems, der Rest zeichnet Bahn und Knauf. Es bleibt
     eine echte Ankreuzfläche - Tastatur, Vorlesestimme und `role="switch"`
     tun damit weiterhin das Richtige. */
  .schalter input[type='checkbox'] {
    appearance: none;
    position: relative;
    flex: none;
    width: 2.7rem;
    height: 1.5rem;
    min-width: 0;
    margin: 0;
    padding: 0;
    border: 1px solid var(--rand);
    border-radius: 999px;
    background: var(--hintergrund);
    cursor: inherit;
    transition:
      background 0.15s,
      border-color 0.15s;
  }

  .schalter input[type='checkbox']::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 0.15rem;
    width: 1.1rem;
    height: 1.1rem;
    border-radius: 50%;
    background: var(--gedaempft);
    transform: translateY(-50%);
    transition:
      transform 0.15s,
      background 0.15s;
  }

  .schalter input[type='checkbox']:checked {
    background: var(--akzent);
    border-color: var(--akzent);
  }

  .schalter input[type='checkbox']:checked::after {
    background: #fff;
    transform: translate(1.15rem, -50%);
  }

  .schalter input[type='checkbox']:disabled {
    opacity: 0.5;
  }

  .schalter input[type='checkbox']:focus-visible {
    outline: 2px solid var(--akzent);
    outline-offset: 2px;
  }

  h3 {
    font-size: 1rem;
    margin: 1.25rem 0 0.4rem;
  }

  h3 + .gedaempft {
    margin-top: 0;
  }

  .schieber {
    border: 0;
    padding: 0;
    max-width: 20rem;
  }

  /* Farbfeld und Hex-Eingabe nebeneinander, nicht als eigene `label`-Zeile:
     Beides steuert denselben Wert, nur das eine per Auge, das andere für den,
     der den Code schon kennt. */
  .farbe .reihe {
    align-items: center;
  }

  input[type='color'] {
    width: 3rem;
    padding: 0.15rem;
  }

  .hex {
    max-width: 8rem;
    font-family: monospace;
  }
</style>
