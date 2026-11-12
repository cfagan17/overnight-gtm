/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'], mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'] },
      colors: {
        // The scale keeps its old names so class names did not have to change. It now runs light:
        // 950 and 800 are surfaces, 900 is the page, 850 to 700 are fills, 600 and 500 are lines.
        night: { 950: '#ffffff', 900: '#f7f7f8', 850: '#f3f3f5', 800: '#ffffff', 750: '#f3f3f5', 700: '#e8e8ec', 600: '#dcdce1', 500: '#a1a1aa' },
        ink: { DEFAULT: '#18181b', muted: '#52525b', faint: '#71717a' },
        ledger: '#0f766e', control: '#047857', prim: '#1d4ed8', loop: '#b45309', people: '#be185d',
      },
    },
  },
  plugins: [],
};
