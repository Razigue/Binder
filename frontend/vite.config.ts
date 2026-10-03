import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// Phosphor ships six drawings per icon; the interface only draws these (regular, with bold, fill
// and light accents). Add a weight here before using it, or its icons render empty.
const ICON_WEIGHTS = ['regular', 'bold', 'fill', 'light']

/** Drops the unused weights from each Phosphor icon: about a third of the icon code. */
function phosphorWeights(keep: string[]): Plugin {
  // One `["weight", <svg>]` entry per weight, as formatted in `dist/defs/*.es.js`.
  const entry = /\n {2}\[\n {4}"(\w+)",[\s\S]*?\n {2}\],?/g
  return {
    name: 'phosphor-weights',
    apply: 'build',
    transform: {
      filter: { id: /@phosphor-icons[\\/]react[\\/]dist[\\/]defs[\\/]/ },
      handler(code) {
        const kept = code.replace(entry, (match, weight: string) => (keep.includes(weight) ? match : ''))
        return { code: kept, map: null }
      },
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), phosphorWeights(ICON_WEIGHTS)],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  server: { proxy: { '/api': 'http://127.0.0.1:8765' } },
  // The built interface is served by FastAPI.
  build: { outDir: '../backend/src/binder/static', emptyOutDir: true },
})
