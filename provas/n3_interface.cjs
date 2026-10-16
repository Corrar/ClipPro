/* Prova de interface da N-3 (N3-F2): comprar minutos num Chromium de verdade.
 *
 * Chamado por provas/prova_n3.py. MODO=aberta: compra ponta a ponta pelo
 * Mercado Pago FALSO (paga, avisa o webhook assinado e volta ao app).
 * MODO=fechada: com as vendas desligadas, a loja nao oferece nada.
 * Variaveis: APP_URL, MODO, SAIDA. Saida: linhas "CHECK {json}".
 *
 * Convencao: comentarios em PT-BR sem acento.
 */
"use strict";

const { chromium } = require("playwright");
const path = require("path");

const APP = process.env.APP_URL;
const MODO = process.env.MODO;
const SAIDA = process.env.SAIDA;

function confere(ok, descricao, detalhe = "") {
  console.log("CHECK " + JSON.stringify({ ok: Boolean(ok), descricao, detalhe: String(detalhe).slice(0, 160) }));
}
const limpo = (s) => (s || "").replace(/\s+/g, " ").trim();
async function texto(page, sel) {
  const el = await page.$(sel);
  return el ? limpo(await el.textContent()) : "";
}

(async () => {
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 }, locale: "pt-BR" })).newPage();
  const errosJs = [];
  page.on("pageerror", (e) => errosJs.push(String(e)));
  try {
    await page.goto(APP + "/");
    await page.fill("#email", "ana@exemplo.com");
    await page.fill("#senha", "senha-da-ana");
    await page.click("#enviar-conta");
    await page.waitForFunction(() => document.querySelector("#saldo-tc")?.textContent === "300 min");
    await page.click("#saldo");
    await page.waitForSelector("#extrato li");
    confere((await texto(page, "#cr-saldo")) === "300", "o saldo leva à tela de créditos (300)");
    confere((await texto(page, "#extrato li")).includes("Bônus de boas-vindas") &&
            (await texto(page, "#extrato li")).includes("+300 min"),
      "o extrato mostra o bônus de boas-vindas", await texto(page, "#extrato li"));

    if (MODO === "fechada") {
      confere(!(await page.$(".ingresso")) && !(await page.$("#pacotes-fechado[hidden]")),
        "com as vendas desligadas: nenhum pacote, e o aviso de que a loja abre no lançamento");
    } else {
      const ingressos = await page.$$eval(".ingresso", (els) => els.map((e) => e.textContent.replace(/\s+/g, " ").trim()));
      confere(ingressos.length === 2 && ingressos[0].includes("R$ 19,90") && ingressos[1].includes("R$ 79,90"),
        "só os 2 pacotes ativos aparecem, com o preço em reais", ingressos.join(" | "));
      confere(ingressos[0].includes("R$ 0,33 por minuto"), "cada pacote mostra o preço por minuto", ingressos[0]);
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(SAIDA, "5-creditos.png"), fullPage: true });

      await page.click(".ingresso button[data-pacote='p60']");
      await page.waitForURL(/#\/compra\/aprovada/, { timeout: 20000 });
      confere(true, "Comprar leva ao Mercado Pago e volta para o app depois de pagar");
      await page.waitForSelector("text=Pronto: 60 minutos entraram no seu saldo.", { timeout: 20000 });
      confere(true, "a volta confirma: 60 minutos entraram");
      await page.waitForFunction(() => document.querySelector("#saldo-tc")?.textContent === "360 min");
      confere((await texto(page, "#cp-saldo")) === "360", "o saldo sobe para 360 min");
      await page.screenshot({ path: path.join(SAIDA, "6-compra-aprovada.png") });

      await page.goto(APP + "/#/creditos");
      await page.waitForSelector("#extrato li");
      const primeira = await texto(page, "#extrato li");
      confere(primeira.includes("Compra de créditos") && primeira.includes("+60 min"),
        "o extrato mostra a compra no topo", primeira);
    }
    confere(errosJs.length === 0, "nenhum erro de JavaScript", errosJs.join(" | "));
  } catch (e) {
    confere(false, "a prova de compra rodou até o fim", String(e).split("\n")[0]);
    try { await page.screenshot({ path: path.join(SAIDA, `erro-${MODO}.png`), fullPage: true }); } catch (_) {}
  } finally {
    await browser.close();
  }
})();
