"use strict";

const MARKUPS = [50, 60, 70];
const TELAS = { inicio: "Início", vendas: "Vendas", produtos: "Produtos" };
const FILTROS = [
  [null, "Todas"],
  ["a_receber", "A receber"],
  ["a_enviar", "A enviar"],
  ["enviado", "Enviadas"],
  ["entregue", "Entregues"],
  ["cancelada", "Canceladas"],
];
const ROTULOS = {
  pendente: "A receber",
  pago: "Pago",
  a_enviar: "A enviar",
  enviado: "Enviado",
  entregue: "Entregue",
  cancelada: "Cancelada",
};
const PARTES = [
  ["produto", "Produto"],
  ["frete_internacional", "Frete internacional"],
  ["impostos", "Impostos"],
  ["frete_nacional", "Frete até você"],
];

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const usd = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD" });
const fmtMes = new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" });
const fmtDiaCurto = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" });
const fmtDia = new Intl.DateTimeFormat("pt-BR");
const fmtHoje = new Intl.DateTimeFormat("pt-BR", { weekday: "long", day: "numeric", month: "long" });

const $ = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

const estado = {
  tela: "inicio",
  mes: mesAtual(), // "YYYY-MM" ou null para todas
  filtro: null,
  vendas: [],
  totalVendas: 0,
  produtos: [],
  vendaEditando: null,
  itensVenda: [],
  produtoEditando: null,
  fotoNova: null,
  fotoRemover: false,
  compraEditando: null,
};

/* ---------- Utilidades ---------- */

function mesAtual() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function hojeISO() {
  return `${mesAtual()}-${String(new Date().getDate()).padStart(2, "0")}`;
}

function moverMes(iso, delta) {
  const [a, m] = iso.split("-").map(Number);
  const d = new Date(a, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

// "1.234,56", "1234,56" ou "1234.56" -> inteiro na escala; vazio -> null; inválido -> NaN
function paraInteiro(texto, escala) {
  let t = String(texto).replace(/[R$US%\s]/g, "");
  if (!t) return null;
  if (t.includes(",")) t = t.replace(/\./g, "").replace(",", ".");
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 ? Math.round(n * escala) : NaN;
}

const paraCentavos = (t) => paraInteiro(t, 100);
const valido = (n) => n != null && !Number.isNaN(n);
const paraTexto = (n, escala = 100, casas = 2) =>
  n == null ? "" : (n / escala).toFixed(casas).replace(".", ",");
const dinheiro = (c) => (c == null ? "–" : brl.format(c / 100));
const dataLocal = (iso) => new Date(`${iso}T12:00:00`);
const sinal = (c) => (c < 0 ? "negativo" : "positivo");
const lucroTexto = (c) => (c > 0 ? "+" : "") + dinheiro(c);
const porcento = (n) => `${n.toFixed(1).replace(".", ",")}%`;
const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;
const semAcento = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

// Mesmas contas do servidor (app/calculos.py): inteiros, meio centavo para cima.
const dividir = (a, b) => Math.floor((2 * a + b) / (2 * b));
const comMarkup = (custo, pct) => dividir(custo * (100 + pct), 100);
const calcTaxa = (subtotal, desconto, pct) => dividir(Math.max(0, subtotal - desconto) * pct, 10000);

function el(tag, classe, texto) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texto != null) e.textContent = texto;
  return e;
}

function miniatura(url, nome) {
  if (!url) return el("span", "mini mini-vazia");
  const img = el("img", "mini");
  img.src = url;
  img.alt = "";
  img.loading = "lazy";
  img.title = nome;
  return img;
}

class ErroLogin extends Error {}

async function api(caminho, opcoes = {}) {
  const corpoJson = opcoes.body && !(opcoes.body instanceof FormData);
  const resp = await fetch(caminho, {
    credentials: "same-origin",
    ...opcoes,
    headers: corpoJson ? { "Content-Type": "application/json" } : {},
  });
  if (resp.status === 401 && caminho !== "/api/login") {
    mostrarLogin();
    throw new ErroLogin("Sessão encerrada.");
  }
  if (!resp.ok) {
    let detalhe = `Erro ${resp.status}`;
    try {
      const corpo = await resp.json();
      if (typeof corpo.detail === "string") detalhe = corpo.detail;
      else if (Array.isArray(corpo.detail))
        detalhe = corpo.detail.map((d) => String(d.msg).replace(/^Value error, /, "")).join(" ");
    } catch {}
    throw new Error(detalhe);
  }
  return resp.status === 204 ? null : resp.json();
}

function carimbo(status) {
  const s = el("span", "carimbo", ROTULOS[status]);
  s.dataset.status = status;
  return s;
}

function falhaCarga(alvo) {
  return (e) => {
    if (e instanceof ErroLogin) return;
    alvo.hidden = false;
    alvo.textContent = `Não foi possível carregar (${e.message}). Verifique a conexão e recarregue a página.`;
  };
}

/* ---------- Login ---------- */

const formLogin = $("#form-login");

function mostrarLogin() {
  $$("dialog[open]").forEach((d) => d.close());
  $("#app").hidden = true;
  $("#login").hidden = false;
  document.body.dataset.tela = "login";
  formLogin.senha.value = "";
  (formLogin.usuario.value ? formLogin.senha : formLogin.usuario).focus();
}

formLogin.addEventListener("submit", async (e) => {
  e.preventDefault();
  const usuario = formLogin.usuario.value.trim();
  const senha = formLogin.senha.value;
  if (!usuario || !senha) {
    mostrarErro(formLogin, "Informe usuário e senha.");
    return;
  }
  await enviar(formLogin, async () => {
    await api("/api/login", { method: "POST", body: JSON.stringify({ usuario, senha }) });
    mostrarErro(formLogin, "");
    iniciarApp();
  }, "");
});

$("#sair").addEventListener("click", async () => {
  try {
    await api("/api/logout", { method: "POST" });
  } finally {
    mostrarLogin();
  }
});

function iniciarApp() {
  $("#login").hidden = true;
  $("#app").hidden = false;
  irPara(location.hash.slice(1) || "inicio");
}

