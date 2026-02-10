import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Space Grotesk", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        ink: "#eaf0ff",
        muted: "#98a3b8",
        accent: "#6cf6c6",
        accent2: "#5fa3ff",
        panel: "rgba(15, 24, 36, 0.85)",
        panelBorder: "rgba(112, 130, 155, 0.35)",
      },
      boxShadow: {
        panel: "0 20px 60px rgba(0, 0, 0, 0.45)",
      },
    },
  },
  plugins: [],
} satisfies Config;
