import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { clearInbox, waitForLink } from "./mailpit";

const EMAIL = `demo+${Date.now()}@example.com`;
const PASSWORD = "senha-segura-demo-test";

test.describe("US1 — Cadastro, login e saída", () => {
  test.beforeAll(async () => {
    await clearInbox();
  });

  test("fluxo completo ponta a ponta", async ({ page, baseURL }) => {
    // 1. Autocadastro
    await page.goto("/register");
    await expect(page.getByRole("heading", { name: /criar conta/i })).toBeVisible();
    await page.getByLabel(/^nome/i).fill("Loja Demo");
    await page.getByLabel(/^e-mail/i).fill(EMAIL);
    await page.getByLabel(/^senha/i).fill(PASSWORD);
    await page.getByRole("button", { name: /criar conta/i }).click();
    await expect(page.getByRole("heading", { name: /verifique/i })).toBeVisible();

    // 2. Pega o link no Mailpit e confirma
    const link = await waitForLink(EMAIL, /http[s]?:\/\/[^\s"'<>]+\/verify\?token=[^\s"'<>]+/);
    const relative = link.replace(baseURL ?? "", "");
    await page.goto(relative);
    await expect(page.getByText(/confirmado/i)).toBeVisible();

    // 3. Login com as credenciais
    await page.goto("/login");
    await page.getByLabel(/^e-mail/i).fill(EMAIL);
    await page.getByLabel(/^senha/i).fill(PASSWORD);
    await page.getByRole("button", { name: /^entrar$/i }).click();
    await page.waitForURL(/\/chat/);

    // 4. Sair encerra a sessão e barrar o acesso de volta
    await page.getByRole("button", { name: /sair/i }).click();
    await page.waitForURL(/\/login/);
    await page.goto("/chat");
    await page.waitForURL(/\/login/);
  });

  test("tela de login não tem violações de a11y críticas", async ({ page }) => {
    await page.goto("/login");
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    const critical = results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(critical).toEqual([]);
  });
});
