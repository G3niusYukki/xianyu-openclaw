/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'xy-brand': {
          50: 'var(--xy-brand-50)',
          100: 'var(--xy-brand-100)',
          200: 'var(--xy-brand-200)',
          300: 'var(--xy-brand-300)',
          400: 'var(--xy-brand-400)',
          500: 'var(--xy-brand-500)',
          600: 'var(--xy-brand-600)',
          700: 'var(--xy-brand-700)',
        },
        'xy-gray': {
          50: 'var(--xy-gray-50)',
          100: 'var(--xy-gray-100)',
          200: 'var(--xy-gray-200)',
          300: 'var(--xy-gray-300)',
          400: 'var(--xy-gray-400)',
          500: 'var(--xy-gray-500)',
          600: 'var(--xy-gray-600)',
          700: 'var(--xy-gray-700)',
          800: 'var(--xy-gray-800)',
          900: 'var(--xy-gray-900)',
        },
        'xy-text': {
          primary: 'var(--xy-text-primary)',
          secondary: 'var(--xy-text-secondary)',
          muted: 'var(--xy-text-muted)',
        },
        'xy-surface': 'var(--xy-surface)',
        'xy-bg': 'var(--xy-bg)',
        'xy-border': 'var(--xy-border)',
        'xy-success': 'var(--xy-success)',
        'xy-warning': 'var(--xy-warning)',
        'xy-error': 'var(--xy-error)',
        'xy-info': 'var(--xy-info)',
      },
      borderRadius: {
        'xy-sm': 'var(--xy-radius-sm)',
        'xy-md': 'var(--xy-radius-md)',
        'xy-lg': 'var(--xy-radius-lg)',
      }
    },
  },
  plugins: [],
}