/* ---------- Navegação ---------- */

function irPara(tela) {
  if (!TELAS[tela]) tela = "inicio";
  estado.tela = tela;
  document.body.dataset.tela = tela;
  $("#titulo").textContent = TELAS[tela];
  document.title = `${TELAS[tela]} | Vendas`;
  $$(".tela").forEach((s) => (s.hidden = s.id !== `tela-${tela}`));
  $$("[data-aba]").forEach((a) =>
    a.dataset.aba === tela ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")
  );
  $("#nova").textContent = tela === "produtos" ? "Novo produto" : "Nova venda";
  recarregar();
}

function recarregar() {
  if (estado.tela === "inicio") return carregarPainel().catch(falhaCarga($("#vazio-recentes")));
  if (estado.tela === "vendas") return carregarVendas().catch(falhaCarga($("#vazio-vendas")));
  return carregarProdutos().then(desenharProdutos).catch(falhaCarga($("#vazio-produtos")));
}

window.addEventListener("hashchange", () => {
  if (!$("#app").hidden) irPara(location.hash.slice(1));
});

/* ---------- Início ---------- */

function valorBloco(seletor, centavos) {
  const alvo = $(seletor);
  alvo.textContent = dinheiro(centavos);
  alvo.classList.toggle("negativo", centavos < 0);
}

async function carregarPainel() {
  const p = await api(`/api/painel?hoje=${hojeISO()}`);
  $("#hoje").textContent = fmtHoje.format(new Date());

  valorBloco("#p-lucro-dia", p.lucro_dia);
  $("#p-vendas-dia").textContent = p.vendas_dia
    ? `${plural(p.vendas_dia, "venda", "vendas")}, ${dinheiro(p.vendido_dia)}`
    : "Nenhuma venda hoje";
  valorBloco("#p-lucro-mes", p.lucro_mes);
  $("#p-vendas-mes").textContent = p.vendas_mes
    ? `${plural(p.vendas_mes, "venda", "vendas")}, ${dinheiro(p.vendido_mes)}`
    : "Nenhuma venda este mês";

  valorBloco("#p-receber", p.a_receber);
  $("#p-receber-nota").textContent = p.vendas_a_receber
    ? `em ${plural(p.vendas_a_receber, "venda", "vendas")}`
    : "Tudo recebido";
  $("#p-enviar").textContent = p.a_enviar;

  $("#p-estoque-itens").textContent = plural(p.estoque_itens, "item", "itens");
  $("#p-estoque-produtos").textContent = plural(p.estoque_produtos, "produto", "produtos");
  valorBloco("#p-estoque-valor", p.estoque_valor);

  $("#grupo-baixo").hidden = p.estoque_baixo.length === 0;
  $("#lista-baixo").replaceChildren(...p.estoque_baixo.map(itemProduto));

  $("#lista-recentes").replaceChildren(...p.recentes.map(itemVenda));
  $("#vazio-recentes").hidden = p.recentes.length > 0;
  $("#vazio-recentes").textContent = "Nenhuma venda registrada ainda.";
}

$$(".bloco[data-filtro]").forEach((a) =>
  a.addEventListener("click", () => {
    // Os totais do painel valem para todas as datas.
    estado.filtro = a.dataset.filtro;
    estado.mes = null;
    desenharMes();
    desenharFiltros();
  })
);

/* ---------- Vendas ---------- */

