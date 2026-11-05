/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'], mono: ['JetBrains Mono', 'ui-monospace', 'monospace'] },
      colors: {
        night: { 950: '#070b17', 900: '#0b1020', 850: '#0f1528', 800: '#141b2e', 750: '#18203a', 700: '#1e2846', 600: '#2a3550', 500: '#3a4766' },
        ink: { DEFAULT: '#eef2fa', muted: '#93a0bb', faint: '#5d6985' },
        ledger: '#60a5fa', control: '#34d399', prim: '#a78bfa', loop: '#fbbf24', people: '#f472b6',
      },
      boxShadow: { glow: '0 0 0 1px rgba(167,139,250,.35), 0 8px 40px -12px rgba(167,139,250,.45)' },
    },
  },
  plugins: [],
};
