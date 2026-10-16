/* Prova da galeria de modelos (N5-F1): um Chromium de verdade medindo as
 * previas contra os numeros dos presets.
 *
 * Chamado por provas/prova_n5.py, que sobe o app e a nuvem falsa e passa a
 * tabela PREVIAS gerada dos presets (nao a do app.js: a prova compara com a
 * fonte, nao consigo mesma). Saida: linhas "CHECK {json}".
 * Variaveis: APP_URL, SAIDA, VIDEO (arquivo de teste), PREVIAS (json).
 *
 * Convencao: comentarios em PT-BR sem acento.
 */
"use strict";

const { chromium } = require("playwright");
const path = require("path");

const APP = process.env.APP_URL;
const SAIDA = process.env.SAIDA;
const VIDEO = process.env.VIDEO;
const PREVIAS = JSON.parse(process.env.PREVIAS);

function confere(ok, descricao, detalhe = "") {
  console.log("CHECK " + JSON.stringify({ ok: Boolean(ok), descricao, detalhe: String(detalhe).slice(0, 200) }));
}
const rgb = (hex) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
};
const perto = (a, b, tol = 1.5) => Math.abs(a - b) <= tol;
// Escala 1 vem como "none" ou como a matriz identidade, conforme o CSS.
const semEscala = (t) => t === "none" || t === "matrix(1, 0, 0, 1, 0, 0)";
const sel = (nome) => `.visual[data-modelo="${nome}"] .previa`;

// Print do compositor inteiro numa janela alta: print de elemento maior que a
// janela costura pedacos e desenha o topo e a barra fixos no meio.
async function fotoCompositor(page, nome) {
  await page.setViewportSize({ width: 1366, height: 1700 });
  await page.evaluate(() => { window.scrollTo(0, 0); document.querySelector("#aviso").hidden = true; });
  await page.waitForTimeout(500);
  const caixa = await page.locator("#form-novo").boundingBox();
  await page.screenshot({ path: path.join(SAIDA, nome), clip: { x: caixa.x - 24, y: caixa.y - 24,
    width: caixa.width + 48, height: caixa.height + 48 } });
}

async function legenda(page, nome) {
  return page.$eval(sel(nome), (pv) => {
    const leg = pv.querySelector(".pv-legenda");
    const ag = leg.querySelector(".agora");
    return leg.textContent + "|" + (ag ? ag.textContent : "");
  });
}

