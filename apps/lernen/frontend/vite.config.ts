import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

const hier = dirname(fileURLToPath(import.meta.url));
const repowurzel = resolve(hier, '../../..');

// Das Baudatum wandert als fester Wert ins Bündel (siehe packages/ui/bau.ts);
// der Seitenfuß zeigt es an. In der Entwicklung ist es der Serverstart.
const baudatum = new Date().toISOString();

export default defineConfig({
  plugins: [svelte()],
  define: { __BAUDATUM__: JSON.stringify(baudatum) },
  // Diese App liegt unter der gemeinsamen Domain auf `/lernen/` (siehe `BASIS`
  // in backend/main.py und packages/ui/apps.ts). Ohne `base` verwiese das
  // gebaute HTML auf `/assets/…` und träfe damit die App „hören" auf der Wurzel.
  base: '/lernen/',
  resolve: {
    // Geteilte Komponenten liegen außerhalb dieser App.
    alias: { $ui: resolve(repowurzel, 'packages/ui') },
  },
  server: {
    // Eigener Port, damit „hören" (5173) und „schreiben" (5174) daneben laufen.
    port: 5175,
    // Ohne diese Freigabe verweigert Vite Dateien oberhalb des Projektordners.
    fs: { allow: [repowurzel] },
    // Statt CORS: der Entwicklungsserver reicht die API an das Backend durch.
    // Der Pfad bleibt dabei unverändert - das Backend hängt seine Wege selbst
    // unter `/lernen` (siehe `BASIS` dort). Port 8002, damit alle drei
    // Backends gleichzeitig laufen können (Makefile).
    proxy: {
      '/lernen/api': 'http://localhost:8002',
      // Die Modellübersicht zeigt oben, was „schreiben" gerade geladen hat -
      // das gehört jener App, und eine zweite Wahrheit darüber wäre eine zu
      // viel (siehe `lib/api.ts`).
      '/schreiben/api': 'http://localhost:8001',
      // Die PIN und die Zugangsprüfung stehen im Korpus, und den führt allein
      // „hören" - auch die Ansichten dieser App fragen dessen API. Im Betrieb
      // verteilt das der Reverse Proxy, hier diese Zeile.
      '/api': 'http://localhost:8000',
    },
  },
});
