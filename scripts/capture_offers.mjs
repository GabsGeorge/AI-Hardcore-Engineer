// Captura as taxas e ofertas de https://site.getnet.com.br/todas-as-maquininhas/ como um navegador as vê.
//
// A página monta o simulador (faixas de faturamento, parcelas, cartões das maquininhas) com
// JavaScript, então o crawler comum não recebe esse conteúdo. Este robô abre a página, clica em cada
// faixa e grava o que aparece na tela em JSON (scripts/build_curated_offers.py o converte em
// Markdown para a base de conhecimento).
//
//   node scripts/capture_offers.mjs [saida.json]
//
// Variáveis: BROWSER_PATH (msedge/chrome; padrão: Edge do Windows) e PLAYWRIGHT_CORE (padrão:
// apps/web/node_modules/playwright-core/index.mjs).
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const out = process.argv[2] ?? 'src/app/rag/curated/todas-as-maquininhas.capture.json';
const browserPath =
  process.env.BROWSER_PATH ?? 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const corePath = path.resolve(
  process.env.PLAYWRIGHT_CORE ?? 'apps/web/node_modules/playwright-core/index.mjs',
);
const URL = 'https://site.getnet.com.br/todas-as-maquininhas/';

const { chromium } = await import(pathToFileURL(corePath).href);
const browser = await chromium.launch({ headless: true, executablePath: browserPath });
const page = await browser.newPage({ viewport: { width: 1280, height: 1000 }, locale: 'pt-BR' });
await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
await page.waitForSelector('#offers-card', { timeout: 30000 });
await page.waitForTimeout(6000);

const title = await page.evaluate(
  () => (document.querySelector('.gntx-title')?.innerText || '').replace(/\s+/g, ' ').trim(),
);
const tiers = await page.$$eval('.js-tier', (buttons) =>
  buttons.map((b) => ({
    id: b.dataset.tier,
    label: (b.innerText || '').replace(/\s+/g, ' ').replace('NOVO', '').trim(),
  })),
);

const result = { fonte: URL, titulo: title, capturadoEm: new Date().toISOString(), faixas: [] };
for (const tier of tiers) {
  // Clica pelo próprio JavaScript da página: um pop-up de oferta fica por cima e bloquearia o clique.
  await page.evaluate((id) => document.querySelector(`.js-tier[data-tier="${id}"]`).click(), tier.id);
  await page.waitForTimeout(900);
  const dados = await page.evaluate(() => {
    const text = (selector) => (document.querySelector(selector)?.innerText || '').trim();
    return {
      debito: text('#rate-debit'),
      credito1x: text('#rate-credit'),
      parcelas: text('#inst-options'),
      descontoAluguel: text('#discount-val'),
      cartoes: text('#cards-aluguel'),
    };
  });
  result.faixas.push({ ...tier, ...dados });
}

// Quadro "Detalhes da oferta": faixas, bandeira e a tabela "A partir de".
await page.evaluate(() => {
  const el = [...document.querySelectorAll('a,button,div,span')].find((e) =>
    /^\s*DETALHES DA OFERTA\s*$/i.test(e.innerText || ''),
  );
  el?.click();
});
await page.waitForTimeout(2000);
result.detalhes = await page.evaluate(() => {
  const modal = document.querySelector('.gnt-modal-ca');
  return {
    texto: (modal?.innerText || '').trim(),
    bandeiras: [...document.querySelectorAll('.gnt-pill')]
      .map((p) => (p.innerText || '').trim())
      .filter((t) => !/^(At[ée]|Acima)/i.test(t)),
  };
});

fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, JSON.stringify(result, null, 2), 'utf8');
console.log(`capturado: ${result.faixas.length} faixas -> ${out}`);
await browser.close();
