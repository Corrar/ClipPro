/* ClipPro - painel local, JS sem dependencia e sem build.
 *
 * Duas telas e um roteador de uma linha (a hash da URL). O estado vem do
 * servidor: a tela do job desenha o que chega por SSE, e o unico "estado" que
 * o navegador guarda e a conexao aberta.
 */

const tela = document.getElementById("tela");
let fonteEventos = null;   // EventSource da tela do job (fechada ao trocar de rota)
let padroes = {};

// ------------------------------------------------------------------ utilidades

const $ = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

function modelo(id) {
  return document.getElementById(id).content.cloneNode(true);
}

async function api(caminho, opcoes = {}) {
  const resposta = await fetch(caminho, opcoes);
  const tipo = resposta.headers.get("content-type") || "";
  const corpo = tipo.includes("json") ? await resposta.json() : await resposta.text();
  if (!resposta.ok) {
    const erro = new Error((corpo && corpo.detail && corpo.detail.mensagem) || (corpo && corpo.mensagem) || "falhou");
    erro.dados = (corpo && corpo.detail) || corpo || {};
    erro.status = resposta.status;
    throw erro;
  }
  return corpo;
}

function tempoCurto(segundos) {
  const s = Math.max(0, Math.round(segundos || 0));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")}m`;
}

function bytesCurto(n) {
  if (!n) return "";
  const mb = n / 1048576;
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb.toFixed(0)} MB`;
}

const ROTULO_STATUS = {
  na_fila: "na fila",
  rodando: "rodando",
  aguardando_resposta: "aguardando você",
  concluido: "pronto",
  erro: "erro",
};

// ------------------------------------------------------------------ roteador

function rota() {
  return location.hash.replace(/^#\/?/, "");
}

async function desenhar() {
  if (fonteEventos) { fonteEventos.close(); fonteEventos = null; }
  const alvo = rota();
  tela.innerHTML = "";
  if (alvo.startsWith("job/")) {
    await telaJob(alvo.slice(4));
  } else {
    await telaHome();
  }
}

window.addEventListener("hashchange", desenhar);

// ------------------------------------------------------------------ home

async function telaHome() {
  tela.appendChild(modelo("tpl-home"));

  padroes = await api("/api/padroes");
  $("#estrategia").value = padroes.estrategia;
  $("#n").value = padroes.n;
  $("#preset").innerHTML = padroes.presets
    .map((p) => `<option value="${escapar(p)}"${p === padroes.preset ? " selected" : ""}>${escapar(p)}</option>`)
    .join("");
  $("#modelo_whisper").innerHTML = padroes.modelos_whisper
    .map((m) => `<option value="${escapar(m)}"${m === padroes.modelo_whisper ? " selected" : ""}>${escapar(m)}</option>`)
    .join("");
  $("#dica-api").textContent = padroes.tem_chave_api
    ? "com ANTHROPIC_API_KEY: a escolha dos cortes é automática"
    : "sem chave de API: você vai colar o prompt num chat (modo manual)";

  // arrastar e soltar
  const solta = $("#solta");
  const entrada = $("#arquivo");
  ["dragenter", "dragover"].forEach((ev) =>
    solta.addEventListener(ev, (e) => { e.preventDefault(); solta.classList.add("sobre"); })
  );
  ["dragleave", "drop"].forEach((ev) =>
    solta.addEventListener(ev, (e) => { e.preventDefault(); solta.classList.remove("sobre"); })
  );
  solta.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length) { entrada.files = e.dataTransfer.files; mostrarArquivo(); }
  });
  entrada.addEventListener("change", mostrarArquivo);
  function mostrarArquivo() {
    const f = entrada.files[0];
    const selo = $("#arquivo-nome");
    selo.hidden = !f;
    if (f) selo.textContent = `${f.name} · ${bytesCurto(f.size)}`;
  }

  $("#form-novo").addEventListener("submit", enviarNovo);
  await listarJobs();
}

async function enviarNovo(evento) {
  evento.preventDefault();
  const botao = $("#enviar");
  const aviso = $("#erro-novo");
  aviso.hidden = true;
  botao.disabled = true;
  botao.textContent = "Enviando…";

  const dados = new FormData();
  const arquivo = $("#arquivo").files[0];
  if (arquivo) dados.append("arquivo", arquivo);
  dados.append("url", $("#url").value.trim());
  dados.append("n", $("#n").value);
  dados.append("estrategia", $("#estrategia").value);
  dados.append("preset", $("#preset").value);
  dados.append("modelo_whisper", $("#modelo_whisper").value);
  dados.append("usar_api", padroes.tem_chave_api ? "true" : "false");

  try {
    const job = await api("/jobs", { method: "POST", body: dados });
    location.hash = `#/job/${job.id}`;
  } catch (erro) {
    aviso.hidden = false;
    aviso.textContent = [erro.dados.mensagem, erro.dados.sugestao].filter(Boolean).join(" — ");
  } finally {
    botao.disabled = false;
    botao.textContent = "Gerar cortes";
  }
}