function consultaVendas(extra = {}) {
  const p = new URLSearchParams();
  if (estado.mes) p.set("mes", estado.mes);
  if (estado.filtro) p.set("filtro", estado.filtro);
  for (const [k, v] of Object.entries(extra)) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function carregarVendas() {
  const [pagina, resumo] = await Promise.all([
    api(`/api/vendas${consultaVendas()}`),
    api(`/api/resumo${estado.mes ? `?mes=${estado.mes}` : ""}`),
  ]);
  estado.vendas = pagina.vendas;
  estado.totalVendas = pagina.total;
  desenharResumo(resumo);
  desenharVendas();
  $("#exportar").href = `/api/vendas.csv${consultaVendas()}`;
}

$("#mais-vendas").addEventListener("click", async (e) => {
  const b = e.currentTarget;
  b.disabled = true;
  try {
    const pagina = await api(`/api/vendas${consultaVendas({ offset: estado.vendas.length })}`);
    estado.vendas.push(...pagina.vendas);
    estado.totalVendas = pagina.total;
    desenharVendas();
  } catch (err) {
    falhaCarga($("#vazio-vendas"))(err);
  } finally {
    b.disabled = false;
  }
});

function desenharMes() {
  const nome = estado.mes ? fmtMes.format(dataLocal(`${estado.mes}-01`)) : "Todas";
  $("#mes-nome").textContent = nome[0].toUpperCase() + nome.slice(1);
  $$(".mes-seta").forEach((b) => (b.disabled = !estado.mes));
}

function desenharResumo(r) {
  $("#r-vendido").textContent = dinheiro(r.vendido);
  const lucro = $("#r-lucro");
  lucro.textContent = dinheiro(r.lucro);
  lucro.className = r.lucro < 0 ? "negativo" : r.lucro > 0 ? "positivo" : "";
  $("#r-margem").textContent = r.vendido ? porcento((r.lucro / r.vendido) * 100) : "–";
  $("#r-receber").textContent = dinheiro(r.a_receber);
}

function desenharFiltros() {
  $("#filtros").replaceChildren(
    ...FILTROS.map(([valor, rotulo]) => {
      const b = el("button", "chip", rotulo);
      b.type = "button";
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", String(estado.filtro === valor));
      b.addEventListener("click", () => {
        estado.filtro = valor;
        desenharFiltros();
        recarregar();
      });
      return b;
    })
  );
}

const resumoItens = (v) => v.itens.map((i) => `${i.qtd}× ${i.produto}`).join(", ");

function carimbosVenda(v) {
  return v.cancelada ? [carimbo("cancelada")] : [carimbo(v.pagamento), carimbo(v.entrega)];
}

function itemVenda(v) {
  const li = document.createElement("li");
  const b = el("button", `item${v.cancelada ? " cancelado" : ""}`);
  b.type = "button";
  const meta = el("span", "item-meta");
  meta.append(fmtDiaCurto.format(dataLocal(v.data_venda)), ...carimbosVenda(v));
  b.append(
    el("span", "item-cliente", v.cliente),
    el("span", "item-valor", dinheiro(v.total)),
    el("span", "item-produto", resumoItens(v)),
    el("span", `item-lucro ${sinal(v.lucro)}`, lucroTexto(v.lucro)),
    meta
  );
  b.addEventListener("click", () => abrirVenda(v));
  li.append(b);
  return li;
}

function desenharVendas() {
  const { vendas } = estado;
  $("#lista-vendas").replaceChildren(...vendas.map(itemVenda));

  $("#tabela tbody").replaceChildren(
    ...vendas.map((v) => {
      const tr = document.createElement("tr");
      if (v.cancelada) tr.className = "cancelado";
      tr.tabIndex = 0;
      const pagamento = document.createElement("td");
      const entrega = document.createElement("td");
      if (v.cancelada) pagamento.append(carimbo("cancelada"));
      else {
        pagamento.append(carimbo(v.pagamento));
        entrega.append(carimbo(v.entrega));
      }
      tr.append(
        el("td", null, v.cliente),
        el("td", null, fmtDia.format(dataLocal(v.data_venda))),
        el("td", "produto", resumoItens(v)),
        el("td", "num", v.itens.reduce((s, i) => s + i.qtd, 0)),
        el("td", "num", dinheiro(v.custo_itens)),
        el("td", "num", dinheiro(v.total)),
        el("td", "num markup", dinheiro(v.taxa + v.frete)),
        el("td", `num ${sinal(v.lucro)}`, dinheiro(v.lucro)),
        pagamento,
        entrega
      );
      tr.addEventListener("click", () => abrirVenda(v));
      tr.addEventListener("keydown", (e) => e.key === "Enter" && abrirVenda(v));
      return tr;
    })
  );

  const restantes = estado.totalVendas - vendas.length;
  const mais = $("#mais-vendas");
  mais.hidden = restantes <= 0;
  mais.textContent = `Mostrar mais ${Math.min(restantes, 30)} de ${restantes}`;

  const vazio = $("#vazio-vendas");
  vazio.hidden = vendas.length > 0;
  $(".tabela-wrap").hidden = vendas.length === 0;
  if (!vendas.length) {
    const onde = estado.mes ? `em ${fmtMes.format(dataLocal(`${estado.mes}-01`)).split(" ")[0]}` : "registrada";
    const filtro = estado.filtro ? ` no filtro ${FILTROS.find(([v]) => v === estado.filtro)[1].toLowerCase()}` : "";
    vazio.textContent = `Nenhuma venda ${onde}${filtro}. Toque em Nova venda para registrar.`;
  }
}

$$(".mes-seta").forEach((b) =>
  b.addEventListener("click", () => {
    estado.mes = moverMes(estado.mes, Number(b.dataset.mes));
    desenharMes();
    recarregar();
  })
);

$("#mes-nome").addEventListener("click", () => {
  estado.mes = estado.mes ? null : mesAtual();
  desenharMes();
  recarregar();
});

/* ---------- Produtos ---------- */

async function carregarProdutos() {
  estado.produtos = await api("/api/produtos");
}

function buscarProdutos(termo) {
  const t = semAcento(termo.trim());
  return t ? estado.produtos.filter((p) => semAcento(p.nome).includes(t)) : estado.produtos;
}

function desenharProdutos() {
  const termo = $("#busca-produtos").value;
  const achados = buscarProdutos(termo);
  $("#lista-produtos").replaceChildren(...achados.map(itemProduto));
  const vazio = $("#vazio-produtos");
  vazio.hidden = achados.length > 0;
  vazio.textContent = estado.produtos.length
    ? `Nenhum produto com "${termo.trim()}".`
    : "Nenhum produto cadastrado. Toque em Novo produto para registrar a primeira compra e ver os preços sugeridos.";
}

$("#busca-produtos").addEventListener("input", desenharProdutos);

function textoEstoque(n) {
  if (n > 0) return `${n} em estoque`;
  if (n === 0) return "sem estoque";
  return `${-n} sob encomenda`;
}

function itemProduto(p) {
  const li = document.createElement("li");
  const b = el("button", "item item-com-foto");
  b.type = "button";
  const precos = el("span", "item-precos");
  if (p.precos) {
    for (const pct of MARKUPS) {
      const s = el("span", null, `+${pct}% `);
      s.append(el("b", null, dinheiro(p.precos[pct])));
      precos.append(s);
    }
  } else {
    precos.textContent = "Registre uma compra para ver os preços sugeridos";
  }
  b.append(
    miniatura(p.foto_url, p.nome),
    el("span", "item-cliente", p.nome),
    el("span", `item-estoque${p.estoque <= 0 ? " zerado" : ""}`, textoEstoque(p.estoque)),
    el("span", "item-produto", p.custo == null ? "Sem compra registrada" : `Custo ${dinheiro(p.custo)}`),
    el("span"),
    precos
  );
  b.addEventListener("click", () => abrirProduto(p));
  li.append(b);
  return li;
}

/* ---------- Componentes de formulário ---------- */

function desenharFaixas(grade, aoEscolher) {
  grade.replaceChildren(
    ...MARKUPS.map((pct) => {
      const f = el(aoEscolher ? "button" : "div", "faixa");
      if (aoEscolher) {
        f.type = "button";
        f.addEventListener("click", () => aoEscolher(pct));
      }
      f.dataset.pct = pct;
      f.append(el("span", "faixa-pct", `+${pct}%`), el("span", "faixa-preco", "–"));
      return f;
    })
  );
}

function atualizarFaixas(grade, custo, selecionado) {
  const ok = valido(custo);
  $$(".faixa", grade).forEach((f) => {
    const preco = ok ? comMarkup(custo, Number(f.dataset.pct)) : null;
    $(".faixa-preco", f).textContent = dinheiro(preco);
    if (f.tagName === "BUTTON") {
      f.disabled = !ok;
      f.setAttribute("aria-pressed", String(ok && preco === selecionado));
    }
  });
}

function criarPasso(input, minimo, aoMudar) {
  const caixa = input.closest(".passo");
  $$("[data-passo]", caixa).forEach((b) =>
    b.addEventListener("click", () => {
      const atual = parseInt(input.value, 10) || 0;
      input.value = Math.max(minimo, atual + Number(b.dataset.passo));
      input.dispatchEvent(new Event("input", { bubbles: true }));
      aoMudar?.();
    })
  );
}

function ligarFolha(folha) {
  $(".fechar", folha).addEventListener("click", () => folha.close());
  folha.addEventListener("click", (e) => e.target === folha && folha.close());
}

function mostrarErro(form, msg) {
  const erro = $(".erro", form);
  erro.textContent = msg;
  erro.hidden = !msg;
}

function limparInvalidos(form) {
  $$("[aria-invalid]", form).forEach((i) => i.removeAttribute("aria-invalid"));
}

function validador(form) {
  limparInvalidos(form);
  const erros = [];
  return {
    erros,
    marcar(campo, msg) {
      campo.setAttribute("aria-invalid", "true");
      erros.push(msg);
    },
    falhou() {
      if (!erros.length) return false;
      mostrarErro(form, erros.join(" "));
      $("[aria-invalid]", form)?.focus();
      return true;
    },
  };
}

function prepararExcluir(form, visivel) {
  const b = $(".excluir", form);
  b.hidden = !visivel;
  b.classList.remove("confirmar");
  b.textContent = "Excluir";
}

// Primeiro toque arma, segundo confirma, sem diálogo do navegador.
function ligarExcluir(form, executar) {
  $(".excluir", form).addEventListener("click", async (e) => {
    const b = e.currentTarget;
    if (!b.classList.contains("confirmar")) {
      b.classList.add("confirmar");
      b.textContent = "Confirmar exclusão";
      return;
    }
    try {
      await executar();
    } catch (err) {
      if (!(err instanceof ErroLogin)) mostrarErro(form, `Não foi possível excluir: ${err.message}`);
    }
  });
}

async function enviar(form, chamada, prefixo = "Não foi possível salvar: ") {
  const salvar = $(".salvar[type=submit]", form);
  salvar.disabled = true;
  try {
    await chamada();
  } catch (err) {
    if (!(err instanceof ErroLogin)) mostrarErro(form, prefixo + err.message);
  } finally {
    salvar.disabled = false;
  }
}

/* ---------- Campos de compra (lote) ---------- */

// Monta os campos do template dentro de `alvo` e devolve como ler e preencher.
function criarCamposCompra(alvo) {
  alvo.append($("#tpl-compra").content.cloneNode(true));
  const campo = (nome) => $(`[name=${nome}]`, alvo);
  const moeda = () => $("input[name=moeda]:checked", alvo).value;
  const barra = $(".composicao-barra", alvo);
  const legenda = $(".composicao-legenda", alvo);

  // Ids únicos para rótulos do passo de quantidade.
  const id = `qtd-${Math.random().toString(36).slice(2, 8)}`;
  $("[data-rotulo=qtd]", alvo).id = id;
  $(".passo", alvo).setAttribute("aria-labelledby", id);
  campo("qtd").setAttribute("aria-labelledby", id);

  function ler() {
    const m = moeda();
    return {
      data_compra: campo("data_compra").value,
      qtd: parseInt(campo("qtd").value, 10),
      moeda: m,
      preco_unit: paraCentavos(campo("preco_unit").value),
      cambio: m === "BRL" ? 10000 : paraInteiro(campo("cambio").value, 10000),
      frete_internacional: paraCentavos(campo("frete_internacional").value) ?? 0,
      impostos: paraCentavos(campo("impostos").value) ?? 0,
      frete_nacional: paraCentavos(campo("frete_nacional").value) ?? 0,
    };
  }

  function atualizar() {
    const m = moeda();
    $("[data-so-dolar]", alvo).hidden = m === "BRL";
    $("[data-rotulo=preco]", alvo).textContent = `Preço por unidade (${m === "USD" ? "US$" : "R$"})`;

    const c = ler();
    const ok = c.qtd >= 1 && valido(c.preco_unit) && valido(c.cambio)
      && [c.frete_internacional, c.impostos, c.frete_nacional].every(valido);
    if (!ok) {
      $("[data-custo-unit]", alvo).textContent = "–";
      barra.replaceChildren();
      legenda.replaceChildren();
      return;
    }
    const partes = {
      produto: dividir(c.preco_unit * c.qtd * c.cambio, 10000),
      frete_internacional: c.frete_internacional,
      impostos: c.impostos,
      frete_nacional: c.frete_nacional,
    };
    const total = Object.values(partes).reduce((a, b) => a + b, 0);
    $("[data-custo-unit]", alvo).textContent = dinheiro(dividir(total, c.qtd));
    barra.replaceChildren(
      ...PARTES.filter(([k]) => partes[k] > 0).map(([k]) => {
        const s = el("span", `parte parte-${k}`);
        s.style.flexGrow = partes[k];
        return s;
      })
    );
    legenda.replaceChildren(
      ...PARTES.filter(([k]) => partes[k] > 0).map(([k, rotulo]) => {
        const li = el("li");
        li.append(
          el("span", `ponto parte-${k}`),
          el("span", null, rotulo),
          el("span", "legenda-valor", `${dinheiro(partes[k])} (${porcento((partes[k] / total) * 100)})`)
        );
        return li;
      })
    );
  }

  function preencher(lote) {
    campo("data_compra").value = lote?.data_compra ?? hojeISO();
    campo("qtd").value = lote?.qtd ?? 1;
    const m = lote?.moeda ?? localStorage.getItem("ultima-moeda") ?? "USD";
    $(`input[name=moeda][value=${m}]`, alvo).checked = true;
    campo("preco_unit").value = paraTexto(lote?.preco_unit);
    const cambio = lote?.cambio ?? (Number(localStorage.getItem("ultimo-cambio")) || null);
    campo("cambio").value = m === "USD" && cambio ? paraTexto(cambio, 10000, 4) : "";
    for (const k of ["frete_internacional", "impostos", "frete_nacional"])
      campo(k).value = lote?.[k] ? paraTexto(lote[k]) : "";
    atualizar();
  }

  function validar(v) {
    const c = ler();
    if (!c.data_compra) v.marcar(campo("data_compra"), "Informe a data da compra.");
    if (!(c.qtd >= 1)) v.marcar(campo("qtd"), "A quantidade precisa ser 1 ou mais.");
    if (!valido(c.preco_unit)) v.marcar(campo("preco_unit"), "Informe o preço por unidade, por exemplo 25,90.");
    if (!valido(c.cambio) || c.cambio === 0) v.marcar(campo("cambio"), "Informe o câmbio, por exemplo 5,42.");
    for (const k of ["frete_internacional", "impostos", "frete_nacional"])
      if (!valido(c[k])) v.marcar(campo(k), "Valores de frete e impostos inválidos. Use o formato 150,00.");
    return c;
  }

  // Lembra moeda e câmbio para a próxima compra.
  function lembrar(c) {
    localStorage.setItem("ultima-moeda", c.moeda);
    if (c.moeda === "USD") localStorage.setItem("ultimo-cambio", c.cambio);
  }

  alvo.addEventListener("input", (e) => {
    e.target.removeAttribute?.("aria-invalid");
    atualizar();
  });
  alvo.addEventListener("change", atualizar);
  criarPasso(campo("qtd"), 1);

  return { ler, preencher, validar, lembrar };
}

/* ---------- Folha de produto ---------- */

const folhaProduto = $("#folha-produto");
const formProduto = $("#form-produto");
const compraNova = criarCamposCompra($("#fp-compra"));
desenharFaixas($("#fp-faixas"));

function desenharFotoProduto(url) {
  const previa = $("#fp-foto-previa");
  previa.replaceChildren();
  if (url) {
    const img = el("img");
    img.src = url;
    img.alt = "Foto do produto";
    previa.append(img);
  } else {
    previa.append(el("span", null, "Sem foto"));
  }
  $("#fp-foto-rotulo").textContent = url ? "Trocar foto" : "Adicionar foto";
  $("#fp-foto-remover").hidden = !url;
}

function desenharDetalheProduto(p) {
  $("#fp-estoque").textContent = textoEstoque(p.estoque);
  $("#fp-custo").textContent = p.custo == null ? "–" : dinheiro(p.custo);
  atualizarFaixas($("#fp-faixas"), p.custo);
  $("#fp-compras").replaceChildren(
    ...p.lotes.map((l) => {
      const li = document.createElement("li");
      const b = el("button", "item");
      b.type = "button";
      const origem = l.moeda === "USD" ? `${usd.format(l.preco_unit / 100)} a R$ ${paraTexto(l.cambio, 10000, 2)}` : "em reais";
      b.append(
        el("span", "item-cliente", `${plural(l.qtd, "unidade", "unidades")} em ${fmtDia.format(dataLocal(l.data_compra))}`),
        el("span", "item-valor", `${dinheiro(l.custo_unit)}/un`),
        el("span", "item-produto", `Total ${dinheiro(l.custo_total)}, ${origem}`),
        el("span")
      );
      b.addEventListener("click", () => abrirCompra(p, l));
      li.append(b);
      return li;
    })
  );
  if (!p.lotes.length) $("#fp-compras").append(el("li", "vazio-curto", "Nenhuma compra registrada."));
}

async function abrirProduto(resumo = null) {
  let produto = null;
  if (resumo) {
    try {
      produto = await api(`/api/produtos/${resumo.id}`);
    } catch (err) {
      if (!(err instanceof ErroLogin)) alertarTela(`Não foi possível abrir o produto (${err.message}).`);
      return;
    }
  }
  estado.produtoEditando = produto;
  estado.fotoNova = null;
  estado.fotoRemover = false;
  formProduto.reset();
  limparInvalidos(formProduto);
  mostrarErro(formProduto, "");
  prepararExcluir(formProduto, produto && produto.vendas === 0);

  $("#fp-titulo").textContent = produto ? "Editar produto" : "Novo produto";
  formProduto.nome.value = produto?.nome ?? "";
  formProduto.observacao.value = produto?.observacao ?? "";
  desenharFotoProduto(produto?.foto_url);
  $("#fp-compra").hidden = !!produto;
  $("#fp-detalhe").hidden = !produto;
  if (produto) desenharDetalheProduto(produto);
  else compraNova.preencher(null);

  folhaProduto.showModal();
  if (!produto) formProduto.nome.focus();
}

// Reduz para no máximo 1000 px e converte para JPEG antes de enviar.
async function reduzirFoto(arquivo) {
  const imagem = await createImageBitmap(arquivo);
  const escala = Math.min(1, 1000 / Math.max(imagem.width, imagem.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(imagem.width * escala);
  canvas.height = Math.round(imagem.height * escala);
  canvas.getContext("2d").drawImage(imagem, 0, 0, canvas.width, canvas.height);
  return new Promise((ok) => canvas.toBlob(ok, "image/jpeg", 0.82));
}

$("#fp-foto").addEventListener("change", async (e) => {
  const arquivo = e.target.files[0];
  e.target.value = "";
  if (!arquivo) return;
  try {
    estado.fotoNova = await reduzirFoto(arquivo);
    estado.fotoRemover = false;
    desenharFotoProduto(URL.createObjectURL(estado.fotoNova));
  } catch {
    mostrarErro(formProduto, "Não foi possível ler essa imagem. Tente uma foto em JPEG ou PNG.");
  }
});

$("#fp-foto-remover").addEventListener("click", () => {
  estado.fotoNova = null;
  estado.fotoRemover = true;
  desenharFotoProduto(null);
});

$("#fp-nova-compra").addEventListener("click", () => abrirCompra(estado.produtoEditando));

ligarFolha(folhaProduto);

formProduto.addEventListener("input", (e) => e.target.removeAttribute?.("aria-invalid"));

formProduto.addEventListener("submit", (e) => {
  e.preventDefault();
  const v = validador(formProduto);
  const nome = formProduto.nome.value.trim();
  const observacao = formProduto.observacao.value.trim();
  if (!nome) v.marcar(formProduto.nome, "Informe o nome do produto.");
  const editando = estado.produtoEditando;
  const compra = editando ? null : compraNova.validar(v);
  if (v.falhou()) return;

  enviar(formProduto, async () => {
    const salvo = editando
      ? await api(`/api/produtos/${editando.id}`, { method: "PUT", body: JSON.stringify({ nome, observacao }) })
      : await api("/api/produtos", { method: "POST", body: JSON.stringify({ nome, observacao, compra }) });
    if (compra) compraNova.lembrar(compra);
    // Se a foto falhar, o produto já está salvo: passa a editar em vez de criar outro.
    estado.produtoEditando = salvo;
    if (estado.fotoNova) {
      const dados = new FormData();
      dados.append("foto", estado.fotoNova, "foto.jpg");
      await api(`/api/produtos/${salvo.id}/foto`, { method: "PUT", body: dados });
    } else if (estado.fotoRemover && salvo.foto_url) {
      await api(`/api/produtos/${salvo.id}/foto`, { method: "DELETE" });
    }
    folhaProduto.close();
    await recarregar();
  });
});

ligarExcluir(formProduto, async () => {
  await api(`/api/produtos/${estado.produtoEditando.id}`, { method: "DELETE" });
  folhaProduto.close();
  await recarregar();
});

/* ---------- Folha de compra ---------- */

const folhaCompra = $("#folha-compra");
const formCompra = $("#form-compra");
const camposCompra = criarCamposCompra($("#fc-campos"));

function abrirCompra(produto, lote = null) {
  estado.compraEditando = { produto, lote };
  limparInvalidos(formCompra);
  mostrarErro(formCompra, "");
  prepararExcluir(formCompra, !!lote);
  $("#fc-titulo").textContent = lote ? "Editar compra" : "Registrar compra";
  $("#fc-produto").textContent = produto.nome;
  camposCompra.preencher(lote);
  folhaCompra.showModal();
}

ligarFolha(folhaCompra);

async function aposCompra(produto) {
  folhaCompra.close();
  estado.produtoEditando = produto;
  desenharDetalheProduto(produto);
  prepararExcluir(formProduto, produto.vendas === 0);
  await recarregar();
}

formCompra.addEventListener("submit", (e) => {
  e.preventDefault();
  const v = validador(formCompra);
  const compra = camposCompra.validar(v);
  if (v.falhou()) return;
  const { produto, lote } = estado.compraEditando;
  enviar(formCompra, async () => {
    const atualizado = await api(lote ? `/api/lotes/${lote.id}` : `/api/produtos/${produto.id}/lotes`, {
      method: lote ? "PUT" : "POST",
      body: JSON.stringify(compra),
    });
    camposCompra.lembrar(compra);
    await aposCompra(atualizado);
  });
});

ligarExcluir(formCompra, async () => {
  const atualizado = await api(`/api/lotes/${estado.compraEditando.lote.id}`, { method: "DELETE" });
  await aposCompra(atualizado);
});

/* ---------- Folha de venda ---------- */

const folhaVenda = $("#folha-venda");
const formVenda = $("#form-venda");
const busca = $("#fv-busca");
const resultados = $("#fv-resultados");

function taxasLembradas() {
  try {
    return JSON.parse(localStorage.getItem("taxas") || "{}");
  } catch {
    return {};
  }
}

function lerCustosVenda() {
  return {
    taxa_pct: paraCentavos(formVenda.taxa_pct.value) ?? 0,
    frete: paraCentavos(formVenda.frete.value) ?? 0,
    desconto: paraCentavos(formVenda.desconto.value) ?? 0,
  };
}

function cancelada() {
  return formVenda.cancelada.checked;
}

function avisoEstoque(item) {
  if (cancelada()) return ["", ""];
  if (item.qtd > item.disponivel) {
    const ha = Math.max(0, item.disponivel);
    return [`Só há ${plural(ha, "unidade", "unidades")} em estoque. O que faltar fica como encomenda.`, "alerta"];
  }
  return [plural(item.disponivel, "unidade disponível", "unidades disponíveis"), ""];
}

function linhaItem(item) {
  const li = el("li", "item-venda");
  const topo = el("div", "iv-topo");
  const remover = el("button", "iv-remover", "×");
  remover.type = "button";
  remover.setAttribute("aria-label", `Remover ${item.nome}`);
  remover.addEventListener("click", () => {
    estado.itensVenda = estado.itensVenda.filter((i) => i !== item);
    desenharItens();
    busca.focus();
  });
  topo.append(miniatura(item.foto_url, item.nome), el("strong", "iv-nome", item.nome), remover);

  const estoque = el("p", "iv-estoque");

  const linha = el("div", "iv-linha");
  const passo = el("div", "passo");
  passo.setAttribute("role", "group");
  passo.setAttribute("aria-label", `Quantidade de ${item.nome}`);
  const menos = el("button", null, "−");
  menos.type = "button";
  menos.dataset.passo = "-1";
  menos.setAttribute("aria-label", "Diminuir quantidade");
  const qtd = el("input");
  qtd.type = "number";
  qtd.inputMode = "numeric";
  qtd.min = "1";
  qtd.value = item.qtd;
  qtd.setAttribute("aria-label", `Quantidade de ${item.nome}`);
  const mais = el("button", null, "+");
  mais.type = "button";
  mais.dataset.passo = "1";
  mais.setAttribute("aria-label", "Aumentar quantidade");
  passo.append(menos, qtd, mais);

  const preco = el("input", "iv-preco");
  preco.inputMode = "decimal";
  preco.placeholder = "Valor final";
  preco.autocomplete = "off";
  preco.value = paraTexto(item.preco);
  preco.setAttribute("aria-label", `Valor final por unidade de ${item.nome}`);
  linha.append(passo, preco);

  const faixas = el("div", "faixas-grade faixas-mini");
  desenharFaixas(faixas, (pct) => {
    item.preco = comMarkup(item.custo, pct);
    preco.value = paraTexto(item.preco);
    preco.removeAttribute("aria-invalid");
    atualizar();
  });

  function atualizar() {
    const [texto, classe] = avisoEstoque(item);
    estoque.textContent = texto;
    estoque.className = `iv-estoque ${classe}`;
    atualizarFaixas(faixas, item.custo, item.preco);
    atualizarConta();
  }

  qtd.addEventListener("input", () => {
    item.qtd = Math.max(1, parseInt(qtd.value, 10) || 1);
    atualizar();
  });
  preco.addEventListener("input", () => {
    preco.removeAttribute("aria-invalid");
    item.preco = paraCentavos(preco.value);
    atualizar();
  });
  criarPasso(qtd, 1);

  li.append(topo, estoque, linha, faixas);
  li.atualizar = atualizar;
  li.campoPreco = preco;
  atualizar();
  return li;
}

function desenharItens() {
  const lista = $("#fv-itens");
  lista.replaceChildren(...estado.itensVenda.map(linhaItem));
  busca.placeholder = estado.itensVenda.length ? "Adicionar outro produto" : "Buscar produto para adicionar";
  atualizarConta();
}

function atualizarConta() {
  const itens = estado.itensVenda;
  const conta = $("#fv-conta");
  const precosOk = itens.length && itens.every((i) => valido(i.preco));
  const c = lerCustosVenda();
  if (!precosOk || ![c.taxa_pct, c.frete, c.desconto].every(valido)) {
    conta.replaceChildren(
      el("p", "conta-dica", itens.length ? "Informe o valor final de cada produto para ver o lucro." : "Adicione pelo menos um produto.")
    );
    return;
  }
  const subtotal = itens.reduce((s, i) => s + i.qtd * i.preco, 0);
  const custo = itens.reduce((s, i) => s + i.qtd * i.custo, 0);
  const taxa = calcTaxa(subtotal, c.desconto, c.taxa_pct);
  const total = subtotal - c.desconto;
  const lucro = total - taxa - c.frete - custo;

  const linhas = [["Produtos", dinheiro(subtotal)]];
  if (c.desconto) linhas.push(["Desconto", `− ${dinheiro(c.desconto)}`]);
  if (c.desconto) linhas.push(["Cliente paga", dinheiro(total)]);
  if (taxa) linhas.push([`Taxa (${paraTexto(c.taxa_pct)}%)`, `− ${dinheiro(taxa)}`]);
  if (c.frete) linhas.push(["Frete pago por você", `− ${dinheiro(c.frete)}`]);
  linhas.push(["Custo dos produtos", `− ${dinheiro(custo)}`]);

  const partes = linhas.map(([k, v]) => {
    const d = el("div");
    d.append(el("dt", null, k), el("dd", null, v));
    return d;
  });
  const final = el("div", "conta-lucro");
  const margem = total ? ` (${porcento((lucro / total) * 100)})` : "";
  final.append(el("dt", null, "Lucro"), el("dd", sinal(lucro), dinheiro(lucro) + margem));
  conta.replaceChildren(...partes, final);
}

function itemDeProduto(p) {
  return { produto_id: p.id, nome: p.nome, foto_url: p.foto_url, custo: p.custo, qtd: 1, preco: null, disponivel: p.estoque };
}

function adicionarProduto(p) {
  const existente = estado.itensVenda.find((i) => i.produto_id === p.id);
  busca.value = "";
  fecharResultados();
  if (existente) {
    existente.qtd += 1;
    desenharItens();
    return;
  }
  estado.itensVenda.push(itemDeProduto(p));
  desenharItens();
  $("#fv-itens").lastElementChild.campoPreco.focus();
}

function desenharResultados() {
  const achados = buscarProdutos(busca.value).slice(0, 8);
  if (!achados.length) {
    resultados.replaceChildren(el("li", "resultado-vazio", `Nenhum produto com "${busca.value.trim()}".`));
  } else {
    resultados.replaceChildren(
      ...achados.map((p, n) => {
        const li = el("li", "resultado");
        li.id = `resultado-${p.id}`;
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", String(n === 0));
        const vendavel = p.custo != null;
        if (!vendavel) li.setAttribute("aria-disabled", "true");
        const texto = el("span", "resultado-texto");
        texto.append(
          el("span", "resultado-nome", p.nome),
          el("span", "resultado-info", vendavel ? `${textoEstoque(p.estoque)}, custo ${dinheiro(p.custo)}` : "Sem compra registrada")
        );
        li.append(miniatura(p.foto_url, p.nome), texto);
        if (vendavel) li.addEventListener("click", () => adicionarProduto(p));
        li.produto = vendavel ? p : null;
        return li;
      })
    );
  }
  resultados.hidden = false;
  busca.setAttribute("aria-expanded", "true");
}

function fecharResultados() {
  resultados.hidden = true;
  busca.setAttribute("aria-expanded", "false");
}

busca.addEventListener("input", desenharResultados);
busca.addEventListener("focus", desenharResultados);
busca.addEventListener("blur", () => setTimeout(fecharResultados, 150));
// Evita que tocar num resultado tire o foco da busca antes do clique.
resultados.addEventListener("mousedown", (e) => e.preventDefault());
busca.addEventListener("keydown", (e) => {
  const opcoes = $$(".resultado", resultados);
  const atual = opcoes.findIndex((o) => o.getAttribute("aria-selected") === "true");
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    if (!opcoes.length) return;
    const prox = (atual + (e.key === "ArrowDown" ? 1 : -1) + opcoes.length) % opcoes.length;
    opcoes.forEach((o, n) => o.setAttribute("aria-selected", String(n === prox)));
    busca.setAttribute("aria-activedescendant", opcoes[prox].id);
  } else if (e.key === "Enter") {
    e.preventDefault();
    const p = opcoes[Math.max(0, atual)]?.produto;
    if (p) adicionarProduto(p);
  } else if (e.key === "Escape" && !resultados.hidden) {
    e.preventDefault();
    fecharResultados();
  }
});

async function abrirVenda(venda = null) {
  try {
    await carregarProdutos();
  } catch (err) {
    if (!(err instanceof ErroLogin)) alertarTela(`Não foi possível carregar os produtos (${err.message}).`);
    return;
  }
  estado.vendaEditando = venda;
  formVenda.reset();
  limparInvalidos(formVenda);
  mostrarErro(formVenda, "");
  prepararExcluir(formVenda, !!venda);
  fecharResultados();

  const semProdutos = estado.produtos.length === 0 && !venda;
  $("#fv-sem-produtos").hidden = !semProdutos;
  $("#fv-campos").hidden = semProdutos;

  $("#fv-titulo").textContent = venda ? "Editar venda" : "Nova venda";
  formVenda.cliente.value = venda?.cliente ?? "";
  formVenda.data_venda.value = venda?.data_venda ?? hojeISO();
  formVenda.forma_pagamento.value = venda?.forma_pagamento ?? "pix";
  const taxa = venda ? venda.taxa_pct : taxasLembradas()[formVenda.forma_pagamento.value];
  formVenda.taxa_pct.value = taxa ? paraTexto(taxa) : "";
  formVenda.frete.value = venda?.frete ? paraTexto(venda.frete) : "";
  formVenda.desconto.value = venda?.desconto ? paraTexto(venda.desconto) : "";
  $(`input[name=pagamento][value=${venda?.pagamento ?? "pendente"}]`, formVenda).checked = true;
  $(`input[name=entrega][value=${venda?.entrega ?? "a_enviar"}]`, formVenda).checked = true;
  formVenda.cancelada.checked = !!venda?.cancelada;
  $("#fv-cancelada-campo").hidden = !venda;

  // Item já vendido mantém o custo gravado; o disponível inclui o que esta venda já reservou.
  estado.itensVenda = (venda?.itens ?? []).map((i) => {
    const p = estado.produtos.find((x) => x.id === i.produto_id);
    const reservado = venda.cancelada ? 0 : i.qtd;
    return {
      produto_id: i.produto_id, nome: i.produto, foto_url: p?.foto_url, custo: i.custo,
      qtd: i.qtd, preco: i.preco, disponivel: (p?.estoque ?? 0) + reservado,
    };
  });
  desenharItens();

  folhaVenda.showModal();
  if (!venda && !semProdutos) formVenda.cliente.focus();
}

function alertarTela(msg) {
  const alvo = $(`#tela-${estado.tela} .vazio`);
  alvo.hidden = false;
  alvo.textContent = msg;
}

formVenda.forma_pagamento.addEventListener("change", () => {
  const taxa = taxasLembradas()[formVenda.forma_pagamento.value];
  formVenda.taxa_pct.value = taxa ? paraTexto(taxa) : "";
  atualizarConta();
});

formVenda.addEventListener("input", (e) => {
  e.target.removeAttribute?.("aria-invalid");
  if (["taxa_pct", "frete", "desconto"].includes(e.target.name)) atualizarConta();
});
formVenda.cancelada.addEventListener("change", () => $$("#fv-itens > li").forEach((li) => li.atualizar()));

ligarFolha(folhaVenda);

$("#fv-ir-produto").addEventListener("click", () => {
  folhaVenda.close();
  location.hash = "#produtos";
  abrirProduto();
});

formVenda.addEventListener("submit", (e) => {
  e.preventDefault();
  const v = validador(formVenda);
  const custos = lerCustosVenda();
  const dados = {
    cliente: formVenda.cliente.value.trim(),
    data_venda: formVenda.data_venda.value,
    forma_pagamento: formVenda.forma_pagamento.value,
    ...custos,
    pagamento: $("input[name=pagamento]:checked", formVenda).value,
    entrega: $("input[name=entrega]:checked", formVenda).value,
    cancelada: cancelada(),
    itens: estado.itensVenda.map((i) => ({ produto_id: i.produto_id, qtd: i.qtd, preco: i.preco })),
  };
  if (!dados.cliente) v.marcar(formVenda.cliente, "Informe o cliente.");
  if (!dados.data_venda) v.marcar(formVenda.data_venda, "Informe a data da venda.");
  if (!dados.itens.length) v.marcar(busca, "Adicione pelo menos um produto.");
  $$("#fv-itens > li").forEach((li, n) => {
    if (!valido(estado.itensVenda[n].preco)) v.marcar(li.campoPreco, `Informe o valor final de ${estado.itensVenda[n].nome}.`);
  });
  if (!valido(custos.taxa_pct) || custos.taxa_pct > 10000) v.marcar(formVenda.taxa_pct, "Taxa inválida. Use o formato 4,99.");
  if (!valido(custos.frete)) v.marcar(formVenda.frete, "Frete inválido. Use o formato 25,00.");
  if (!valido(custos.desconto)) v.marcar(formVenda.desconto, "Desconto inválido. Use o formato 10,00.");
  if (v.falhou()) return;

  enviar(formVenda, async () => {
    const id = estado.vendaEditando?.id;
    await api(id ? `/api/vendas/${id}` : "/api/vendas", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(dados),
    });
    localStorage.setItem("taxas", JSON.stringify({ ...taxasLembradas(), [dados.forma_pagamento]: dados.taxa_pct }));
    // Venda lançada em outro mês: pula para ele para que apareça na lista.
    if (estado.mes && dados.data_venda.slice(0, 7) !== estado.mes) {
      estado.mes = dados.data_venda.slice(0, 7);
      desenharMes();
    }
    folhaVenda.close();
    await recarregar();
  });
});

ligarExcluir(formVenda, async () => {
  await api(`/api/vendas/${estado.vendaEditando.id}`, { method: "DELETE" });
  folhaVenda.close();
  await recarregar();
});

/* ---------- Início do app ---------- */

$("#nova").addEventListener("click", () => (estado.tela === "produtos" ? abrirProduto() : abrirVenda()));

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

desenharMes();
desenharFiltros();
api("/api/eu").then(iniciarApp, (err) => {
  if (!(err instanceof ErroLogin)) mostrarLogin();
});
