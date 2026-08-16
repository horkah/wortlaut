import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

// `vitePreprocess` übersetzt `<script lang="ts">` in den Komponenten.
// Mehr braucht es nicht: kein SvelteKit, keine weiteren Präprozessoren.
export default { preprocess: vitePreprocess() };
