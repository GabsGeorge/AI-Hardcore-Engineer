import { expect, test } from "@playwright/test";

test.describe("US4 — RBAC guarda rotas por sessão e papel", () => {
  test("sem sessão, /history redireciona para /login com next preservado", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/history");
    await page.waitForURL(/\/login\?next=/);
    expect(page.url()).toContain("next=%2Fhistory");
  });

  test("sem sessão, /queue redireciona para /login", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/queue");
    await page.waitForURL(/\/login/);
  });

  test("sem sessão, /admin redireciona para /login", async ({ page }) => {
    await page.context().clearCookies();
    await page.goto("/admin");
    await page.waitForURL(/\/login/);
  });
});