async function listarJobs() {
  const { jobs } = await api("/jobs");
  const lista = $("#lista-jobs");
  if (!jobs.length) {
    lista.innerHTML = `<p class="vazio">Nenhum vídeo processado ainda.</p>`;
    return;
  }
  lista.innerHTML = jobs
    .map((j) => {
      const quando = (j.criado_em || "").replace("T", " ").slice(0, 16);
      const status = ROTULO_STATUS[j.status] || j.status;
      return `<a class="item" href="#/job/${encodeURIComponent(j.id)}" data-rota>
        <span>
          <div class="item-nome">${escapar(j.titulo || j.id)}</div>
          <div class="item-meta">${escapar(quando)} · ${escapar((j.opcoes && j.opcoes.preset) || "")}${j.do_terminal ? " · feito no terminal" : ""}</div>
        </span>
        <span class="selo ${j.status}">${status}</span>
      </a>`;
    })
    .join("");
}

function escapar(texto) {
  const d = document.createElement("div");
  d.textContent = texto == null ? "" : String(texto);
  return d.innerHTML;
}

// ------------------------------------------------------------------ job

const ORDEM_ESTAGIOS = [
  ["ingestao", "Baixar"],
  ["transcricao", "Transcrever"],
  ["selecao", "Selecionar"],
  ["render", "Renderizar"],
];

async function telaJob(id) {
  ultimosClipes = [];
  tela.appendChild(modelo("tpl-job"));
  let job;
  try {
    job = await api(`/jobs/${id}`);
  } catch (erro) {
    tela.innerHTML = `<section class="coluna"><h1>Vídeo não encontrado</h1>
      <p class="fraco">${escapar(erro.dados.mensagem || "")}</p>
      <a class="voltar" href="#/">← todos os vídeos</a></section>`;
    return;
  }
  pintarJob(job);

  $("#copiar-prompt").addEventListener("click", async () => {
    const texto = await api(`/jobs/${id}/prompt`);
    await navigator.clipboard.writeText(texto);
    const ok = $("#copiado");
    ok.hidden = false;
    setTimeout(() => { ok.hidden = true; }, 2200);
  });

  $("#validar").addEventListener("click", () => validarResposta(id));
  $("#abrir-pasta").addEventListener("click", () => api(`/jobs/${id}/abrir-pasta`, { method: "POST" }));

  // SSE: o servidor manda o estado atual assim que conecta.
  fonteEventos = new EventSource(`/jobs/${id}/events`);
  fonteEventos.onmessage = (evento) => {
    const dados = JSON.parse(evento.data);
    if (!dados.job) return;
    if (dados.tipo === "concluido") {
      api(`/jobs/${id}`).then(pintarJob);
    } else {
      pintarJob(dados.job);
    }
  };
}

let ultimosClipes = [];

function pintarJob(job) {
  $("#job-titulo").textContent = job.titulo || job.id;
  $("#job-entrada").textContent = job.entrada || "";

  // trilha de estagios
  const feitos = job.estagios || {};
  $("#trilha").innerHTML = ORDEM_ESTAGIOS.map(([nome, rotulo]) => {
    const e = feitos[nome] || {};
    const classe = e.status === "pronto" ? "pronto" : job.estagio === nome ? "rodando" : "";
    const tempo = e.segundos ? tempoCurto(e.segundos) + (e.reaproveitado ? " · reaproveitado" : "") : "";
    return `<li class="${classe}"><span class="pino"></span>${rotulo}<span class="tempo">${tempo}</span></li>`;
  }).join("");

  $("#barra-cheia").style.transform = `scaleX(${Math.min(1, job.progresso || 0)})`;

  const est = job.estimativa || {};
  const partes = [];
  if (job.status === "rodando" && est.restante_s > 0) partes.push(`faltam ~${tempoCurto(est.restante_s)}`);
  if (job.status) partes.push(ROTULO_STATUS[job.status] || job.status);
  $("#job-tempo").textContent = partes.join(" · ");

  // erro
  const blocoErro = $("#bloco-erro");
  blocoErro.hidden = !job.erro;
  if (job.erro) {
    $("#erro-msg").textContent = job.erro.mensagem || "";
    $("#erro-sugestao").textContent = job.erro.sugestao || "";
    const det = $("#erro-detalhe");
    det.hidden = !job.erro.detalhe;
    det.textContent = job.erro.detalhe || "";
  }

  // modo manual
  $("#bloco-manual").hidden = job.status !== "aguardando_resposta";

  // Clipes: um evento sem a chave 'clipes' NAO significa "nao ha clipes" --
  // significa "este evento nao fala de clipes". Apagar a grade nesse caso
  // fazia os cortes sumirem da tela um instante depois de aparecerem.
  const clipes = Array.isArray(job.clipes) ? job.clipes : ultimosClipes;
  ultimosClipes = clipes;
  $("#bloco-clipes").hidden = clipes.length === 0;
  $("#contagem").textContent = clipes.length ? `· ${clipes.length}` : "";
  if (clipes.length) pintarClipes(job, clipes);
}

