/* ClipPro, app na nuvem (N-2, RULINGS §29.3; desenho da N-5, §30).
 *
 * TRES REGRAS QUE EXPLICAM O RESTO:
 * 1. NENHUMA CHAVE SECRETA AQUI. O navegador so conhece a URL e a chave
 *    PUBLICA do Supabase (vem de /api/config). O que cada conta pode ver e
 *    fazer e decidido no banco (RLS + criar_trabalho), nao neste arquivo.
 * 2. CONTEUDO DINAMICO SO POR textContent. Titulo de clipe, gancho e
 *    mensagem de erro vem de fora; nada disso passa por innerHTML (o D3 do
 *    PENDENCIAS foi um escapar() que nao escapava aspas).
 * 3. A ULTIMA NAVEGACAO VENCE. Cada tela leva o numero da "vez"; resposta
 *    que chega depois de o usuario ter trocado de tela e descartada.
 *
 * Convencao: comentarios em PT-BR sem acento; textos para o usuario em PT-BR
 * com acentuacao correta.
 */
"use strict";

(function () {
  // Os modelos que a galeria oferece. Nome e ordem conferidos pela N5-E1.
  const PRESETS = [
    { nome: "cortes", titulo: "Cortes", tag: "Moldura",
      desc: "Vídeo em moldura com título e barra de progresso. A palavra dita acende em amarelo." },
    { nome: "cortes-editorial", titulo: "Editorial", tag: "Moldura",
      desc: "Moldura sóbria, título em tarja e destaque âmbar. Legenda em caixa mista." },
    { nome: "bold-amarelo", titulo: "Bold", tag: "Tela cheia",
      desc: "Letras grandes com contorno grosso; a fala vai ficando amarela. Lê em qualquer fundo." },
    { nome: "clean-branco", titulo: "Clean", tag: "Tela cheia",
      desc: "Negrito branco e discreto, para vídeos que já têm muita informação na tela." },
  ];

  // >>> PREVIAS -- gerado por `python provas/prova_n5.py --gerar`; N5-E1 confere
  const PREVIAS = {
    "cortes": {
      "legenda": {
        "fonte": "Impact",
        "tamanho": 92,
        "negrito": false,
        "maiusculas": true,
        "espacamento": 1,
        "por_falar": "#FFFFFF",
        "falada": "#BFBFBF",
        "destaque": "#FFE500",
        "pop": 112,
        "destaque_minimo": 3,
        "contorno_cor": "#000000",
        "contorno": 6,
        "sombra_cor": "#000000",
        "sombra_opacidade": 0.294,
        "sombra": 4,
        "margem_lateral": 175,
        "margem_inferior": 520,
        "palavras_linha": 3
      },
      "composicao": {
        "cartao": {
          "x": 134,
          "y": 240,
          "largura": 810,
          "altura": 1440,
          "raio": 36,
          "traco": 2.0,
          "traco_cor": "#FFFFFF",
          "traco_opacidade": 0.14,
          "sombra_dy": 20,
          "sombra_sigma": 30.0,
          "sombra_opacidade": 0.6,
          "sombra_cor": "#000000"
        },
        "fundo": {
          "escurecer": 0.4,
          "saturacao": 1.05,
          "vinheta": 0.0
        },
        "titulo": {
          "fonte": "Segoe UI Black",
          "tamanho": 44,
          "maiusculas": true,
          "cor": "#FFFFFF",
          "pilula_cor": "#101317",
          "pilula_opacidade": 0.84,
          "altura": 108,
          "raio": 54,
          "padding_h": 36,
          "largura_maxima": 810,
          "x": 135,
          "y": 64,
          "acento": "barra",
          "acento_cor": "#FFE500",
          "acento_largura": 8,
          "acento_altura": 44,
          "acento_gap": 22
        },
        "progresso": {
          "y": 1656,
          "altura": 10,
          "recuo": 40,
          "trilho_cor": "#FFFFFF",
          "trilho_opacidade": 0.35,
          "cor": "#FFE500",
          "opacidade": 1.0,
          "contorno": 2,
          "contorno_cor": "#000000",
          "contorno_opacidade": 0.45
        },
        "scrim": {
          "y_inicio": 1000,
          "y_fim": 1260,
          "opacidade": 0.28,
          "cor": "#000000"
        }
      }
    },
    "cortes-editorial": {
      "legenda": {
        "fonte": "Segoe UI Black",
        "tamanho": 84,
        "negrito": false,
        "maiusculas": false,
        "espacamento": 0,
        "por_falar": "#8E887C",
        "falada": "#F2EDE3",
        "destaque": "#FFC24A",
        "pop": 112,
        "destaque_minimo": 3,
        "contorno_cor": "#0D0B09",
        "contorno": 2,
        "sombra_cor": "#000000",
        "sombra_opacidade": 0.451,
        "sombra": 3,
        "margem_lateral": 171,
        "margem_inferior": 500,
        "palavras_linha": 3
      },
      "composicao": {
        "cartao": {
          "x": 134,
          "y": 240,
          "largura": 810,
          "altura": 1440,
          "raio": 32,
          "traco": 2.0,
          "traco_cor": "#FFFFFF",
          "traco_opacidade": 0.16,
          "sombra_dy": 24,
          "sombra_sigma": 38.0,
          "sombra_opacidade": 0.65,
          "sombra_cor": "#000000"
        },
        "fundo": {
          "escurecer": 0.36,
          "saturacao": 0.72,
          "vinheta": 0.18
        },
        "titulo": {
          "fonte": "Bahnschrift",
          "tamanho": 42,
          "maiusculas": true,
          "cor": "#F4EFE6",
          "pilula_cor": "#14110E",
          "pilula_opacidade": 0.88,
          "altura": 100,
          "raio": 28,
          "padding_h": 40,
          "largura_maxima": 810,
          "x": 135,
          "y": 88,
          "acento": "circulo",
          "acento_cor": "#FFC24A",
          "acento_largura": 12,
          "acento_altura": 12,
          "acento_gap": 18
        },
        "progresso": {
          "y": 1658,
          "altura": 8,
          "recuo": 40,
          "trilho_cor": "#FFFFFF",
          "trilho_opacidade": 0.3,
          "cor": "#FFC24A",
          "opacidade": 1.0,
          "contorno": 2,
          "contorno_cor": "#000000",
          "contorno_opacidade": 0.4
        },
        "scrim": {
          "y_inicio": 1080,
          "y_fim": 1330,
          "opacidade": 0.45,
          "cor": "#000000"
        }
      }
    },
    "bold-amarelo": {
      "legenda": {
        "fonte": "Impact",
        "tamanho": 96,
        "negrito": false,
        "maiusculas": true,
        "espacamento": 1,
        "por_falar": "#FFFFFF",
        "falada": "#FFE500",
        "destaque": null,
        "pop": 100,
        "destaque_minimo": 0,
        "contorno_cor": "#000000",
        "contorno": 7,
        "sombra_cor": "#000000",
        "sombra_opacidade": 0.294,
        "sombra": 4,
        "margem_lateral": 110,
        "margem_inferior": 520,
        "palavras_linha": 4
      },
      "composicao": null
    },
    "clean-branco": {
      "legenda": {
        "fonte": "Segoe UI",
        "tamanho": 82,
        "negrito": true,
        "maiusculas": false,
        "espacamento": 0,
        "por_falar": "#A8A8A8",
        "falada": "#FFFFFF",
        "destaque": null,
        "pop": 100,
        "destaque_minimo": 0,
        "contorno_cor": "#141414",
        "contorno": 4,
        "sombra_cor": "#000000",
        "sombra_opacidade": 0.412,
        "sombra": 2,
        "margem_lateral": 120,
        "margem_inferior": 500,
        "palavras_linha": 5
      },
      "composicao": null
    }
  };
  // <<< PREVIAS

  const ROTULOS = { pendente: "Na fila", em_curso: "Processando", concluido: "Pronto",
                    falhou: "Falhou", recusado: "Recusado" };
  const ICONE_STATUS = { pendente: "relogio", em_curso: "engrenagem", concluido: "check",
                         falhou: "alerta", recusado: "alerta" };
  const EXTENSOES = [".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"];
  const LIMITE_ARQUIVO = 2 * 1024 ** 3;
  const N_MAX = 10;
  const INTERVALO_MS = 8000;

  const MOTIVOS = { cadastro: "Bônus de boas-vindas", reserva: "Reserva para um vídeo",
                    devolucao: "Devolução do que sobrou", compra: "Compra de créditos", ajuste: "Ajuste" };
  const estado = {
    sb: null, sessao: null, saldo: null, vez: 0, timer: null, recuperando: false, compras: false,
    modoConta: "entrar", via: "link", arquivo: null, duracaoArquivo: null, quadro: null,
  };

  // ------------------------------------------------------------ apoio
  const $ = (seletor, raiz = document) => raiz.querySelector(seletor);

  function montar(id) {
    const no = document.getElementById(id).content.firstElementChild.cloneNode(true);
    document.getElementById("tela").replaceChildren(no);
    return no;
  }

  function el(tag, props = {}, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "texto") e.textContent = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : String(v));
    }
    for (const f of filhos) if (f !== null && f !== undefined && f !== false) e.append(f);
    return e;
  }

  // Icones de traco, desenhados aqui: nada de biblioteca nem de <img>.
  const ICONES = {
    check: "M5 12.5l4.2 4.2L19 7",
    relogio: "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17zM12 7.5V12l3 2",
    engrenagem: "M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3M6 6l2.1 2.1M15.9 15.9L18 18M6 18l2.1-2.1M15.9 8.1L18 6",
    alerta: "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17zM12 8v4.5M12 16v.01",
    baixar: "M12 4v11m0 0l-4.5-4.5M12 15l4.5-4.5M5 19.5h14",
    copiar: "M9 9h10v10H9zM15 9V5H5v10h4",
  };
  function icone(nome, tam = 16) {
    const NS = "http://www.w3.org/2000/svg";
    const s = document.createElementNS(NS, "svg");
    for (const [k, v] of Object.entries({ viewBox: "0 0 24 24", width: tam, height: tam, "aria-hidden": "true" })) s.setAttribute(k, v);
    const p = document.createElementNS(NS, "path");
    for (const [k, v] of Object.entries({ d: ICONES[nome], fill: "none", stroke: "currentColor", "stroke-width": "1.8",
                                          "stroke-linecap": "round", "stroke-linejoin": "round" })) p.setAttribute(k, v);
    s.append(p);
    return s;
  }

  function msg(alvo, texto, tipo = "erro") {
    if (!alvo) return;
    alvo.textContent = texto || "";
    alvo.className = `msg ${tipo}`;
    alvo.hidden = !texto;
  }

  let avisoTimer = null;
  function avisar(texto) {
    const a = $("#aviso");
    a.textContent = texto;
    a.hidden = false;
    clearTimeout(avisoTimer);
    avisoTimer = setTimeout(() => { a.hidden = true; }, 5000);
  }

  function quando(iso) {
    const d = new Date(iso);
    const s = (Date.now() - d.getTime()) / 1000;
    if (!isFinite(s)) return "";
    if (s < 60) return "agora";
    if (s < 3600) return `há ${Math.floor(s / 60)} min`;
    if (s < 86400) return `há ${Math.floor(s / 3600)} h`;
    return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" });
  }

  function nomePreset(nome) {
    return (PRESETS.find((p) => p.nome === nome) || { titulo: nome || "—" }).titulo;
  }

  function tamanhoLegivel(bytes) {
    if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1).replace(".", ",")} GB`;
    return `${Math.max(1, Math.round(bytes / 1024 ** 2))} MB`;
  }

  function relogio(segundos) {
    const s = Math.round(segundos);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  // Erros do Supabase Auth vem em ingles; os do banco (criar_trabalho) ja vem
  // em portugues e passam direto.
  function legivel(erro) {
    const texto = String((erro && (erro.message || erro.msg)) || erro || "");
    const codigo = String((erro && (erro.code || erro.error_code)) || "");
    const tudo = `${texto} ${codigo}`;
    if (/invalid login credentials|invalid_credentials/i.test(tudo)) return "E-mail ou senha incorretos.";
    if (/email not confirmed|email_not_confirmed/i.test(tudo))
      return "Confirme o seu e-mail antes de entrar: o link está na sua caixa de entrada.";
    if (/already registered|user_already_exists/i.test(tudo))
      return "Este e-mail já tem conta. Entre, ou use “Esqueci minha senha”.";
    if (/weak_password|at least \d+ characters/i.test(tudo)) return "A senha precisa de pelo menos 8 caracteres.";
    if (/rate limit|over_.*_rate_limit/i.test(tudo)) return "Muitas tentativas seguidas. Espere um minuto e tente de novo.";
    if (/failed to fetch|networkerror|load failed/i.test(tudo))
      return "Sem conexão com o ClipPro agora. Confira a internet e tente de novo.";
    if (/[áàâãéêíóôõúç]/i.test(texto)) return texto.charAt(0).toUpperCase() + texto.slice(1);
    return "Algo deu errado. Tente de novo em instantes.";
  }

  async function token() {
    const { data } = await estado.sb.auth.getSession();
    return data && data.session ? data.session.access_token : null;
  }

  function pararRolos() {
    clearTimeout(estado.timer);
    estado.timer = null;
  }

  async function copiar(texto) {
    try {
      await navigator.clipboard.writeText(texto);
    } catch (_) {
      const area = el("textarea", { class: "copia", "aria-hidden": "true" });
      area.value = texto;
      document.body.append(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
  }

  // ------------------------------------------------------------ previas dos modelos
  // Cada previa e o quadro 1080x1920 do motor em miniatura: posicoes, tamanhos
  // e cores vem da tabela PREVIAS (gerada dos presets). O CSS converte "pixel
  // do motor" em tela com --u; aqui so se passam os numeros.
  //
  // libass mede o tamanho da fonte pela altura total dela (ascendente +
  // descendente), nao pelo "em" do CSS. Os fatores abaixo saem das metricas
  // OS/2 (win) de cada fonte: Impact 2066+432 em 2048 -> 1,22, logo 1/1,22;
  // Segoe UI 2210+514 em 2048 -> 1,33. As reservas (Anton, Archivo) so entram
  // fora do Windows e nao sao identicas: a previa ali e aproximada.
  const FONTES = {
    "Impact": { pilha: 'Impact, "Anton", "Arial Narrow", sans-serif', peso: 400, fe: 0.82 },
    "Segoe UI": { pilha: '"Segoe UI", "Archivo", sans-serif', peso: 400, fe: 0.75 },
    "Segoe UI Black": { pilha: '"Segoe UI Black", "Segoe UI", "Archivo", sans-serif', peso: 900, fe: 0.75 },
    "Bahnschrift": { pilha: 'Bahnschrift, "Archivo", sans-serif', peso: 600, largura: "82%", fe: 0.8 },
  };
  const fonte = (nome) => FONTES[nome] || { pilha: '"Archivo", sans-serif', peso: 600, fe: 0.8 };
  // Frase e titulo de exemplo: neutros, e com palavra curta ("é", "o") para
  // mostrar a regra do destaque minimo de letras.
  const FRASE = "Esse é o detalhe que faz o público ficar até o fim".split(" ");
  const TITULO_EXEMPLO = "Como segurar o público";

  function rgba(hex, opacidade) {
    const n = parseInt(String(hex).replace("#", ""), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${opacidade})`;
  }

  function previa(nome, fase = 0) {
    const p = PREVIAS[nome];
    const L = p.legenda;
    const C = p.composicao;
    const raiz = el("div", { class: `previa previa-${nome}`, "data-modelo": nome });
    const v = (k, val) => raiz.style.setProperty(k, String(val));

    if (C) {
      const k = C.cartao;
      v("--saturacao", C.fundo.saturacao);
      v("--escurecer", C.fundo.escurecer);
      v("--vinheta", C.fundo.vinheta);
      v("--cx", k.x); v("--cy", k.y); v("--cw", k.largura); v("--ch", k.altura); v("--craio", k.raio);
      v("--sdy", k.sombra_dy); v("--ssig", k.sombra_sigma); v("--scor", rgba(k.sombra_cor, k.sombra_opacidade));
      v("--traco", k.traco); v("--traco-cor", rgba(k.traco_cor, k.traco_opacidade));
      const cartao = el("div", { class: "pv-cartao" }, el("div", { class: "pv-cena" }));
      if (C.scrim) {
        v("--scy", Math.max(0, C.scrim.y_inicio - k.y));
        v("--sch", Math.max(1, C.scrim.y_fim - C.scrim.y_inicio));
        v("--scrim", rgba(C.scrim.cor, C.scrim.opacidade));
        cartao.append(el("div", { class: "pv-scrim" }));
      }
      raiz.append(el("div", { class: "pv-fundo" }, el("div", { class: "pv-cena" })),
                  el("div", { class: "pv-vinheta" }), cartao);
      if (C.progresso) {
        const b = C.progresso;
        v("--bx", k.x + b.recuo); v("--by", b.y); v("--bw", k.largura - 2 * b.recuo); v("--bh", b.altura);
        v("--btrilho", rgba(b.trilho_cor, b.trilho_opacidade)); v("--bcor", rgba(b.cor, b.opacidade));
        v("--bc", b.contorno); v("--bcontorno", rgba(b.contorno_cor, b.contorno_opacidade));
        raiz.append(el("div", { class: "pv-barra" }));
      }
      if (C.titulo) {
        const t = C.titulo;
        const f = fonte(t.fonte);
        v("--tix", t.x); v("--tiy", t.y); v("--tih", t.altura); v("--timax", t.largura_maxima);
        v("--tip", t.padding_h); v("--tir", t.raio); v("--tifundo", rgba(t.pilula_cor, t.pilula_opacidade));
        v("--ticor", t.cor); v("--tifonte", f.pilha); v("--tipeso", f.peso); v("--tife", f.fe);
        v("--tilargura", f.largura || "100%"); v("--tit", t.tamanho); v("--ticaixa", t.maiusculas ? "uppercase" : "none");
        v("--ag", t.acento_gap); v("--aw", t.acento_largura); v("--ah", t.acento_altura); v("--acor", t.acento_cor);
        raiz.append(el("div", { class: "pv-titulo" },
          t.acento && t.acento !== "nenhum" ? el("i", { class: `pv-acento ${t.acento}` }) : null,
          el("span", { texto: TITULO_EXEMPLO })));
      }
    } else {
      raiz.append(el("div", { class: "pv-cena" }));
    }

    const f = fonte(L.fonte);
    v("--lfonte", f.pilha); v("--lpeso", L.negrito ? 700 : f.peso); v("--lfe", f.fe);
    v("--lt", L.tamanho); v("--lcaixa", L.maiusculas ? "uppercase" : "none"); v("--le", L.espacamento);
    v("--ml", L.margem_lateral); v("--mi", L.margem_inferior);
    v("--por-falar", L.por_falar); v("--falada", L.falada);
    if (L.destaque) v("--destaque", L.destaque);
    if (L.pop > 100) v("--pop", L.pop / 100);
    v("--lc", L.contorno); v("--lcontorno", L.contorno_cor);
    v("--ls", L.sombra); v("--lsombra", rgba(L.sombra_cor, L.sombra_opacidade));
    const legenda = el("p", { class: "pv-legenda" });
    raiz.append(legenda);

    const blocos = [];
    for (let i = 0; i < FRASE.length; i += L.palavras_linha) blocos.push(FRASE.slice(i, i + L.palavras_linha));
    // Parado, mostra os tres estados de uma vez: ja falada, acesa, por falar.
    raiz._karaoke = { blocos, b: 1, w: 1, pausa: 0, L, legenda, fase };
    desenharLegenda(raiz);
    return raiz;
  }

  const letras = (palavra) => (palavra.match(/\p{L}/gu) || []).length;

  function desenharLegenda(pv) {
    const k = pv._karaoke;
    const filhos = [];
    k.blocos[k.b].forEach((palavra, i) => {
      if (i) filhos.push(" ");
      let classe = null;
      if (i < k.w) classe = "dita";
      else if (i === k.w) classe = letras(palavra) < k.L.destaque_minimo ? "agora curta" : "agora";
      filhos.push(el("span", { class: classe, texto: palavra }));
    });
    k.legenda.replaceChildren(...filhos);
    const total = k.blocos.reduce((s, b) => s + b.length, 0);
    const feitas = k.blocos.slice(0, k.b).reduce((s, b) => s + b.length, 0) + k.w;
    pv.style.setProperty("--bpos", `${Math.round(8 + (feitas / total) * 88)}%`);
  }

  // Um relogio so para todas as previas "vivas" (selecionada, sob o mouse e a
  // vitrine da entrada). ~3 palavras por segundo, o ritmo de fala comum.
  function avancar(pv) {
    const k = pv._karaoke;
    if (k.fase > 0) { k.fase--; return; }
    if (k.pausa > 0) { k.pausa--; return; }
    k.w++;
    if (k.w > k.blocos[k.b].length) {
      k.b = (k.b + 1) % k.blocos.length;
      k.w = 0;
    } else if (k.w === k.blocos[k.b].length) {
      k.pausa = 1;
    }
    desenharLegenda(pv);
  }
  setInterval(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    document.querySelectorAll(".previa.viva").forEach(avancar);
  }, 320);

  function aquietar(pv) {
    pv.classList.remove("viva");
    Object.assign(pv._karaoke, { b: 1, w: 1, pausa: 0, fase: 0 });
    desenharLegenda(pv);
  }

  // Um quadro do video escolhido, lido no proprio navegador (nada sai daqui),
  // e a duracao, que serve para conferir o saldo antes do envio.
  function lerVideo(arquivo) {
    return new Promise((pronto) => {
      const video = document.createElement("video");
      const url = URL.createObjectURL(arquivo);
      let duracao = null;
      let feito = false;
      const fim = (quadro) => {
        if (feito) return;
        feito = true;
        URL.revokeObjectURL(url);
        pronto({ duracao, quadro });
      };
      video.muted = true;
      video.preload = "auto";
      video.addEventListener("loadedmetadata", () => {
        duracao = isFinite(video.duration) ? video.duration : null;
        video.currentTime = duracao ? Math.max(0.1, Math.min(duracao * 0.25, 20)) : 0.1;
      });
      video.addEventListener("seeked", () => {
        try {
          if (!video.videoWidth) return fim(null);
          const c = document.createElement("canvas");
          c.width = 480;
          c.height = Math.round((480 * video.videoHeight) / video.videoWidth);
          c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
          fim(c.toDataURL("image/jpeg", 0.85));
        } catch (_) {
          fim(null);
        }
      });
      video.addEventListener("error", () => fim(null));
      setTimeout(() => fim(null), 10000);
      video.src = url;
    });
  }

  // ------------------------------------------------------------ inicio
  async function iniciar() {
    let cfg;
    try {
      const r = await fetch("/api/config", { cache: "no-store" });
      cfg = await r.json();
      if (!r.ok) throw new Error(cfg.erro || "");
    } catch (e) {
      const no = montar("t-config");
      if (e && e.message) $("#config-msg", no).textContent = legivel(e);
      return;
    }
    estado.compras = Boolean(cfg.compras);
    estado.sb = window.supabase.createClient(cfg.supabase_url, cfg.supabase_chave, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true, flowType: "pkce" },
    });
    estado.sb.auth.onAuthStateChange((evento, sessao) => {
      estado.sessao = sessao;
      if (evento === "PASSWORD_RECOVERY") estado.recuperando = true;
      // Fora do callback: o supabase-js trava se o callback esperar outra
      // chamada do proprio cliente (aviso da documentacao dele).
      setTimeout(rotear, 0);
    });
    $("#sair").addEventListener("click", sair);
    ligarMenuConta();
    window.addEventListener("hashchange", rotear);
  }

  function ligarMenuConta() {
    const botao = $("#conta-btn");
    const menu = $("#conta-menu");
    const abrir = (sim) => {
      menu.hidden = !sim;
      botao.setAttribute("aria-expanded", String(sim));
      if (sim) menu.querySelector("a, button").focus();
    };
    botao.addEventListener("click", () => abrir(menu.hidden));
    menu.addEventListener("click", (e) => { if (e.target.closest("a, button")) abrir(false); });
    document.addEventListener("click", (e) => { if (!menu.hidden && !e.target.closest(".conta")) abrir(false); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !menu.hidden) { abrir(false); botao.focus(); }
    });
  }

  function topo(modo) {
    // modo: "fora" (sem sessao), "beta" (logado, sem convite) ou "dentro".
    $("#topo-conta").hidden = modo === "fora";
    $("#topo-nav").hidden = modo !== "dentro";
    $("#saldo").hidden = modo !== "dentro";
    if (modo === "fora") return;
    const email = (estado.sessao && estado.sessao.user && estado.sessao.user.email) || "";
    $("#menu-email").textContent = email;
    $("#avatar-letra").textContent = (email.charAt(0) || "·").toUpperCase();
    const creditos = location.hash.startsWith("#/creditos");
    for (const [link, ativo] of [[$("#nav-projetos"), !creditos], [$("#link-creditos"), creditos]]) {
      if (ativo) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
  }

  async function rotear() {
    const vez = ++estado.vez;
    pararRolos();
    if (estado.recuperando && estado.sessao) {
      topo("fora");
      return telaNovaSenha();
    }
    if (!estado.sessao) {
      topo("fora");
      estado.saldo = null;
      return telaEntrar();
    }
    const { data, error } = await estado.sb.from("perfis").select("liberado,email").limit(1);
    if (vez !== estado.vez) return;
    if (error) {
      topo("beta");
      const no = montar("t-config");
      $("h1", no).textContent = "Não consegui abrir a sua conta.";
      $("#config-msg", no).textContent = legivel(error);
      return;
    }
    const perfil = data && data[0];
    if (!perfil || !perfil.liberado) {
      topo("beta");
      return telaBeta(perfil ? perfil.email : estado.sessao.user.email);
    }
    topo("dentro");
    atualizarSaldo();
    const m = location.hash.match(/^#\/rolo\/([0-9a-f-]{36})$/i);
    if (m) return telaTrabalho(m[1].toLowerCase(), vez);
    if (location.hash === "#/creditos") return telaCreditos(vez);
    // O Mercado Pago volta com parametros depois do hash (?payment_id=...).
    const volta = location.hash.match(/^#\/compra\/(aprovada|pendente|recusada)(?:\?(.*))?$/);
    if (volta) return telaVoltaCompra(volta[1], new URLSearchParams(volta[2] || ""), vez);
    return telaPainel(vez);
  }

  async function sair() {
    pararRolos();
    await estado.sb.auth.signOut();
    if (location.hash !== "#/") location.hash = "#/";
  }

  async function atualizarSaldo() {
    const { data, error } = await estado.sb.rpc("meu_saldo");
    if (error) return;
    const novo = Number(data) || 0;
    const caixa = $("#saldo");
    $("#saldo-tc").textContent = `${novo} min`;
    caixa.setAttribute("aria-label", `Saldo: ${novo} minutos de vídeo`);
    caixa.title = `${novo} minutos de vídeo (1 crédito = 1 minuto)`;
    if (estado.saldo !== null && novo !== estado.saldo) {
      caixa.classList.remove("mudou");
      void caixa.offsetWidth;
      caixa.classList.add("mudou");
    }
    estado.saldo = novo;
  }

  // ------------------------------------------------------------ entrar
  function telaEntrar() {
    const no = montar("t-entrar");
    const form = $("#form-conta", no);
    const aviso = $("#msg-conta", no);
    const botao = $("#enviar-conta", no);
    const abas = { entrar: $("#aba-entrar", no), criar: $("#aba-criar", no) };

    // Vitrine: tres modelos de verdade, cada um num passo do karaoke.
    const vitrine = $("#vitrine", no);
    ["cortes-editorial", "cortes", "bold-amarelo"].forEach((nome, i) => {
      const pv = previa(nome, i * 4);
      pv.classList.add("viva");
      vitrine.append(el("figure", {}, pv, el("figcaption", { texto: nomePreset(nome) })));
    });

    function modo(qual) {
      estado.modoConta = qual;
      for (const [k, b] of Object.entries(abas)) b.setAttribute("aria-selected", String(k === qual));
      botao.textContent = qual === "entrar" ? "Entrar" : "Criar conta";
      $("#senha", no).setAttribute("autocomplete", qual === "entrar" ? "current-password" : "new-password");
      $("#dica-senha", no).hidden = qual === "entrar";
      $("#esqueci", no).hidden = qual !== "entrar";
      $("#consentimento", no).hidden = qual !== "criar";
      msg(aviso, "");
    }
    abas.entrar.addEventListener("click", () => modo("entrar"));
    abas.criar.addEventListener("click", () => modo("criar"));
    modo(estado.modoConta);

    $("#google", no).addEventListener("click", async () => {
      const { error } = await estado.sb.auth.signInWithOAuth({
        provider: "google", options: { redirectTo: `${location.origin}/` },
      });
      if (error) msg(aviso, legivel(error));
    });

    $("#esqueci", no).addEventListener("click", async () => {
      const email = $("#email", no).value.trim();
      if (!email) {
        msg(aviso, "Digite o seu e-mail acima e clique de novo em “Esqueci minha senha”.");
        return $("#email", no).focus();
      }
      const { error } = await estado.sb.auth.resetPasswordForEmail(email, { redirectTo: `${location.origin}/` });
      if (error) msg(aviso, legivel(error));
      else msg(aviso, `Se houver uma conta para ${email}, o link para trocar a senha chega em instantes.`, "ok");
    });

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const campoEmail = $("#email", no);
      const email = campoEmail.value.trim();
      const senha = $("#senha", no).value;
      campoEmail.removeAttribute("aria-invalid");
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
        campoEmail.setAttribute("aria-invalid", "true");
        msg(aviso, "Digite um e-mail válido.");
        return campoEmail.focus();
      }
      if (senha.length < 8) {
        msg(aviso, "A senha precisa de pelo menos 8 caracteres.");
        return $("#senha", no).focus();
      }
      botao.disabled = true;
      msg(aviso, "");
      try {
        if (estado.modoConta === "entrar") {
          const { error } = await estado.sb.auth.signInWithPassword({ email, password: senha });
          if (error) throw error;
        } else {
          const { data, error } = await estado.sb.auth.signUp({
            email, password: senha, options: { emailRedirectTo: `${location.origin}/` },
          });
          if (error) throw error;
          if (!data.session) {
            modo("entrar");
            msg(aviso, `Quase lá: enviamos um link para ${email}. Confirme o e-mail e depois entre aqui.`, "ok");
          }
        }
      } catch (e) {
        msg(aviso, legivel(e));
      } finally {
        botao.disabled = false;
      }
    });
    $("#email", no).focus();
  }

  function telaNovaSenha() {
    const no = montar("t-nova-senha");
    const aviso = $("#msg-nova-senha", no);
    $("#form-nova-senha", no).addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const senha = $("#nova-senha", no).value;
      if (senha.length < 8) return msg(aviso, "A senha precisa de pelo menos 8 caracteres.");
      const { error } = await estado.sb.auth.updateUser({ password: senha });
      if (error) return msg(aviso, legivel(error));
      estado.recuperando = false;
      avisar("Senha trocada. Pode seguir.");
      rotear();
    });
    $("#nova-senha", no).focus();
  }

  function telaBeta(email) {
    const no = montar("t-beta");
    $("#beta-email", no).textContent = email || "";
    $("#beta-atualizar", no).addEventListener("click", rotear);
  }

  // ------------------------------------------------------------ painel
  function telaPainel(vez) {
    const no = montar("t-painel");
    const form = $("#form-novo", no);
    const aviso = $("#msg-novo", no);
    estado.via = "link";
    estado.arquivo = null;
    estado.duracaoArquivo = null;
    estado.quadro = null;

    // Galeria de modelos: a previa da escolhida e a sob o mouse ficam vivas.
    const grade = $("#visuais", no);
    PRESETS.forEach((p, i) => {
      const pv = previa(p.nome);
      grade.append(el("label", { class: "visual", "data-modelo": p.nome },
        el("input", { type: "radio", name: "preset", value: p.nome, checked: i === 0 }),
        el("span", { class: "visual-quadro" }, pv, el("span", { class: "visual-check", "aria-hidden": "true" }, icone("check", 14))),
        el("span", { class: "visual-linha" },
          el("span", { class: "visual-nome", texto: p.titulo }),
          el("span", { class: "visual-tag", texto: p.tag })),
        el("span", { class: "visual-desc", texto: p.desc })));
    });
    function vivas() {
      grade.querySelectorAll(".visual").forEach((rotulo) => {
        const pv = $(".previa", rotulo);
        const ligada = $("input", rotulo).checked || rotulo.matches(":hover");
        if (ligada && !pv.classList.contains("viva")) pv.classList.add("viva");
        else if (!ligada && pv.classList.contains("viva")) aquietar(pv);
      });
    }
    grade.addEventListener("change", vivas);
    grade.addEventListener("mouseover", vivas);
    grade.addEventListener("mouseleave", vivas);
    vivas();

    function mostrarQuadro() {
      const usar = estado.via === "arquivo" && estado.quadro;
      if (usar) grade.style.setProperty("--quadro", `url("${estado.quadro}")`);
      else grade.style.removeProperty("--quadro");
      $("#modelos-nota", no).textContent = usar
        ? "Prévias com um quadro do seu vídeo e as medidas reais de cada modelo."
        : "Prévias com as medidas reais de cada modelo. Escolha um arquivo para vê-las com o seu vídeo.";
    }

    // Link | Arquivo
    const vias = { link: $("#via-link", no), arquivo: $("#via-arquivo", no) };
    function via(qual) {
      estado.via = qual;
      for (const [k, b] of Object.entries(vias)) b.setAttribute("aria-selected", String(k === qual));
      $("#painel-link", no).hidden = qual !== "link";
      $("#painel-arquivo", no).hidden = qual !== "arquivo";
      msg(aviso, "");
      mostrarQuadro();
    }
    vias.link.addEventListener("click", () => via("link"));
    vias.arquivo.addEventListener("click", () => via("arquivo"));

    // Arquivo: escolher ou arrastar
    const entradaArquivo = $("#arquivo", no);
    const soltar = $("#soltar", no);
    const info = $("#arquivo-info", no);
    async function escolher(arquivo) {
      estado.arquivo = null;
      estado.duracaoArquivo = null;
      estado.quadro = null;
      mostrarQuadro();
      info.hidden = true;
      if (!arquivo) return;
      const nome = arquivo.name.toLowerCase();
      if (!EXTENSOES.some((e) => nome.endsWith(e))) {
        return msg(aviso, "Escolha um arquivo de vídeo (mp4, mov, mkv, webm, m4v ou avi).");
      }
      if (arquivo.size > LIMITE_ARQUIVO) {
        return msg(aviso, `Este arquivo tem ${tamanhoLegivel(arquivo.size)}; o limite é 2 GB. Envie um trecho menor.`);
      }
      msg(aviso, "");
      estado.arquivo = arquivo;
      info.textContent = `${arquivo.name} · ${tamanhoLegivel(arquivo.size)}`;
      info.hidden = false;
      const { duracao, quadro } = await lerVideo(arquivo);
      if (estado.arquivo !== arquivo) return;
      estado.duracaoArquivo = duracao;
      estado.quadro = quadro;
      mostrarQuadro();
      if (duracao) info.textContent = `${arquivo.name} · ${tamanhoLegivel(arquivo.size)} · ${relogio(duracao)}`;
    }
    entradaArquivo.addEventListener("change", () => escolher(entradaArquivo.files[0]));
    for (const ev of ["dragenter", "dragover"]) soltar.addEventListener(ev, (e) => { e.preventDefault(); soltar.classList.add("arrastando"); });
    for (const ev of ["dragleave", "drop"]) soltar.addEventListener(ev, () => soltar.classList.remove("arrastando"));
    soltar.addEventListener("drop", (e) => { e.preventDefault(); escolher(e.dataTransfer.files[0]); });

    // Contador de clipes
    const campoN = $("#n", no);
    function limitarN() { campoN.value = String(Math.min(N_MAX, Math.max(1, parseInt(campoN.value, 10) || 5))); }
    no.querySelectorAll(".contador-btn").forEach((b) => b.addEventListener("click", () => {
      campoN.value = String((parseInt(campoN.value, 10) || 5) + Number(b.dataset.passo));
      limitarN();
    }));
    campoN.addEventListener("change", limitarN);

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      msg(aviso, "");
      limitarN();
      const preset = (form.querySelector("input[name=preset]:checked") || {}).value || "cortes";
      const estrategia = $("#estrategia", no).value.trim() || null;
      let entrada = null;
      if (estado.via === "link") {
        const campo = $("#link", no);
        const link = campo.value.trim();
        campo.removeAttribute("aria-invalid");
        if (!/^https?:\/\/[^\s/$.?#][^\s]*$/i.test(link)) {
          campo.setAttribute("aria-invalid", "true");
          msg(aviso, "Cole o link completo do vídeo, começando com https://.");
          return campo.focus();
        }
        entrada = { tipo: "link", valor: link };
      } else if (!estado.arquivo) {
        return msg(aviso, "Escolha o arquivo de vídeo.");
      } else if (estado.duracaoArquivo && estado.saldo !== null
                 && Math.ceil(estado.duracaoArquivo / 60) > estado.saldo) {
        return msg(aviso, `Este vídeo tem ${Math.ceil(estado.duracaoArquivo / 60)} min e o seu saldo é de ${estado.saldo} min.`);
      }
      if (estado.saldo !== null && estado.saldo < 1) return msg(aviso, "Seus créditos acabaram.");

      const botao = $("#gerar", no);
      botao.disabled = true;
      try {
        if (!entrada) {
          botao.textContent = "Enviando o vídeo…";
          entrada = { tipo: "arquivo", valor: await enviarArquivo(estado.arquivo, no) };
        }
        botao.textContent = "Colocando na fila…";
        const { error } = await estado.sb.rpc("criar_trabalho", {
          p_entrada: entrada, p_n: parseInt(campoN.value, 10), p_preset: preset, p_estrategia: estrategia,
        });
        if (error) throw error;
        avisar("Vídeo na fila. Os clipes aparecem em Projetos quando ficarem prontos.");
        $("#link", no).value = "";
        estado.arquivo = null;
        estado.quadro = null;
        mostrarQuadro();
        info.hidden = true;
        $("#progresso", no).hidden = true;
        await Promise.all([carregarRolos(vez), atualizarSaldo()]);
      } catch (e) {
        msg(aviso, legivel(e));
      } finally {
        botao.disabled = false;
        botao.textContent = "Gerar clipes";
      }
    });

    carregarRolos(vez);
  }

  async function enviarArquivo(arquivo, no) {
    const r = await fetch("/api/upload", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${await token()}` },
      body: JSON.stringify({ nome: arquivo.name, tamanho: arquivo.size, tipo: arquivo.type }),
    });
    const dados = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(dados.erro || "Não consegui preparar o envio do vídeo.");
    const caixa = $("#progresso", no);
    const barra = $("#progresso-barra", no);
    const texto = $("#progresso-txt", no);
    caixa.hidden = false;
    await new Promise((pronto, falha) => {
      const x = new XMLHttpRequest();
      x.open("PUT", dados.url);
      x.upload.addEventListener("progress", (e) => {
        if (!e.lengthComputable) return;
        const p = Math.round((e.loaded / e.total) * 100);
        barra.style.width = `${p}%`;
        texto.textContent = `${p}%`;
      });
      x.addEventListener("load", () => (x.status >= 200 && x.status < 300
        ? pronto() : falha(new Error(`O envio do vídeo foi recusado (HTTP ${x.status}). Tente de novo.`))));
      x.addEventListener("error", () => falha(new Error("O envio do vídeo caiu. Confira a internet e tente de novo.")));
      x.send(arquivo);
    });
    return dados.chave;
  }

  function origem(t) {
    const e = (t.pedido && t.pedido.entrada) || {};
    if (e.tipo !== "link") return "Vídeo enviado";
    try {
      const u = new URL(e.valor);
      return `${u.hostname.replace(/^www\./, "")}${u.pathname}${u.search}`;
    } catch (_) {
      return String(e.valor || "");
    }
  }

  function itemRolo(t) {
    const r = t.resultado || {};
    const clipes = r.clipes || [];
    const falhou = t.status === "falhou" || t.status === "recusado";
    const titulo = t.status === "concluido" && clipes.length ? (clipes[0].titulo || "Clipes prontos") : origem(t);
    const meta = [quando(t.criado_em), nomePreset(t.pedido && t.pedido.preset)];
    if (t.status === "concluido") meta.push(`${clipes.length} clipes`, `${r.creditos || 0} créditos`);
    else meta.push(`${(t.pedido && t.pedido.n) || "?"} clipes pedidos`);
    if (falhou) meta.push("créditos devolvidos");
    return el("li", {},
      el("a", { class: "rolo", href: `#/rolo/${t.id}`, "data-status": t.status },
        el("span", { class: "rolo-icone", "aria-hidden": "true" }, icone(ICONE_STATUS[t.status] || "relogio", 18)),
        el("span", { class: "rolo-titulo", texto: titulo }),
        el("span", { class: `chip ${t.status}`, texto: ROTULOS[t.status] || t.status }),
        el("span", { class: "rolo-meta", texto: meta.join(" · ") }),
        falhou && r.erro && r.erro.mensagem ? el("span", { class: "rolo-meta erro-txt", texto: r.erro.mensagem }) : null));
  }

  async function carregarRolos(vez) {
    const { data, error } = await estado.sb.from("trabalhos")
      .select("id,status,pedido,resultado,criado_em")
      .order("criado_em", { ascending: false }).limit(30);
    if (vez !== estado.vez) return;
    const lista = $("#lista-rolos");
    if (!lista) return;
    if (error) return msg($("#msg-novo"), legivel(error));
    lista.replaceChildren(...data.map(itemRolo));
    $("#rolos-vazio").hidden = data.length > 0;
    const ativos = data.some((t) => t.status === "pendente" || t.status === "em_curso");
    $("#rolos-auto").hidden = !ativos;
    pararRolos();
    if (ativos) {
      estado.timer = setTimeout(() => { carregarRolos(vez); atualizarSaldo(); }, INTERVALO_MS);
    }
  }

  // ------------------------------------------------------------ trabalho
  function etapas(status) {
    const ordem = ["pendente", "em_curso", "concluido"];
    const i = ordem.indexOf(status);
    return el("ol", { class: "etapas", "aria-label": "Etapas" },
      ...ordem.map((s, j) => el("li", { class: j < i ? "feita" : j === i ? "agora" : null,
                                         "aria-current": j === i ? "step" : null, texto: ROTULOS[s] })));
  }

  async function telaTrabalho(id, vez) {
    const no = montar("t-trabalho");
    const corpo = $("#tr-corpo", no);
    const { data, error } = await estado.sb.from("trabalhos")
      .select("id,status,pedido,resultado,criado_em").eq("id", id).limit(1);
    if (vez !== estado.vez) return;
    if (error || !data || !data.length) {
      $("#tr-titulo", no).textContent = "Projeto não encontrado";
      corpo.replaceChildren(el("div", { class: "espera" },
        el("p", { texto: "Este projeto não existe ou não é da sua conta." })));
      return;
    }
    const t = data[0];
    const r = t.resultado || {};
    $("#tr-quando", no).textContent = `Pedido ${quando(t.criado_em)} · Modelo ${nomePreset(t.pedido && t.pedido.preset)}`;
    $("#tr-origem", no).textContent = origem(t);
    const chip = $("#tr-status", no);
    chip.className = `chip ${t.status}`;
    chip.textContent = ROTULOS[t.status] || t.status;

    if (t.status === "pendente" || t.status === "em_curso") {
      $("#tr-titulo", no).textContent = t.status === "pendente" ? "Na fila" : "Processando";
      corpo.replaceChildren(el("div", { class: "espera" },
        etapas(t.status),
        el("span", { class: "giro", "aria-hidden": "true" }),
        el("p", { texto: t.status === "pendente"
          ? "O vídeo está na fila. O processamento começa em instantes."
          : "Transcrevendo, escolhendo os melhores trechos e renderizando. Um vídeo de 1 hora leva perto de 50 minutos." }),
        el("p", { class: "dica", texto: "Pode fechar esta página: os clipes ficam guardados na sua conta." })));
      estado.timer = setTimeout(async () => {
        if (vez !== estado.vez) return;
        const { data: d } = await estado.sb.from("trabalhos").select("status").eq("id", id).limit(1);
        if (vez === estado.vez && d && d[0] && d[0].status !== t.status) rotear();
        else if (vez === estado.vez) telaTrabalhoEspera(id, vez, t.status);
      }, INTERVALO_MS);
      return;
    }
    if (t.status !== "concluido") {
      $("#tr-titulo", no).textContent = t.status === "recusado" ? "Pedido recusado" : "Não deu certo";
      corpo.replaceChildren(el("div", { class: "espera" },
        el("p", { texto: (r.erro && r.erro.mensagem) || "O processamento deste vídeo falhou." }),
        r.erro && r.erro.sugestao ? el("p", { class: "dica", texto: r.erro.sugestao }) : null,
        el("p", { texto: "Os minutos reservados voltaram para o seu saldo." }),
        el("a", { class: "btn primario", href: "#/", texto: "Tentar outro vídeo" })));
      return;
    }

    $("#tr-titulo", no).textContent = `${(r.clipes || []).length} clipes prontos`;
    corpo.replaceChildren(el("div", { class: "carregando" }, el("span", { class: "giro", "aria-hidden": "true" }), "Buscando os clipes…"));
    let dados;
    try {
      const resp = await fetch(`/api/clipes?trabalho=${encodeURIComponent(id)}`, {
        headers: { Authorization: `Bearer ${await token()}` }, cache: "no-store",
      });
      dados = await resp.json();
      if (!resp.ok) throw new Error(dados.erro || "");
    } catch (e) {
      if (vez !== estado.vez) return;
      corpo.replaceChildren(el("div", { class: "espera" }, el("p", { texto: legivel(e) })));
      return;
    }
    if (vez !== estado.vez) return;
    $("#tr-titulo", no).textContent = `${dados.clipes.length} clipes prontos`;
    // Os clipes ficam 30 dias no deposito (regra de ciclo de vida do R2 e
    // Politica de privacidade, secao 4).
    const ate = new Date(new Date(t.criado_em).getTime() + 30 * 86400000);
    corpo.replaceChildren(
      el("p", { class: "dica validade", texto: `Disponíveis até ${ate.toLocaleDateString("pt-BR", { day: "2-digit", month: "long" })}. Baixe o que quiser guardar.` }),
      el("div", { class: "grade-clipes" }, ...dados.clipes.map(cartaoClipe)));
  }

  // Polling da tela de espera sem remontar a tela (nada pisca).
  function telaTrabalhoEspera(id, vez, statusAtual) {
    estado.timer = setTimeout(async () => {
      if (vez !== estado.vez) return;
      const { data } = await estado.sb.from("trabalhos").select("status").eq("id", id).limit(1);
      if (vez !== estado.vez) return;
      if (data && data[0] && data[0].status !== statusAtual) rotear();
      else telaTrabalhoEspera(id, vez, statusAtual);
    }, INTERVALO_MS);
  }

  function cartaoClipe(c, i) {
    const video = el("video", {
      controls: true, preload: "none", playsinline: true, poster: c.capa || null, src: c.ver,
      "aria-label": `Clipe ${i + 1}: ${c.titulo || ""}`,
    });
    const acoes = el("div", { class: "clipe-acoes" },
      el("a", { class: "btn primario pequeno", href: c.baixar }, icone("baixar"), "Baixar"));
    if (c.gancho) {
      acoes.append(el("button", { class: "btn secundario pequeno", type: "button",
        onclick: async () => { await copiar(c.gancho); avisar("Gancho copiado."); } }, icone("copiar", 14), "Copiar gancho"));
    }
    if (c.publicacao) {
      acoes.append(el("button", { class: "btn secundario pequeno", type: "button", title: "Copia a legenda pronta para a publicação",
        onclick: async () => {
          try {
            const r = await fetch(c.publicacao);
            if (!r.ok) throw new Error();
            await copiar(await r.text());
            avisar("Texto de publicação copiado.");
          } catch (_) {
            avisar("Não consegui buscar o texto de publicação agora.");
          }
        } }, icone("copiar", 14), "Copiar legenda"));
    }
    const temNota = c.score !== null && c.score !== undefined;
    return el("article", { class: "clipe" },
      el("div", { class: "clipe-quadro" }, video),
      el("div", { class: "clipe-corpo" },
        el("div", { class: "clipe-linha" },
          el("span", { texto: `Clipe ${i + 1}` }),
          c.duracao ? el("span", { texto: relogio(c.duracao) }) : null,
          temNota ? el("span", { class: "clipe-nota", title: "Nota de 0 a 10 dada na escolha do trecho" },
            "Nota ", el("b", { texto: Number(c.score).toFixed(1).replace(".", ",") })) : null),
        el("h3", { class: "clipe-titulo", texto: c.titulo || `Clipe ${i + 1}` }),
        c.gancho ? el("p", { class: "clipe-gancho" }, el("span", { texto: "Gancho" }), c.gancho) : null,
        acoes));
  }

  // ------------------------------------------------------------ creditos
  function reais(centavos) {
    return (centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  async function telaCreditos(vez) {
    const no = montar("t-creditos");
    const aviso = $("#msg-pacotes", no);
    const [saldo, pacotes, extrato] = await Promise.all([
      estado.sb.rpc("meu_saldo"),
      estado.compras
        ? estado.sb.from("pacotes").select("id,nome,minutos,preco_centavos").order("ordem")
        : Promise.resolve({ data: [] }),
      estado.sb.from("movimentos").select("delta,motivo,criado_em")
        .order("criado_em", { ascending: false }).limit(50),
    ]);
    if (vez !== estado.vez) return;
    $("#cr-saldo", no).textContent = String(Number(saldo.data) || 0);

    const lista = (pacotes && pacotes.data) || [];
    $("#pacotes-fechado", no).hidden = estado.compras && lista.length > 0;
    $("#pacotes-nota", no).hidden = !(estado.compras && lista.length > 0);
    $("#pacotes", no).replaceChildren(...lista.map((p) => el("article", { class: "pacote" },
      el("p", { class: "pacote-nome", texto: p.nome }),
      el("p", { class: "pacote-min", texto: String(p.minutos) }, el("small", { texto: "minutos" })),
      el("p", { class: "pacote-preco", texto: reais(p.preco_centavos) },
        el("small", { texto: `${reais(p.preco_centavos / p.minutos)} por minuto de vídeo` })),
      el("button", { class: "btn primario", type: "button", "data-pacote": p.id, texto: "Comprar",
        onclick: (ev) => comprar(p.id, ev.currentTarget, aviso) }))));

    const itens = (extrato && extrato.data) || [];
    $("#extrato", no).replaceChildren(...(itens.length ? itens.map((m) => el("li", {},
      el("span", { class: "extrato-motivo", texto: MOTIVOS[m.motivo] || m.motivo }),
      el("span", { class: "extrato-quando", texto: new Date(m.criado_em).toLocaleString("pt-BR",
        { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) }),
      el("span", { class: `extrato-delta ${m.delta >= 0 ? "mais" : "menos"}`,
        texto: `${m.delta >= 0 ? "+" : "−"}${Math.abs(m.delta)} min` })))
      : [el("li", {}, el("span", { class: "extrato-quando", texto: "Nada por aqui ainda." }))]));
  }

  async function comprar(pacote, botao, aviso) {
    botao.disabled = true;
    botao.textContent = "Abrindo o Mercado Pago…";
    msg(aviso, "");
    try {
      const r = await fetch("/api/comprar", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${await token()}` },
        body: JSON.stringify({ pacote }),
      });
      const dados = await r.json().catch(() => ({}));
      if (!r.ok || !dados.url) throw new Error(dados.erro || "Não consegui abrir o pagamento.");
      location.href = dados.url;
    } catch (e) {
      msg(aviso, legivel(e));
      botao.disabled = false;
      botao.textContent = "Comprar";
    }
  }

  function telaVoltaCompra(tipo, params, vez) {
    const no = montar("t-compra");
    const titulo = $("#cp-titulo", no);
    const texto = $("#cp-texto", no);
    if (tipo === "recusada") {
      titulo.textContent = "Pagamento não concluído";
      texto.textContent = "Nada foi cobrado. Você pode tentar de novo em Créditos.";
      return;
    }
    titulo.textContent = tipo === "aprovada" ? "Pagamento aprovado" : "Pagamento em processamento";
    texto.textContent = tipo === "aprovada"
      ? "Conferindo com o Mercado Pago… os minutos entram em segundos."
      : "Pix ou boleto ainda não compensou. Os minutos entram sozinhos quando o Mercado Pago aprovar; pode fechar esta página.";
    const compra = params.get("external_reference") || "";
    if (!/^[0-9a-f-]{36}$/i.test(compra)) return;
    let tentativas = 0;
    const conferir = async () => {
      if (vez !== estado.vez) return;
      const { data } = await estado.sb.from("compras").select("status,minutos").eq("id", compra).limit(1);
      if (vez !== estado.vez) return;
      const c = data && data[0];
      if (c && c.status === "aprovada") {
        titulo.textContent = "Minutos na conta";
        texto.textContent = `Pronto: ${c.minutos} minutos entraram no seu saldo.`;
        await atualizarSaldo();
        $("#cp-saldo", no).textContent = String(estado.saldo);
        $("#cp-saldo-caixa", no).hidden = false;
        return;
      }
      if (c && c.status === "recusada") {
        titulo.textContent = "Pagamento não aprovado";
        texto.textContent = "O Mercado Pago recusou o pagamento. Nada foi cobrado.";
        return;
      }
      if (++tentativas < 40) estado.timer = setTimeout(conferir, 3000);
      else texto.textContent = "Ainda não recebemos a confirmação. Os minutos entram sozinhos quando ela chegar.";
    };
    conferir();
  }

  iniciar();
})();
