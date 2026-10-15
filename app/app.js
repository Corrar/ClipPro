/* ClipPro, app na nuvem (N-2, RULINGS §29.3).
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
  const PRESETS = [
    { nome: "cortes", titulo: "Cortes", mini: "cortes", palavra: "Corta",
      desc: "Fundo borrado, cartão central, pílula de título e karaokê palavra a palavra." },
    { nome: "cortes-editorial", titulo: "Editorial", mini: "editorial", palavra: "Corta",
      desc: "O mesmo cartão com acabamento contido: âmbar e legenda em caixa mista." },
    { nome: "bold-amarelo", titulo: "Bold", mini: "bold", palavra: "Corta",
      desc: "Legenda grossa; a palavra falada acende em amarelo. Lê em qualquer fundo." },
    { nome: "clean-branco", titulo: "Clean", mini: "clean", palavra: "Corta",
      desc: "Negrito branco com contorno fino, para vídeo que já tem muita informação." },
  ];
  const ROTULOS = { pendente: "Na fila", em_curso: "Processando", concluido: "Pronto",
                    falhou: "Falhou", recusado: "Recusado" };
  const PASSO = { pendente: 1, em_curso: 2, concluido: 3 };
  const EXTENSOES = [".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"];
  const LIMITE_ARQUIVO = 2 * 1024 ** 3;
  const N_MAX = 10;
  const INTERVALO_MS = 8000;

  const MOTIVOS = { cadastro: "Bônus de boas-vindas", reserva: "Reserva para um vídeo",
                    devolucao: "Devolução do que sobrou", compra: "Compra de créditos", ajuste: "Ajuste" };
  const estado = {
    sb: null, sessao: null, saldo: null, vez: 0, timer: null, recuperando: false, compras: false,
    modoConta: "entrar", via: "link", arquivo: null, duracaoArquivo: null,
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
    window.addEventListener("hashchange", rotear);
  }

  async function rotear() {
    const vez = ++estado.vez;
    pararRolos();
    const conta = $("#topo-conta");
    if (estado.recuperando && estado.sessao) {
      conta.hidden = true;
      return telaNovaSenha();
    }
    if (!estado.sessao) {
      conta.hidden = true;
      estado.saldo = null;
      return telaEntrar();
    }
    conta.hidden = false;
    const { data, error } = await estado.sb.from("perfis").select("liberado,email").limit(1);
    if (vez !== estado.vez) return;
    if (error) {
      const no = montar("t-config");
      $("h1", no).textContent = "Não consegui abrir a sua conta.";
      $("#config-msg", no).textContent = legivel(error);
      return;
    }
    const perfil = data && data[0];
    if (!perfil || !perfil.liberado) return telaBeta(perfil ? perfil.email : estado.sessao.user.email);
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

    const grade = $("#visuais", no);
    PRESETS.forEach((p, i) => {
      grade.append(el("label", { class: "visual", title: p.desc },
        el("input", { type: "radio", name: "preset", value: p.nome, checked: i === 0 }),
        el("span", { class: `mini mini-${p.mini}`, "data-palavra": p.palavra, "aria-hidden": "true" }),
        el("span", { class: "visual-nome", texto: p.titulo })));
    });

    // Link | Arquivo
    const vias = { link: $("#via-link", no), arquivo: $("#via-arquivo", no) };
    function via(qual) {
      estado.via = qual;
      for (const [k, b] of Object.entries(vias)) b.setAttribute("aria-selected", String(k === qual));
      $("#painel-link", no).hidden = qual !== "link";
      $("#painel-arquivo", no).hidden = qual !== "arquivo";
      msg(aviso, "");
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
      const duracao = await lerDuracao(arquivo);
      if (estado.arquivo !== arquivo) return;
      estado.duracaoArquivo = duracao;
      if (duracao) info.textContent = `${arquivo.name} · ${tamanhoLegivel(arquivo.size)} · ${Math.ceil(duracao / 60)} min`;
    }
    entradaArquivo.addEventListener("change", () => escolher(entradaArquivo.files[0]));
    for (const ev of ["dragenter", "dragover"]) soltar.addEventListener(ev, (e) => { e.preventDefault(); soltar.classList.add("arrastando"); });
    for (const ev of ["dragleave", "drop"]) soltar.addEventListener(ev, () => soltar.classList.remove("arrastando"));
    soltar.addEventListener("drop", (e) => { e.preventDefault(); escolher(e.dataTransfer.files[0]); });

    // Contador de cortes
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
        form.classList.remove("bate");
        void form.offsetWidth;
        form.classList.add("bate");
        avisar("Vídeo na fila. Os cortes aparecem em “Seus rolos” quando ficarem prontos.");
        $("#link", no).value = "";
        estado.arquivo = null;
        info.hidden = true;
        $("#progresso", no).hidden = true;
        await Promise.all([carregarRolos(vez), atualizarSaldo()]);
      } catch (e) {
        msg(aviso, legivel(e));
      } finally {
        botao.disabled = false;
        botao.textContent = "Gerar cortes";
      }
    });

    carregarRolos(vez);
  }

  function lerDuracao(arquivo) {
    return new Promise((pronto) => {
      const video = document.createElement("video");
      const url = URL.createObjectURL(arquivo);
      let feito = false;
      const fim = (d) => {
        if (feito) return;
        feito = true;
        URL.revokeObjectURL(url);
        pronto(d);
      };
      video.preload = "metadata";
      video.addEventListener("loadedmetadata", () => fim(isFinite(video.duration) ? video.duration : null));
      video.addEventListener("error", () => fim(null));
      setTimeout(() => fim(null), 8000);
      video.src = url;
    });
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

  function regua(status) {
    const passo = PASSO[status];
    const falhou = status === "falhou" || status === "recusado";
    return el("div", { class: `regua${falhou ? " falhou" : ""}`, "aria-hidden": "true" },
      ...[1, 2, 3].map((i) => el("span", {
        class: status === "concluido" || i < passo ? "feito" : i === passo ? "agora" : null,
      })));
  }

  function itemRolo(t) {
    const r = t.resultado || {};
    const clipes = r.clipes || [];
    const falhou = t.status === "falhou" || t.status === "recusado";
    const titulo = t.status === "concluido" && clipes.length ? (clipes[0].titulo || "Cortes prontos") : origem(t);
    const meta = [quando(t.criado_em), `${(t.pedido && t.pedido.n) || "?"} cortes`, nomePreset(t.pedido && t.pedido.preset)];
    if (t.status === "concluido") meta.push(`${clipes.length} prontos · ${r.creditos || 0} créditos`);
    if (falhou) meta.push("créditos devolvidos");
    return el("li", {},
      el("a", { class: "rolo", href: `#/rolo/${t.id}`, "data-status": t.status },
        el("div", {},
          el("div", { class: "rolo-titulo", texto: titulo }),
          el("div", { class: "rolo-meta", texto: meta.join(" · ") }),
          falhou && r.erro && r.erro.mensagem ? el("div", { class: "rolo-meta erro-txt", texto: r.erro.mensagem }) : null),
        el("span", { class: `chip ${t.status}`, texto: ROTULOS[t.status] || t.status }),
        regua(t.status)));
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
    $("#cena-n").textContent = String(data.length + 1).padStart(2, "0");
    const ativos = data.some((t) => t.status === "pendente" || t.status === "em_curso");
    $("#rolos-auto").hidden = !ativos;
    pararRolos();
    if (ativos) {
      estado.timer = setTimeout(() => { carregarRolos(vez); atualizarSaldo(); }, INTERVALO_MS);
    }
  }

  // ------------------------------------------------------------ trabalho
  async function telaTrabalho(id, vez) {
    const no = montar("t-trabalho");
    const corpo = $("#tr-corpo", no);
    const { data, error } = await estado.sb.from("trabalhos")
      .select("id,status,pedido,resultado,criado_em").eq("id", id).limit(1);
    if (vez !== estado.vez) return;
    if (error || !data || !data.length) {
      $("#tr-titulo", no).textContent = "Rolo não encontrado";
      corpo.replaceChildren(el("div", { class: "espera" },
        el("p", { texto: "Este rolo não existe ou não é da sua conta." })));
      return;
    }
    const t = data[0];
    const r = t.resultado || {};
    $("#tr-quando", no).textContent = `Pedido ${quando(t.criado_em)} · ${nomePreset(t.pedido && t.pedido.preset)}`;
    $("#tr-origem", no).textContent = origem(t);
    const chip = $("#tr-status", no);
    chip.className = `chip ${t.status}`;
    chip.textContent = ROTULOS[t.status] || t.status;

    if (t.status === "pendente" || t.status === "em_curso") {
      $("#tr-titulo", no).textContent = t.status === "pendente" ? "Na fila" : "Cortando";
      corpo.replaceChildren(el("div", { class: "espera" },
        el("span", { class: "playhead", "aria-hidden": "true" }),
        el("p", { texto: t.status === "pendente"
          ? "O vídeo está na fila. Assim que a ilha de edição pegar, começa o corte."
          : "Transcrevendo, escolhendo os melhores trechos e renderizando. Um vídeo de 1 hora leva perto de 50 minutos." }),
        el("p", { class: "dica", texto: "Pode fechar esta página: os cortes ficam guardados na sua conta." })));
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

    $("#tr-titulo", no).textContent = `${(r.clipes || []).length} cortes prontos`;
    corpo.replaceChildren(el("div", { class: "carregando" }, el("span", { class: "playhead", "aria-hidden": "true" }), "Buscando os clipes…"));
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
    $("#tr-titulo", no).textContent = `${dados.clipes.length} cortes prontos`;
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
    const nota = c.score === null || c.score === undefined ? null
      : el("span", { class: "clipe-nota", title: "Nota da IA, de 0 a 10", texto: Number(c.score).toFixed(1).replace(".", ",") });
    const video = el("video", {
      controls: true, preload: "none", playsinline: true, poster: c.capa || null, src: c.ver,
      "aria-label": `Clipe ${i + 1}: ${c.titulo || ""}`,
    });
    const acoes = el("div", { class: "clipe-acoes" },
      el("a", { class: "btn primario pequeno", href: c.baixar, texto: "Baixar" }));
    if (c.gancho) {
      acoes.append(el("button", { class: "btn fantasma pequeno", type: "button", texto: "Copiar gancho",
        onclick: async () => { await copiar(c.gancho); avisar("Gancho copiado."); } }));
    }
    if (c.publicacao) {
      acoes.append(el("button", { class: "btn fantasma pequeno", type: "button", texto: "Copiar legenda do post",
        onclick: async () => {
          try {
            const r = await fetch(c.publicacao);
            if (!r.ok) throw new Error();
            await copiar(await r.text());
            avisar("Texto de publicação copiado.");
          } catch (_) {
            avisar("Não consegui buscar o texto de publicação agora.");
          }
        } }));
    }
    const duracao = c.duracao ? `${Math.round(c.duracao)} s` : "";
    return el("article", { class: "clipe" },
      el("div", { class: "clipe-quadro" }, nota, video),
      el("h3", { class: "clipe-titulo", texto: c.titulo || `Clipe ${i + 1}` }),
      duracao ? el("p", { class: "clipe-meta", texto: `Clipe ${i + 1} · ${duracao}` }) : null,
      c.gancho ? el("p", { class: "clipe-gancho", texto: c.gancho }) : null,
      acoes);
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
    $("#pacotes", no).replaceChildren(...lista.map((p) => el("article", { class: "ingresso" },
      el("p", { class: "ingresso-nome", texto: p.nome }),
      el("p", { class: "ingresso-min", texto: String(p.minutos) }, el("small", { texto: "minutos" })),
      el("p", { class: "ingresso-preco", texto: reais(p.preco_centavos) },
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
