import { expect, test } from "@playwright/test";

// T100 — Visual regression: captura cada tela pública em desktop e mobile.
// A suíte é opt-in (CI_VISUAL=1) porque os baselines PNG não entram no git — eles são
// específicos do sistema (fonts, rendering) e são regerados localmente antes de uma
// rebase consciente com `playwright test --update-snapshots`. CI roda esse spec apenas
// no job dedicado "web-visual" quando houver baselines commitados por imagem Docker
// determinística (fora do escopo da entrega atual).

const SHOULD_RUN = process.env.CI_VISUAL === "1";

const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 800 },
  { name: "mobile", width: 390, height: 844 },
] as const;

const PUBLIC_ROUTES = [
  { path: "/login", name: "login" },
  { path: "/register", name: "register" },
  { path: "/forgot", name: "forgot" },
] as const;

for (const vp of VIEWPORTS) {
  for (const route of PUBLIC_ROUTES) {
    test(`visual ${route.name} @ ${vp.name}`, async ({ page }) => {
      test.skip(!SHOULD_RUN, "visual regression é opt-in: defina CI_VISUAL=1");
      await page.context().clearCookies();
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(route.path);
      // Esperamos o botão primário renderizar; evita networkidle, que fica preso em
      // SPAs com polling (React Query /me, i18next lazy, etc.).
      await page.getByRole("button").first().waitFor({ state: "visible" });
      await expect(page).toHaveScreenshot(`${route.name}-${vp.name}.png`, {
        fullPage: true,
        maxDiffPixelRatio: 0.01,
      });
    });
  }
}
