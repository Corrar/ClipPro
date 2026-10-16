/* Prova de interface da N-2 (N2-F2): um Chromium de verdade usando o app.
 *
 * Chamado por provas/prova_n2.py, que sobe o app, o Supabase falso e o S3
 * falso. Cada conferencia sai numa linha "CHECK {json}" que o Python le.
 * Variaveis: APP_URL, SB_URL (Supabase falso), SAIDA (pasta dos prints).
 *
 * Convencao: comentarios em PT-BR sem acento.
 */
"use strict";

const { chromium } = require("playwright");
const path = require("path");

const APP = process.env.APP_URL;
const SB = process.env.SB_URL;
const SAIDA = process.env.SAIDA;

function confere(ok, descricao, detalhe = "") {
  console.log("CHECK " + JSON.stringify({ ok: Boolean(ok), descricao, detalhe: String(detalhe).slice(0, 160) }));
}

// Print so depois das animacoes de entrada (0,35 s) e com a pagina no topo:
// o print de pagina inteira desenha o cabecalho fixo onde a rolagem estiver.
async function foto(page, nome, inteira = false) {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(SAIDA, nome), fullPage: inteira });
}

async function texto(page, seletor) {
  const el = await page.$(seletor);
  return el ? (await el.textContent()).trim() : "";
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, locale: "pt-BR" });
  await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: APP });
  const page = await ctx.newPage();
  const errosJs = [];
  let dialogo = false;
  page.on("pageerror", (e) => errosJs.push(String(e)));
  page.on("dialog", (d) => { dialogo = true; d.dismiss(); });
  // O app nao pode pedir nada a terceiros (fontes sao locais): registra
  // qualquer pedido que saia de 127.0.0.1.
  const externos = [];
  page.on("request", (r) => { if (!/^(https?:\/\/127\.0\.0\.1|data:|blob:)/.test(r.url())) externos.push(r.url()); });


  try {
    // 1. Entrar
    await page.goto(APP + "/");
    await page.waitForSelector("text=Do vídeo longo aos cortes que viralizam.");
    confere(true, "a tela de entrada abre (título e formulário)");
    await foto(page, "1-entrar.png");

    await page.click("#aba-criar");
    confere(!(await page.$("#consentimento[hidden]")) &&
            (await texto(page, "#consentimento")).includes("Termos de uso"),
      "ao criar conta, aparecem os links para os Termos e a Privacidade");
    await page.click("#aba-entrar");
    for (const [rota, titulo] of [["/termos", "Termos de uso"], ["/privacidade", "Política de privacidade"]]) {
      const r = await page.request.get(APP + rota + ".html");
      const corpo = await r.text();
      confere(r.status() === 200 && corpo.includes(`<h1>${titulo}</h1>`) && corpo.includes("Rascunho em revisão"),
        `a página ${rota} existe e está marcada como rascunho`);
    }
    confere((await page.$$("footer.rodape a")).length === 2, "o rodapé leva aos Termos e à Privacidade");

    await page.fill("#email", "ana@exemplo.com");
    await page.fill("#senha", "senha-errada");
    await page.click("#enviar-conta");
    await page.waitForSelector("#msg-conta:not([hidden])");
    confere((await texto(page, "#msg-conta")) === "E-mail ou senha incorretos.",
      "senha errada mostra mensagem em português", await texto(page, "#msg-conta"));

    await page.fill("#senha", "senha-da-ana");
    await page.click("#enviar-conta");
    await page.waitForFunction(() => document.querySelector("#saldo-tc")?.textContent === "300 min");
    confere(true, "login abre o painel com o saldo de 300 min");

    // 2. Pedido por link
    await page.fill("#link", "youtube");
    await page.click("#gerar");
    await page.waitForSelector("#msg-novo:not([hidden])");
    confere((await texto(page, "#msg-novo")).startsWith("Cole o link completo"),
      "link torto é recusado antes de ir ao servidor", await texto(page, "#msg-novo"));

    await page.fill("#link", "https://www.youtube.com/watch?v=abc123");
    await page.click("label.visual:has-text('Editorial')");
    await page.click(".contador-btn[data-passo='-1']");
    await page.click(".contador-btn[data-passo='-1']");
    await page.click("#gerar");
    await page.waitForSelector("#aviso:not([hidden])");
    confere((await texto(page, "#aviso")).startsWith("Vídeo na fila"), "pedido aceito: aviso de fila",
      await texto(page, "#aviso"));
    await page.waitForSelector(".rolo[data-status='pendente']");
    confere((await texto(page, ".rolo .chip")) === "Na fila", "o rolo aparece como “Na fila”");
    await page.waitForFunction(() => document.querySelector("#saldo-tc")?.textContent === "0 min");
    confere(true, "a reserva baixa o saldo para 0 min");
    confere(!(await page.$("#rolos-auto[hidden]")), "a lista avisa que está atualizando sozinha");
    await foto(page, "2-painel.png");

    // 3. O "worker" conclui (rota da falsa) e a lista se atualiza sozinha
    const href = await page.getAttribute(".rolo", "href");
    const id = href.split("/").pop();
    await fetch(SB + "/__prova/concluir", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }) });
    await page.waitForSelector(".rolo[data-status='concluido']", { timeout: 15000 });
    confere(true, "sem recarregar, o rolo vira “Pronto” (atualização automática)");
    await page.waitForFunction(() => document.querySelector("#saldo-tc")?.textContent === "298 min", null, { timeout: 15000 });
    confere(true, "o saldo volta para 298 min (devolução do que sobrou)");

    // 4. Tela dos clipes
    await page.click(".rolo");
    await page.waitForSelector(".clipe");
    confere((await texto(page, ".validade")).startsWith("Disponíveis até"),
      "a tela avisa até quando os clipes ficam disponíveis", await texto(page, ".validade"));
    const titulos = await page.$$eval(".clipe-titulo", (els) => els.map((e) => e.textContent));
    confere(titulos.length === 2, "os 2 clipes aparecem", titulos.join(" | "));
    confere(titulos.includes("<img src=x onerror=alert(1)>") && !dialogo && !(await page.$(".clipe img")),
      "título malicioso aparece como texto, sem executar nada");
    const src = await page.getAttribute(".clipe video", "src");
    confere(src.includes("X-Amz-Signature="), "o vídeo usa URL assinada do R2");
    const baixar = await page.getAttribute(".clipe a.btn", "href");
    const resp = await page.request.get(baixar);
    confere(resp.status() === 200 && (resp.headers()["content-disposition"] || "").startsWith("attachment"),
      "o botão Baixar entrega o arquivo como download", resp.headers()["content-disposition"] || resp.status());
    await page.click("button:has-text('Copiar gancho')");
    await page.waitForFunction(() => document.querySelector("#aviso")?.textContent === "Gancho copiado.");
    const area = await page.evaluate(() => navigator.clipboard.readText());
    confere(area === "Ninguém esperava essa resposta", "Copiar gancho põe o gancho na área de transferência", area);
    await page.click("button:has-text('Copiar legenda do post')");
    await page.waitForFunction(() => /Texto de publicação copiado|Não consegui/.test(document.querySelector("#aviso")?.textContent || ""));
    confere((await page.evaluate(() => navigator.clipboard.readText())).startsWith("Texto do post"),
      "Copiar legenda do post busca o texto no R2 e copia");
    await foto(page, "3-clipes.png", true);

    // 5. Pedido por arquivo (envio direto ao R2 pela URL assinada)
    await page.click("a.voltar");
    await page.waitForSelector("#form-novo");
    await page.click("#via-arquivo");
    await page.setInputFiles("#arquivo", { name: "aula.mp4", mimeType: "video/mp4", buffer: Buffer.alloc(50000, 7) });
    await page.waitForSelector("#arquivo-info:not([hidden])");
    confere((await texto(page, "#arquivo-info")).startsWith("aula.mp4"), "o arquivo escolhido aparece", await texto(page, "#arquivo-info"));
    await page.click("#gerar");
    await page.waitForFunction(() => (document.querySelector("#aviso")?.textContent || "").startsWith("Vídeo na fila"), null, { timeout: 15000 });
    confere((await texto(page, "#progresso-txt")) === "100%" || (await page.$("#progresso[hidden]")),
      "o envio vai até 100%");
    await page.waitForSelector(".rolo[data-status='pendente']");
    confere((await texto(page, ".rolo[data-status='pendente'] .rolo-titulo")) === "Vídeo enviado",
      "o pedido por arquivo entra na fila");

    // 6. Celular: nada de rolagem lateral
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(300);
    const larguras = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    confere(larguras[0] <= larguras[1] + 1, "no celular (390 px) não há rolagem lateral", larguras.join(" x "));
    await foto(page, "4-celular.png", true);
    await page.setViewportSize({ width: 1366, height: 900 });

    // 7. Sair; conta sem convite cai na tela do beta
    await page.click("#sair");
    await page.waitForSelector("#form-conta");
    confere(true, "Sair volta para a tela de entrada");
    await page.fill("#email", "bia@exemplo.com");
    await page.fill("#senha", "senha-da-bia");
    await page.click("#enviar-conta");
    await page.waitForSelector("text=Sua conta está criada.");
    confere((await texto(page, "#beta-email")) === "bia@exemplo.com", "conta sem convite vê a tela do beta fechado");

    confere(errosJs.length === 0, "nenhum erro de JavaScript na página", errosJs.join(" | "));
    confere(externos.length === 0, "o app não pediu nada a terceiros (fontes locais, sem Google)",
      externos.slice(0, 3).join(" | "));
    const fontes = await page.evaluate(() => document.fonts.check('16px "Anton"') && document.fonts.check('16px "Archivo"'));
    confere(fontes, "as fontes da marca (Anton, Archivo) carregaram do próprio app");
  } catch (e) {
    confere(false, "a prova de interface rodou até o fim", String(e).split("\n")[0]);
    try { await page.screenshot({ path: path.join(SAIDA, "erro.png"), fullPage: true }); } catch (_) {}
  } finally {
    await browser.close();
  }
})();
