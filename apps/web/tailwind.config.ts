import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: {
          DEFAULT: "#b3312c", // restrained red accent
          dark: "#8f2723",
        },
      },
    },
  },
  plugins: [],
};

export default config;
