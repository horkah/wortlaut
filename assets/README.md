# Zeichen und Schriftzug

## Die Quelldateien

`wortlaut_favicon_wl_kreis.svg` und `wortlaut_favicon_wl_kreis.png` sind **kein
Logo, sondern ein Kontaktbogen**: dasselbe Zeichen viermal nebeneinander, einmal
groß und dreimal in den Größen, in denen ein Favicon tatsächlich erscheint. Sie
dienen der Beurteilung („trägt die Form auch bei 16 px?"), nicht der Einbindung.
Wer eine davon direkt verlinkt, bekommt weißen Grund, drei Beschriftungen und
drei überflüssige Kopien mitgeliefert.

Aufbau der SVG-Quelle:

| | |
|---|---|
| Zeichenfläche | `viewBox="0 0 690 310"`, darin ein weißes Rechteck 680 × 300 |
| Motiv | ein einziger `<path>`, viermal wiederholt in je einer `<g>` |
| Maßstäbe | `scale(2.2)` (Schaubild), `0.64` (= 64 px), `0.32` (32 px), `0.16` (16 px) |
| Linie | `stroke-width="10"`, `linecap`/`linejoin` `round`, `fill="none"` |
| Beschriftung | drei `<text>`-Elemente „64 px / 32 px / 16 px" |

Die PNG-Fassung ist dieselbe Zeichnung in 2760 × 1240 px, also **Faktor 4** zu den
Nutzerkoordinaten der SVG. Das große Zeichen sitzt dort bei `translate(40,40)`.

Die Form selbst ist eine durchgehende Linie: das W, dessen rechter Flügel in eine
Kreisbahn einschwingt, rechts herum und unten entlanglaufend, und als senkrechter
Stamm des L endet.

## Der Ausschnitt

Alle abgeleiteten Dateien zeigen dasselbe Quadrat. Der Pfad hat in seinen
eigenen Koordinaten diese Ausdehnung (Linienbreite eingerechnet, also ±5):

```
x 10,5 … 89,49      y 6,5 … 93,48      Mitte (49,99 | 49,99)
```

Er ist damit von sich aus auf (50 | 50) zentriert, und `viewBox="0 0 100 100"`
ist der richtige Beschnitt — ohne jede Verschiebung. Der Rand beträgt links und
rechts 10,5 %, oben und unten 6,5 %.

## Die abgeleiteten Dateien

| Datei | Farbe | Wofür |
|---|---|---|
| `wortlaut-logo.svg` | `currentColor` | in der App, in `packages/ui/Kopfleiste.svelte` als Quelltext eingebunden (`?raw` + `{@html}`), damit es die Textfarbe annimmt |
| `wortlaut-logo-invers.svg` | `#faf9f7` | die dunkle Fassung der README, über `<picture>` und `prefers-color-scheme` |
| `wortlaut-favicon.svg` | schwarz, im dunklen Systemdesign weiß | der Browser-Tab |

`wortlaut-logo.svg` in ein `<img>` zu hängen geht schief: `currentColor` findet
dort keine Umgebung und bleibt schwarz. Für `<img>` sind die beiden anderen da.

Zwei Kopien liegen bewusst außerhalb dieses Ordners, weil Vite nur seinen eigenen
`public/`-Ordner unter `/` ausliefert:

```
apps/hoeren/frontend/public/favicon.svg           Kopie von wortlaut-favicon.svg
apps/hoeren/frontend/public/apple-touch-icon.png  180 × 180, weißer Grund
```

Das PNG braucht es, weil iOS beim Ablegen auf dem Startbildschirm kein SVG
annimmt und keine Transparenz mag. Es ist aus der PNG-Quelle geschnitten,
Bildausschnitt 160 … 1040 px in beiden Achsen — dasselbe Quadrat wie oben.

## Wenn sich das Zeichen ändert

Neue Quelldatei hierher legen, dann in den drei abgeleiteten SVG das `d`-Attribut
ersetzen und den Beschnitt nachrechnen (Pfad abtasten, Mitte prüfen). Danach
`wortlaut-favicon.svg` nach `public/` kopieren und das Apple-Icon neu schneiden.
