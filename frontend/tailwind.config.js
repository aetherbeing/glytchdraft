/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        glytch: {
          pink: '#ff6b9d',
          blue: '#4ecdc4',
          purple: '#a8e6cf',
          dark: '#1a1a2e'
        }
      },
      fontFamily: {
        'glytch': ['Space Mono', 'monospace'],
      }
    },
  },
  plugins: [],
}
