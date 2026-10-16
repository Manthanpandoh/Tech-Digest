/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#050816",
        card: "#111827",
        neonPink: "#FF2E88",
        neonPurple: "#A855F7",
        neonCyan: "#22D3EE",
      },
    },
  },
  plugins: [],
};