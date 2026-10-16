/**
 * Design tokens — the single source of truth for colour, type, space, radius, elevation and
 * motion. See DESIGN.md for the rationale and the job of each token. tailwind.config.ts is
 * generated from this file; `features/**` never imports Tailwind classes that encode a raw
 * colour.
 */

export const color = {
  brand: {
    DEFAULT: "#EC0000",
    hover: "#D00000",
    pressed: "#B40000",
    soft: "#FBE4E4",
  },
  support: "#005CB9",
  ink: {
    900: "#111318",
    700: "#282828",
    500: "#454C52",
    400: "#66707A",
  },
  surface: {
    100: "#FFFFFF",
    200: "#F5F7FA",
    300: "#E1E6EB",
  },
  state: {
    success: "#117A2B",
    warning: "#B45309",
    danger: "#B40000",
  },
} as const;

export const typography = {
  fontFamily: {
    sans: [
      "Inter",
      "ui-sans-serif",
      "system-ui",
      "-apple-system",
      "Segoe UI",
      "Roboto",
      "Helvetica Neue",
      "Arial",
      "sans-serif",
    ],
  },
  // size → [fontSize, { lineHeight, letterSpacing?, fontWeight? }]
  fontSize: {
    display: ["28px", { lineHeight: "36px", fontWeight: "700" }],
    heading: ["20px", { lineHeight: "28px", fontWeight: "600" }],
    body: ["15px", { lineHeight: "24px", fontWeight: "400" }],
    label: ["13px", { lineHeight: "20px", fontWeight: "500", letterSpacing: "0.005em" }],
  },
} as const;

export const space = {
  "1": "4px",
  "2": "8px",
  "3": "12px",
  "4": "16px",
  "6": "24px",
  "8": "32px",
  "10": "40px",
  "12": "48px",
  "16": "64px",
} as const;

export const radius = {
  sm: "4px",
  md: "8px",
  lg: "12px",
} as const;

export const shadow = {
  "1": "0 1px 2px rgba(17, 19, 24, 0.08)",
  "2": "0 8px 24px rgba(17, 19, 24, 0.12)",
} as const;

export const motion = {
  duration: {
    fast: "120ms",
    slow: "220ms",
  },
  ease: {
    standard: "cubic-bezier(0.2, 0, 0, 1)",
  },
} as const;