function pintarClipes(job, clipes) {
  const grade = $("#grade");
  const assinatura = clipes.map((c) => `${c.id}:${c.bytes}`).join("|");
  if (grade.dataset.assinatura === assinatura) return;  // nao recarrega os players a toa
  grade.dataset.assinatura = assinatura;

  grade.innerHTML = clipes
    .map(
      (c) => `<article class="clipe">
      <video src="/jobs/${job.id}/clips/${c.id}.mp4" poster="/jobs/${job.id}/clips/${c.id}.jpg"
             controls preload="none" playsinline></video>
      <div class="clipe-corpo">
        <div class="clipe-titulo">${escapar(c.titulo)}</div>
        <div class="clipe-linha">
          <span class="nota">${escapar(c.score ?? "—")}</span>
          <span class="fraco">${escapar(c.inicio_mmss)}–${escapar(c.fim_mmss)} · ${Math.round(c.duracao)}s · ${bytesCurto(c.bytes)}</span>
        </div>
        ${c.gancho ? `<div class="clipe-gancho">${escapar(c.gancho)}</div>` : ""}
        ${c.motivo ? `<div class="clipe-motivo">${escapar(c.motivo)}</div>` : ""}
        <div class="clipe-acoes">
          <a class="botao pequeno" href="/jobs/${job.id}/clips/${c.id}.mp4" download>Baixar</a>
          <button class="botao pequeno" data-rerender="${c.id}">Re-renderizar</button>
          ${c.gancho ? `<button class="botao pequeno" data-gancho-de="${c.id}">Copiar gancho</button>` : ""}
        </div>
      </div>
    </article>`
    )
    .join("");

  $$("[data-rerender]", grade).forEach((botao) =>
    botao.addEventListener("click", async () => {
      botao.disabled = true;
      botao.textContent = "Na fila…";
      await api(`/jobs/${job.id}/rerender`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ clip_n: Number(botao.dataset.rerender), forcar: true }),
      });
    })
  );
  // O gancho NAO vai para dentro de um atributo: escapar() neutraliza < e &,
  // mas nao aspas -- e o texto vem do modelo que escolheu os cortes. Aqui o
  // botao guarda so o id, e o texto sai do objeto.
  const ganchoPorId = new Map(clipes.map((c) => [String(c.id), c.gancho || ""]));
  $$("[data-gancho-de]", grade).forEach((botao) =>
    botao.addEventListener("click", async () => {
      await navigator.clipboard.writeText(ganchoPorId.get(botao.dataset.ganchoDe) || "");
      const antes = botao.textContent;
      botao.textContent = "copiado ✓";
      setTimeout(() => { botao.textContent = antes; }, 1800);
    })
  );
}

async function validarResposta(id) {
  const botao = $("#validar");
  const bloco = $("#problemas");
  bloco.hidden = true;
  botao.disabled = true;
  botao.textContent = "Validando…";
  try {
    await api(`/jobs/${id}/prompt-resposta`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ resposta: $("#resposta").value }),
    });
    $("#bloco-manual").hidden = true;
  } catch (erro) {
    const dados = erro.dados || {};
    const problemas = dados.problemas && dados.problemas.length ? dados.problemas : [dados.mensagem];
    bloco.hidden = false;
    $("#problemas-titulo").textContent = dados.mensagem || "a resposta não passou na validação";
    $("#problemas-lista").innerHTML = problemas.map((p) => `<li><span>${escapar(p)}</span></li>`).join("");
    $("#problemas-sugestao").textContent = dados.sugestao || "";
  } finally {
    botao.disabled = false;
    botao.textContent = "Validar e continuar";
  }
}

desenhar();
