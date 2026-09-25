<script lang="ts">
  /**
   * Was dasteht, wenn dieser Browser niemanden vorweisen kann - dieselbe
   * Ansicht in jeder App.
   *
   * Ohne Zugang gibt keine der drei APIs etwas her: kein Korpus, kein Modell,
   * keine Sitzung (siehe jeweils `backend/deps.py`). Eine Ansicht, die es
   * trotzdem versucht, ist eine Wand aus abgewiesenen Anfragen - also steht
   * hier der eine Schritt, der weiterführt.
   *
   * Sie steht hier und nicht dreimal in drei Apps, weil es dreimal dieselbe
   * Lage ist: Der Zugang liegt einmal im Browser und gilt überall (siehe
   * `zugang.ts`), und wer ihn nicht hat, hat ihn in allen dreien nicht. Es
   * standen einmal drei verschieden formulierte Karten dafür da, die dasselbe
   * sagten - drei Gelegenheiten, es verschieden zu sagen, und drei Stellen zum
   * Ändern, von denen man zwei vergisst.
   *
   * Der persönliche Link ist der übliche Weg und verlangt niemandem etwas zu
   * tippen ab. Das Feld unter „Zugangsdaten" ist der Ausweg für den, der einen
   * Zugang von Hand einsetzt - und zugleich der einzige Weg in Verwaltung und
   * Aufsicht, aus jeder App (`Zugangsdaten.svelte`).
   *
   * Eingehängt wird sie vom Rahmen (`Rahmen.svelte`), nicht von den Apps.
   */
  import { ZUGANGSDATEN_PFAD } from './apps';
  import { gehZu } from './route';
</script>

<h2>Kein Zugang</h2>

<div class="karte">
  <p>
    Dieser Browser gehört noch zu niemandem. Was hier geschieht, gehört einem Menschen: Es läuft
    auf seinem Modell und geht in seinen Korpus.
  </p>
  <p>
    Der persönliche Link, einmal geöffnet, genügt - derselbe in allen drei Apps. Danach ist hier
    nichts mehr einzutragen.
  </p>
  <p>Wer verwaltet oder beaufsichtigt, trägt stattdessen seinen Token ein - in dasselbe Feld.</p>
  <button class="knopf haupt" onclick={() => gehZu(ZUGANGSDATEN_PFAD)}>Zu den Zugangsdaten</button>
  <p class="gedaempft">
    Dieselbe Seite steht immer im Menü (☰) rechts oben. Was dort eingetragen wird, bleibt in
    diesem Browser.
  </p>
</div>
