import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = [
  ...nextVitals,
  ...nextTypescript,
  {
    ignores: [".next/**", "coverage/**", "next-env.d.ts"],
    rules: {
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/immutability": "off"
    }
  }
];

export default config;
