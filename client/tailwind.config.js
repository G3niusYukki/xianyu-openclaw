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
          500: 'var(--xy-brand-500)',
          600: 'var(--xy-brand-600)',
        },
        'xy-text': {
          primary: 'var(--xy-text-primary)',
          secondary: 'var(--xy-text-secondary)',
          muted: 'var(--xy-text-muted)',
        },
        'xy-surface': 'var(--xy-surface)',
        'xy-bg': 'var(--xy-bg)',
      },
      borderRadius: {
        'xy-sm': 'var(--xy-radius-sm)',
        'xy-md': 'var(--xy-radius-md)',
        'xy-lg': 'var(--xy-radius-lg)',
      }
    },
  },
  plugins: [
    // 简单引入 forms 插件，方便表单重置，如果没有安装可以注释掉。
    // require('@tailwindcss/forms'),
  ],
}
