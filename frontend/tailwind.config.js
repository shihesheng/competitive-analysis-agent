/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          950: "#070b14",
          900: "#0d1320",
          850: "#111827",
          800: "#172033",
        },
      },
    },
  },
  plugins: [],
};
