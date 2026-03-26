/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        severity: {
          low: "#22c55e",
          medium: "#f59e0b",
          high: "#ef4444",
          critical: "#7f1d1d",
        },
      },
    },
  },
  plugins: [],
};
