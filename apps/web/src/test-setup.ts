import "@testing-library/jest-dom/vitest";
import { initI18n } from "@/lib/i18n";

// Load i18n once per suite so Vitest components can read `t("...")` without async setup.
await initI18n();
