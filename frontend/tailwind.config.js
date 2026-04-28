/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#f0f4fb',
          100: '#e0e9f7',
          500: '#2e75b6',
          700: '#1b3a6b',
          900: '#0f2040',
        },
      },
    },
  },
  plugins: [],
}
