import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      boxShadow: {
        soft: "0 20px 70px rgba(0, 0, 0, 0.34)"
      }
    }
  },
  plugins: []
};

export default config;
