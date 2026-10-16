import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "@/i18n/en.json";
import pt from "@/i18n/pt.json";

const STORAGE_KEY = "getnet.lang";
export type Language = "pt" | "en";

export function detectLanguage(): Language {
  if (typeof window !== "undefined") {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "pt" || stored === "en") {
      return stored;
    }
  }
  if (typeof navigator !== "undefined" && navigator.language.toLowerCase().startsWith("en")) {
    return "en";
  }
  return "pt";
}

export async function initI18n(): Promise<void> {
  if (i18n.isInitialized) {
    return;
  }
  await i18n.use(initReactI18next).init({
    resources: { pt: { translation: pt }, en: { translation: en } },
    lng: detectLanguage(),
    fallbackLng: "pt",
    interpolation: { escapeValue: false },
    returnNull: false,
  });
}

export function setLanguage(lang: Language): void {
  void i18n.changeLanguage(lang);
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, lang);
    window.document.documentElement.lang = lang;
  }
}
