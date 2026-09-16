<script lang="ts">
  /**
   * Farben, Schriftart und Schriftgrößen - eine eigene Ansicht neben
   * `Audio.svelte`.
   *
   * Warum getrennt: siehe `DARSTELLUNG_PFAD` in `apps.ts`. Die Werte selbst,
   * ihre Vorgaben und wie sie auf die App wirken, stehen in
   * `einstellungen.svelte.ts`; hier steht nur die Bedienung dazu.
   */
  import PinSchloss from './PinSchloss.svelte';
  import PromptView from './PromptView.svelte';
  import {
    APPS,
    SCHALTBARE_APPS,
    SCHALTBARE_MENUEPUNKTE,
    SCHALTBARE_REITER,
    type Schaltbar,
  } from './apps';
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

  // Die Abschnitte folgen dem Aufbau der Kopfleiste: oben die Apps, darunter
  // je App ihre Ansichten, zuletzt die Punkte hinter dem Menüknopf.
  function appName(schluessel: string): string {
    return APPS.find((eintrag) => eintrag.schluessel === schluessel)?.name ?? schluessel;
  }

  const ABSCHNITTE: { titel: string; hinweis: string; eintraege: Schaltbar[] }[] = [
    {
      titel: 'Apps in der Kopfleiste',
      hinweis:
        'Die Reiter ganz oben. Ausgeblendet ist eine App nur aus der Leiste verschwunden, nicht abgeschaltet - ihre Adresse gilt weiter.',
      eintraege: SCHALTBARE_APPS,
    },
    ...SCHALTBARE_REITER.map((abschnitt) => ({
      titel: `Ansichten in „${appName(abschnitt.app)}“`,
      hinweis:
        'Die zweite Reihe der Kopfleiste. Auch hier gilt: ausgeblendet heißt unsichtbar, nicht abgeschaltet - wer einen Reiter wieder braucht, holt ihn hier zurück.',
      eintraege: abschnitt.eintraege,
    })),
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
    auch. Auf das Feld tippen öffnet die Farbwahl des Geräts; der Wert darunter lässt sich
    überschreiben, wenn ein Ton genau getroffen werden muss.
  </p>

  <div class="farben">
    {#each FARBEN as farbe (farbe.schluessel)}
      {@const wert = einstellungen.farben[farbe.schluessel]}
      {@const eigen = wert !== farbe.vorgabe}
      <div class="farbe">
        <!-- Das Farbfeld ist der Hauptweg und deshalb die größte Fläche: ein
             Tippen, dann wählt das Gerät. Der Hex-Wert daneben ist der zweite
             Weg für dieselbe Sache, nicht der erste - er sieht aus wie Text
             und wird erst zum Feld, wenn jemand ihn anfasst. -->
        <input
          type="color"
          class="tupfer"
          id="farbe-{farbe.schluessel}"
          value={wert}
          oninput={(ereignis) => setzeFarbe(farbe.schluessel, ereignis.currentTarget.value)}
        />
        <div class="beschriftung">
          <label class="name" for="farbe-{farbe.schluessel}">{farbe.name}</label>
          <input
            type="text"
            class="hex"
            value={wert}
            spellcheck="false"
            autocapitalize="off"
            autocomplete="off"
            maxlength="7"
            title="Hex-Wert, überschreibbar - auch als „1b4d3e“ oder „#abc“"
            aria-label="{farbe.name} als Hex-Wert"
            onfocus={(ereignis) => ereignis.currentTarget.select()}
            onchange={(ereignis) => {
              // Steht dort Unsinn, kommt der geltende Wert zurück ins Feld:
              // Ein Eingabefeld, das eine verworfene Eingabe stehen lässt,
              // behauptet eine Farbe, die nirgends gilt.
              if (!setzeFarbe(farbe.schluessel, ereignis.currentTarget.value))
                ereignis.currentTarget.value = wert;
            }}
          />
        </div>
        <!-- Feste Spalte, auch wenn nichts darin steht: Sonst rückte die
             ganze Zeile beim ersten Farbwechsel zur Seite. -->
        <div class="einzeln">
          {#if eigen}
            <button
              class="zurueck"
              title="„{farbe.name}“ auf die Vorgabe {farbe.vorgabe} zurücksetzen"
              aria-label="„{farbe.name}“ auf die Vorgabe zurücksetzen"
              onclick={() => setzeFarbe(farbe.schluessel, farbe.vorgabe)}
            >
              <!-- Ein Pfeil als Zeichnung und nicht als Schriftzeichen: Nicht
                   jede Schriftart der Oberfläche hat eines dafür, und die
                   Schriftart ist hier gerade einstellbar. -->
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <polyline points="1 4 1 10 7 10" />
                <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
              </svg>
            </button>
          {/if}
        </div>
      </div>
    {/each}
  </div>

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

  /* Wie der Schalter aussieht, steht im gemeinsamen Stylesheet an
     `[role='switch']` - er steht inzwischen auch in der Auswertung. Hier
     bleibt nur, wie die Zeile ihn aufstellt. */

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

  /* Acht Farben als Raster statt als acht Blöcke untereinander.
     Vorher hatte jede Farbe eine eigene Beschriftungszeile, ein Farbfeld und
     ein breites Textfeld - drei Zeilen Höhe für einen Wert, und die ganze
     Seite scrollte an den Schriftgrößen vorbei, die eigentlich der Anlass
     sind, hier zu sein. Jetzt steht eine Farbe in einer Zeile, und die Spalten
     richten sich nach dem Platz: zwei nebeneinander, wenn er reicht, eine auf
     dem Telefon. */
  .farben {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
    gap: 0.4rem;
    margin-bottom: 1rem;
  }

  .farbe {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.4rem 0.5rem;
    border: 1px solid var(--rand);
    border-radius: 0.5rem;
    background: #fff;
  }

  .farbe:focus-within {
    border-color: var(--akzent);
  }

  /* Das Farbfeld selbst, ohne den Rahmen, den das System sonst darum zeichnet:
     Was hier zählt, ist die Farbe, nicht das Kästchen. Die Auszeichnungen für
     die beiden Browserfamilien stehen nebeneinander, weil keine die andere
     versteht. */
  .tupfer {
    appearance: none;
    flex: none;
    width: 2.4rem;
    height: 2.4rem;
    min-width: 0;
    padding: 0;
    border: 1px solid var(--rand);
    border-radius: 0.4rem;
    /* Sichtbar nur, falls ein Browser die Fläche darunter nicht zeichnet -
       dann steht hier ein leeres Feld und kein Loch in der Zeile. */
    background: var(--hintergrund);
    cursor: pointer;
  }

  .tupfer::-webkit-color-swatch-wrapper {
    padding: 0;
  }

  .tupfer::-webkit-color-swatch {
    border: 0;
    border-radius: 0.3rem;
  }

  .tupfer::-moz-color-swatch {
    border: 0;
    border-radius: 0.3rem;
  }

  .beschriftung {
    /* Ohne `min-width: 0` gibt ein Flex-Element seine Breite nicht her, und
       ein langer Name („Akzentfarbe, hell") drückte die Zeile auseinander. */
    min-width: 0;
    flex: 1;
  }

  /* Das Stylesheet macht jedes `label` zu einem Block mit Abstand darunter -
     hier sind Name und Wert zwei Zeilen einer einzigen Angabe. */
  .farbe .name {
    display: block;
    margin: 0;
    font-size: 0.9rem;
    line-height: 1.2;
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Sieht aus wie Text und ist doch ein Feld: Die meisten wählen ihre Farbe
     nebenan mit dem Auge, und ein zweites umrandetes Eingabefeld je Zeile
     sähe nach doppelter Arbeit aus. Wer den Wert genau kennt, findet es
     trotzdem - beim Überfahren tritt der Rahmen hervor. */
  .hex {
    width: 100%;
    max-width: 7rem;
    padding: 0;
    border: 0;
    border-radius: 0.25rem;
    background: none;
    font-family: ui-monospace, 'SFMono-Regular', 'Courier New', monospace;
    font-size: 0.8rem;
    line-height: 1.3;
    color: var(--gedaempft);
    cursor: text;
  }

  .hex:hover {
    color: var(--text);
  }

  .hex:focus {
    color: var(--text);
    outline: 2px solid var(--akzent);
    outline-offset: 1px;
  }

  /* Die Spalte bleibt, auch wenn der Knopf fehlt. */
  .einzeln {
    flex: none;
    width: 1.6rem;
    display: flex;
    justify-content: flex-end;
  }

  /* Nur da, wenn diese eine Farbe von der Vorgabe abweicht - der gezielte
     Rückweg neben dem groben weiter unten, der alles auf einmal zurückholt. */
  .zurueck {
    display: block;
    padding: 0.2rem;
    border: 0;
    border-radius: 0.3rem;
    background: none;
    color: var(--gedaempft);
    cursor: pointer;
    line-height: 0;
  }

  .zurueck:hover {
    background: var(--akzent-hell);
    color: var(--akzent);
  }

  .zurueck svg {
    width: 1rem;
    height: 1rem;
    fill: none;
    stroke: currentColor;
    stroke-width: 2.5;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
</style>
