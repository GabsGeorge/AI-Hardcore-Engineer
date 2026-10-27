import { expect, test } from "@playwright/test";

test.describe("US6 — Admin sem sessão fica fora de /admin/*", () => {
  const paths = ["/admin", "/admin/accounts", "/admin/merchants", "/admin/queue", "/admin/audit"];
  for (const path of paths) {
    test(`sem sessão, ${path} redireciona para /login`, async ({ page }) => {
      await page.context().clearCookies();
      await page.goto(path);
      await page.waitForURL(/\/login/);
    });
  }

  test("convite inválido mostra erro específico", async ({ page }) => {
    await page.goto("/invite?token=nao-existe-123456");
    await page.getByLabel(/nome|name/i).fill("Convidado");
    await page.getByLabel(/nova senha|new password/i).fill("senha-forte-123456");
    await page.getByRole("button", { name: /ativar|activate/i }).click();
    await expect(page.getByRole("alert")).toBeVisible();
  });
});
