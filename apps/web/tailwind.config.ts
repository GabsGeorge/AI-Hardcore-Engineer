/**
 * Generated shape — the single source of truth is `src/design/tokens.ts`. Keep the mapping
 * below in sync when adding a token, and read DESIGN.md first.
 */

import type { Config } from "tailwindcss";
import { color, motion, radius, shadow, space, typography } from "./src/design/tokens";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    // Replace Tailwind's defaults rather than extend, so a raw `text-red-500` cannot slip in.
    colors: {
      transparent: "transparent",
      current: "currentColor",
      inherit: "inherit",
      brand: color.brand,
      support: color.support,
      ink: color.ink,
      surface: color.surface,
      state: color.state,
      // Reusable aliases to keep classnames readable (e.g. bg-page, text-body).
      page: color.surface[100],
      card: color.surface[200],
      line: color.surface[300],
    },
    fontFamily: typography.fontFamily,
    fontSize: typography.fontSize,
    borderRadius: {
      none: "0",
      ...radius,
      full: "9999px",
    },
    boxShadow: {
      none: "none",
      "1": shadow[1],
      "2": shadow[2],
    },
    spacing: {
      px: "1px",
      "0": "0px",
      ...space,
    },
    extend: {
      transitionDuration: {
        fast: motion.duration.fast,
        slow: motion.duration.slow,
      },
      transitionTimingFunction: {
        standard: motion.ease.standard,
      },
    },
  },
} satisfies Config;
