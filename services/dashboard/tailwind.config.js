/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#0a0e14",
          panel: "#121821",
          elevated: "#1a2230",
        },
        accent: {
          DEFAULT: "#38bdf8",
          green: "#34d399",
          amber: "#fbbf24",
          red: "#f87171",
          purple: "#a78bfa",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
