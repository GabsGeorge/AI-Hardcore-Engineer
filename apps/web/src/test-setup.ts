import "@testing-library/jest-dom/vitest";
import { initI18n } from "@/lib/i18n";

// jsdom não implementa scrollIntoView; componentes que o usam (ChatPage) quebram sem stub.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// Load i18n once per suite so Vitest components can read `t("...")` without async setup.
await initI18n();