// Cores e escala de cada estado do karaoke, lidas do CSS calculado.
async function estados(page, nome) {
  return page.$eval(sel(nome), (pv) => {
    const cs = (e) => (e ? getComputedStyle(e) : null);
    const spans = [...pv.querySelectorAll(".pv-legenda span")];
    const porFalar = spans.find((s) => !s.className);
    const dita = spans.find((s) => s.classList.contains("dita"));
    const agora = spans.find((s) => s.classList.contains("agora"));
    return {
      porFalar: porFalar && cs(porFalar).color, dita: dita && cs(dita).color,
      agora: agora && cs(agora).color, escala: agora && cs(agora).transform,
      curta: agora ? agora.classList.contains("curta") : false,
    };
  });
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, locale: "pt-BR" });
  const page = await ctx.newPage();
  const errosJs = [];
  const externos = [];
  page.on("pageerror", (e) => errosJs.push(String(e)));
  page.on("request", (r) => { if (!/^(https?:\/\/127\.0\.0\.1|data:|blob:)/.test(r.url())) externos.push(r.url()); });
  // Violacao de CSP aparece no console; com a CSP de producao no servidor,
  // qualquer uma derruba a prova.
  const bloqueios = [];
  page.on("console", (m) => { if (/Content Security Policy/i.test(m.text())) bloqueios.push(m.text()); });

  try {
    // 1. Vitrine da entrada
    await page.goto(APP + "/");
    await page.waitForSelector("#vitrine .previa");
    const vivas = await page.$$eval("#vitrine .previa.viva", (els) => els.map((e) => e.dataset.modelo));
    confere(vivas.length === 3, "a entrada mostra 3 modelos de verdade, animados", vivas.join(", "));
    const a0 = await page.$eval("#vitrine .previa .pv-legenda", (e) => e.innerHTML);
    await page.waitForTimeout(1500);
    const a1 = await page.$eval("#vitrine .previa .pv-legenda", (e) => e.innerHTML);
    confere(a0 !== a1, "o karaokê da vitrine avança sozinho");
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(SAIDA, "1-entrar.png") });

    // 2. Entrar
    await page.fill("#email", "ana@exemplo.com");
    await page.fill("#senha", "senha-da-ana");
    await page.click("#enviar-conta");
    await page.waitForFunction(() => document.querySelector("#saldo-tc")?.textContent === "300 min");
    await page.waitForSelector("#visuais .visual .previa");
    const nomes = await page.$$eval("#visuais .visual", (els) => els.map((e) => e.dataset.modelo));
    confere(nomes.join() === Object.keys(PREVIAS).join(), "a galeria mostra os 4 modelos de fábrica", nomes.join(", "));

    // 3. Geometria: cada pixel do canvas 1080x1920 do motor, na escala da previa
    for (const nome of Object.keys(PREVIAS)) {
      const P = PREVIAS[nome];
      const g = await page.$eval(sel(nome), (pv) => {
        const r = pv.getBoundingClientRect();
        const caixa = (s) => { const e = pv.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect();
          return { x: b.left - r.left, y: b.top - r.top, w: b.width, h: b.height, base: r.bottom - b.bottom }; };
        return { w: r.width, h: r.height, cartao: caixa(".pv-cartao"), titulo: caixa(".pv-titulo"),
                 barra: caixa(".pv-barra"), legenda: caixa(".pv-legenda") };
      });
      const u = g.w / 1080;
      const erros = [];
      if (!perto(g.h, 1920 * u)) erros.push(`proporção ${g.w}x${g.h}`);
      if (!perto(g.legenda.base, P.legenda.margem_inferior * u)) erros.push(`legenda a ${g.legenda.base} da base`);
      if (!perto(g.legenda.x, P.legenda.margem_lateral * u)) erros.push(`margem ${g.legenda.x}`);
      const C = P.composicao;
      if (C) {
        const k = C.cartao;
        if (!g.cartao || !perto(g.cartao.x, k.x * u) || !perto(g.cartao.y, k.y * u) || !perto(g.cartao.w, k.largura * u)
            || !perto(g.cartao.h, k.altura * u)) erros.push(`cartão ${JSON.stringify(g.cartao)}`);
        if (C.titulo && (!g.titulo || !perto(g.titulo.x, C.titulo.x * u) || !perto(g.titulo.y, C.titulo.y * u)
            || !perto(g.titulo.h, C.titulo.altura * u))) erros.push(`título ${JSON.stringify(g.titulo)}`);
        if (C.progresso && (!g.barra || !perto(g.barra.y, C.progresso.y * u)
            || !perto(g.barra.x, (k.x + C.progresso.recuo) * u)
            || !perto(g.barra.w, (k.largura - 2 * C.progresso.recuo) * u))) erros.push(`barra ${JSON.stringify(g.barra)}`);
      } else if (g.cartao || g.titulo || g.barra) {
        erros.push("modelo de tela cheia desenhou moldura");
      }
      confere(!erros.length, `a prévia de “${nome}” tem a geometria do preset`, erros.join("; "));
    }

    // 4. Regra de cores do karaoke (motor: legendas._bloco_palavra), nas
    //    previas paradas -- a 1a esta escolhida e anima, as outras nao.
    for (const nome of Object.keys(PREVIAS).slice(1)) {
      const L = PREVIAS[nome].legenda;
      const e = await estados(page, nome);
      const esperado = { porFalar: rgb(L.por_falar), dita: rgb(L.falada),
                         agora: rgb(L.destaque && !e.curta ? L.destaque : L.falada) };
      const ok = Boolean(e.porFalar && e.dita && e.agora) && e.porFalar === esperado.porFalar && e.dita === esperado.dita && e.agora === esperado.agora
        && (L.pop > 100 && !e.curta ? !semEscala(e.escala) : semEscala(e.escala));
      confere(ok, `“${nome}”: por falar, falada e acesa nas cores do preset${L.pop > 100 ? ", com pop" : ", sem pop"}`,
        JSON.stringify(e));
    }
    const mudou = (await legenda(page, "cortes")) !== (await page.waitForTimeout(1000), await legenda(page, "cortes"));
    confere(mudou, "o modelo escolhido fica animado na galeria");
    await fotoCompositor(page, "2-galeria.png");

    // 5. Escolher outro: a escolha anima, a anterior para, e a palavra curta
    //    ("é", "o") nao ganha destaque nos modelos com destaque_minimo.
    await page.click(".visual[data-modelo='bold-amarelo']");
    await page.mouse.move(5, 5);
    await page.waitForTimeout(300);
    const boldVivo = await page.$eval(sel("bold-amarelo"), (e) => e.classList.contains("viva"));
    const cortesParado = !(await page.$eval(sel("cortes"), (e) => e.classList.contains("viva")));
    confere(boldVivo && cortesParado, "trocar de modelo passa a animação para o escolhido");
    const ec = await estados(page, "cortes");
    const Lc = PREVIAS.cortes.legenda;
    confere(ec.porFalar === rgb(Lc.por_falar) && ec.dita === rgb(Lc.falada) && ec.agora === rgb(Lc.destaque),
      "“cortes” parado volta a mostrar as três cores", JSON.stringify(ec));
    await page.hover(".visual[data-modelo='cortes-editorial']");
    const curta = await page.waitForSelector(`${sel("cortes-editorial")} .agora.curta`, { timeout: 15000 }).catch(() => null);
    if (curta) {
      const c = await curta.evaluate((s) => ({ cor: getComputedStyle(s).color, escala: getComputedStyle(s).transform }));
      const Le = PREVIAS["cortes-editorial"].legenda;
      confere(c.cor === rgb(Le.falada) && semEscala(c.escala),
        "palavra curta acende sem destaque nem pop (destaque_minimo_letras)", JSON.stringify(c));
    } else {
      confere(false, "palavra curta acende sem destaque nem pop (destaque_minimo_letras)", "não apareceu em 15 s");
    }
    await page.mouse.move(5, 5);

    // 6. Arquivo: um quadro do proprio video entra nas previas (lido no
    //    navegador, sem sair dele)
    await page.click("#via-arquivo");
    await page.setInputFiles("#arquivo", VIDEO);
    await page.waitForFunction(() => /quadro do seu vídeo/.test(document.querySelector("#modelos-nota")?.textContent || ""),
      null, { timeout: 15000 });
    const fundo = await page.$eval(".visual .pv-cena", (e) => getComputedStyle(e).backgroundImage);
    confere(fundo.startsWith('url("data:image/jpeg'), "as prévias passam a usar um quadro do vídeo escolhido",
      fundo.slice(0, 40));
    // O quadro de teste sao barras de cor: o centro da previa de tela cheia
    // tem de sair colorido, nao cinza.
    const cor = await page.$eval(sel("clean-branco"), async (pv) => {
      const fundoUrl = getComputedStyle(pv.querySelector(".pv-cena")).backgroundImage.slice(5, -2);
      const img = new Image();
      img.src = fundoUrl;
      await img.decode();
      const c = document.createElement("canvas");
      c.width = img.width; c.height = img.height;
      const g = c.getContext("2d");
      g.drawImage(img, 0, 0);
      const d = g.getImageData(Math.round(img.width * 0.4), Math.round(img.height * 0.3), 1, 1).data;
      return [d[0], d[1], d[2]];
    });
    confere(Math.max(...cor) - Math.min(...cor) > 60, "o quadro é mesmo o do vídeo (barras coloridas)", cor.join(","));
    await page.mouse.move(5, 5);
    await fotoCompositor(page, "3-galeria-com-video.png");
    await page.click("#via-link");
    const semQuadro = await page.$eval(".visual .pv-cena", (e) => getComputedStyle(e).backgroundImage);
    confere(!semQuadro.includes("data:image"), "voltando para Link, o quadro do arquivo sai das prévias");
    await page.click("#via-arquivo");

    await page.click("#gerar");
    await page.waitForFunction(() => (document.querySelector("#aviso")?.textContent || "").startsWith("Vídeo na fila"),
      null, { timeout: 20000 });
    confere(true, "o pedido com o modelo escolhido entra na fila");

    // 7. Movimento reduzido: nada anima
    await page.emulateMedia({ reducedMotion: "reduce" });
    const r0 = await legenda(page, "bold-amarelo");
    await page.waitForTimeout(1200);
    confere(r0 === (await legenda(page, "bold-amarelo")), "com “reduzir movimento” ligado, as prévias ficam paradas");
    await page.emulateMedia({ reducedMotion: "no-preference" });

    // 8. Celular: duas colunas, sem rolagem lateral
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(300);
    const larg = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    const xs = await page.$$eval("#visuais .visual", (els) => els.map((e) => Math.round(e.getBoundingClientRect().left)));
    confere(larg[0] <= larg[1] + 1 && xs[0] === xs[2] && xs[1] === xs[3] && xs[0] !== xs[1],
      "no celular: galeria em 2 colunas, sem rolagem lateral", `${larg.join("x")} · ${xs.join(",")}`);
    await page.evaluate(() => { window.scrollTo(0, 0); document.querySelector("#aviso").hidden = true; });
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(SAIDA, "4-celular.png"), fullPage: true });

    const cspAtiva = await page.evaluate(async () => (await fetch("/", { cache: "no-store" })).headers.get("content-security-policy") || "");
    confere(cspAtiva.includes("style-src 'self'") && bloqueios.length === 0,
      "tudo funcionou sob a CSP de produção (vercel.json), sem nenhum bloqueio", bloqueios.slice(0, 2).join(" | ") || cspAtiva.slice(0, 60));
    confere(errosJs.length === 0, "nenhum erro de JavaScript", errosJs.join(" | "));
    confere(externos.length === 0, "nada pedido a terceiros", externos.slice(0, 3).join(" | "));
  } catch (e) {
    confere(false, "a prova da galeria rodou até o fim", String(e).split("\n")[0]);
    try { await page.screenshot({ path: path.join(SAIDA, "erro.png"), fullPage: true }); } catch (_) {}
  } finally {
    await browser.close();
  }
})();
