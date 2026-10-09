"""Controle de vendas de importação — API + frontend estático."""

import csv
import io
import os
import secrets
import sqlite3
from datetime import date
from enum import Enum
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from . import auth, db
from .calculos import MARKUPS, custo_do_estoque, custo_unit_lote, dividir, partes_lote, precos, taxa

STATIC_DIR = Path(__file__).parent / "static"
MES_PATTERN = r"^\d{4}-\d{2}$"
ESTOQUE_BAIXO = 2
FOTO_MAX = 1_500_000
POR_PAGINA = 30


# ---------- Modelos ----------

class Moeda(str, Enum):
    USD = "USD"
    BRL = "BRL"


class FormaPagamento(str, Enum):
    pix = "pix"
    dinheiro = "dinheiro"
    debito = "debito"
    credito = "credito"
    link = "link"
    outro = "outro"


class Pagamento(str, Enum):
    pendente = "pendente"
    pago = "pago"


class Entrega(str, Enum):
    a_enviar = "a_enviar"
    enviado = "enviado"
    entregue = "entregue"


class Filtro(str, Enum):
    a_receber = "a_receber"
    a_enviar = "a_enviar"
    enviado = "enviado"
    entregue = "entregue"
    cancelada = "cancelada"


class LoteIn(BaseModel):
    data_compra: date
    qtd: int = Field(ge=1)
    moeda: Moeda = Moeda.USD
    preco_unit: int = Field(ge=0, description="Preço unitário na moeda, em centavos")
    cambio: int = Field(default=10000, ge=1, description="Reais por unidade da moeda, x10000")
    frete_internacional: int = Field(default=0, ge=0)
    impostos: int = Field(default=0, ge=0)
    frete_nacional: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def real_sem_cambio(self):
        if self.moeda == Moeda.BRL:
            self.cambio = 10000
        return self


class ProdutoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    observacao: str = Field(default="", max_length=2000)


class ProdutoNovo(ProdutoIn):
    compra: LoteIn | None = None


class ItemIn(BaseModel):
    produto_id: int
    qtd: int = Field(ge=1)
    preco: int = Field(ge=0, description="Preço final unitário em centavos")


class VendaIn(BaseModel):
    cliente: str = Field(min_length=1, max_length=120)
    data_venda: date
    itens: list[ItemIn] = Field(min_length=1, max_length=50)
    forma_pagamento: FormaPagamento = FormaPagamento.pix
    taxa_pct: int = Field(default=0, ge=0, le=10000, description="Centésimos de %")
    frete: int = Field(default=0, ge=0, description="Frete pago pelo vendedor")
    desconto: int = Field(default=0, ge=0)
    pagamento: Pagamento = Pagamento.pendente
    entrega: Entrega = Entrega.a_enviar
    cancelada: bool = False

    @model_validator(mode="after")
    def desconto_ate_subtotal(self):
        if self.desconto > sum(i.qtd * i.preco for i in self.itens):
            raise ValueError("O desconto não pode ser maior que o valor dos produtos.")
        return self


class Login(BaseModel):
    usuario: str = Field(min_length=1, max_length=80)
    senha: str = Field(min_length=1, max_length=200)


# ---------- App ----------

db.iniciar()
if not auth.existe_usuario() and os.getenv("ADMIN_USER") and os.getenv("ADMIN_PASSWORD"):
    auth.criar_usuario(os.environ["ADMIN_USER"], os.environ["ADMIN_PASSWORD"])

app = FastAPI(title="Vendas", docs_url=None, redoc_url=None, openapi_url=None)
api = APIRouter(prefix="/api", dependencies=[Depends(auth.usuario_atual)])

CSP = (
    "default-src 'self'; img-src 'self' blob: data:; "
    "style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


@app.middleware("http")
async def cabecalhos_seguranca(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Content-Security-Policy"] = CSP
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


# ---------- Login ----------

@app.post("/api/login")
def login(dados: Login, request: Request, response: Response):
    ip = request.client.host if request.client else "?"
    if auth.limite.bloqueado(dados.usuario, ip):
        raise HTTPException(429, "Muitas tentativas. Aguarde 15 minutos e tente de novo.")
    usuario_id = auth.autenticar(dados.usuario, dados.senha)
    if usuario_id is None:
        auth.limite.falhou(dados.usuario, ip)
        raise HTTPException(401, "Usuário ou senha incorretos.")
    auth.limite.acertou(dados.usuario)
    response.set_cookie(
        auth.COOKIE,
        auth.abrir_sessao(usuario_id),
        max_age=auth.DURACAO_SESSAO,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )
    return {"usuario": dados.usuario.strip()}


@app.post("/api/logout", status_code=204)
def logout(request: Request, response: Response):
    if token := request.cookies.get(auth.COOKIE):
        auth.fechar_sessao(token)
    response.delete_cookie(auth.COOKIE, path="/")


@api.get("/eu")
def eu(usuario: str = Depends(auth.usuario_atual)):
    return {"usuario": usuario}


# ---------- Produtos ----------

def foto_url(row) -> str | None:
    return f"/api/produtos/{row['id']}/foto?v={row['foto']}" if row["foto"] else None


def lote_out(lote: sqlite3.Row) -> dict:
    partes = partes_lote(lote)
    return {
        **dict(lote),
        "partes": partes,
        "custo_total": sum(partes.values()),
        "custo_unit": custo_unit_lote(lote),
    }


def carregar_produtos(conn, produto_id: int | None = None, com_lotes=False) -> list[dict]:
    where, params = ("WHERE p.id = ?", (produto_id,)) if produto_id else ("", ())
    produtos = conn.execute(
        f"""
        SELECT p.*,
               COALESCE((SELECT SUM(qtd) FROM lotes l WHERE l.produto_id = p.id), 0) AS comprados,
               COALESCE((SELECT SUM(i.qtd) FROM venda_itens i JOIN vendas v ON v.id = i.venda_id
                         WHERE i.produto_id = p.id AND v.cancelada = 0), 0) AS vendidos,
               (SELECT COUNT(*) FROM venda_itens i WHERE i.produto_id = p.id) AS vendas
        FROM produtos p {where}
        ORDER BY p.nome COLLATE NOCASE
        """,
        params,
    ).fetchall()
    lotes_sql = "SELECT * FROM lotes" + (" WHERE produto_id = ?" if produto_id else "")
    lotes: dict[int, list] = {}
    for lote in conn.execute(lotes_sql + " ORDER BY data_compra, id", params):
        lotes.setdefault(lote["produto_id"], []).append(lote)

    saida = []
    for p in produtos:
        estoque = p["comprados"] - p["vendidos"]
        lotes_p = lotes.get(p["id"], [])
        custo, valor = custo_do_estoque(lotes_p, estoque)
        item = {
            "id": p["id"],
            "nome": p["nome"],
            "observacao": p["observacao"],
            "foto_url": foto_url(p),
            "estoque": estoque,
            "custo": custo,
            "precos": precos(custo),
            "valor_estoque": valor,
            "vendas": p["vendas"],
            "ultima_compra": lotes_p[-1]["data_compra"] if lotes_p else None,
        }
        if com_lotes:
            item["lotes"] = [lote_out(l) for l in reversed(lotes_p)]
        saida.append(item)
    return saida


def buscar_produto(conn, produto_id: int, com_lotes=True) -> dict:
    achados = carregar_produtos(conn, produto_id, com_lotes)
    if not achados:
        raise HTTPException(404, "Produto não encontrado")
    return achados[0]


def inserir_lote(conn, produto_id: int, l: LoteIn) -> int:
    cur = conn.execute(
        """INSERT INTO lotes (produto_id, data_compra, qtd, moeda, preco_unit, cambio,
                              frete_internacional, impostos, frete_nacional)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (produto_id, l.data_compra.isoformat(), l.qtd, l.moeda.value, l.preco_unit, l.cambio,
         l.frete_internacional, l.impostos, l.frete_nacional),
    )
    return cur.lastrowid


@api.get("/produtos")
def listar_produtos():
    with db.conectar() as conn:
        return carregar_produtos(conn)


@api.get("/produtos/{produto_id}")
def detalhar_produto(produto_id: int):
    with db.conectar() as conn:
        return buscar_produto(conn, produto_id)


@api.post("/produtos", status_code=201)
def criar_produto(p: ProdutoNovo):
    with db.conectar() as conn:
        cur = conn.execute(
            "INSERT INTO produtos (nome, observacao) VALUES (?, ?)", (p.nome.strip(), p.observacao.strip())
        )
        if p.compra:
            inserir_lote(conn, cur.lastrowid, p.compra)
        return buscar_produto(conn, cur.lastrowid)


@api.put("/produtos/{produto_id}")
def atualizar_produto(produto_id: int, p: ProdutoIn):
    with db.conectar() as conn:
        buscar_produto(conn, produto_id, com_lotes=False)
        conn.execute(
            "UPDATE produtos SET nome = ?, observacao = ? WHERE id = ?",
            (p.nome.strip(), p.observacao.strip(), produto_id),
        )
        return buscar_produto(conn, produto_id)


def apagar_arquivo_foto(nome: str | None):
    if nome:
        (db.pasta_fotos() / nome).unlink(missing_ok=True)


@api.delete("/produtos/{produto_id}", status_code=204)
def excluir_produto(produto_id: int):
    with db.conectar() as conn:
        p = buscar_produto(conn, produto_id, com_lotes=False)
        if p["vendas"]:
            raise HTTPException(409, "Este produto já tem vendas registradas e não pode ser excluído.")
        foto = conn.execute("SELECT foto FROM produtos WHERE id = ?", (produto_id,)).fetchone()["foto"]
        conn.execute("DELETE FROM produtos WHERE id = ?", (produto_id,))
    apagar_arquivo_foto(foto)


@api.put("/produtos/{produto_id}/foto")
def enviar_foto(produto_id: int, foto: UploadFile = File(...)):
    conteudo = foto.file.read(FOTO_MAX + 1)
    if len(conteudo) > FOTO_MAX:
        raise HTTPException(413, "Foto muito grande. O limite é 1,5 MB.")
    # O frontend sempre reduz e converte para JPEG antes de enviar.
    if not conteudo.startswith(b"\xff\xd8\xff"):
        raise HTTPException(415, "Envie a foto em JPEG.")
    nome = f"{produto_id}-{secrets.token_hex(6)}.jpg"
    with db.conectar() as conn:
        buscar_produto(conn, produto_id, com_lotes=False)
        antiga = conn.execute("SELECT foto FROM produtos WHERE id = ?", (produto_id,)).fetchone()["foto"]
        (db.pasta_fotos() / nome).write_bytes(conteudo)
        conn.execute("UPDATE produtos SET foto = ? WHERE id = ?", (nome, produto_id))
        produto = buscar_produto(conn, produto_id)
    apagar_arquivo_foto(antiga)
    return produto


@api.delete("/produtos/{produto_id}/foto", status_code=204)
def remover_foto(produto_id: int):
    with db.conectar() as conn:
        buscar_produto(conn, produto_id, com_lotes=False)
        antiga = conn.execute("SELECT foto FROM produtos WHERE id = ?", (produto_id,)).fetchone()["foto"]
        conn.execute("UPDATE produtos SET foto = NULL WHERE id = ?", (produto_id,))
    apagar_arquivo_foto(antiga)


@api.get("/produtos/{produto_id}/foto")
def ver_foto(produto_id: int):
    with db.conectar() as conn:
        row = conn.execute("SELECT foto FROM produtos WHERE id = ?", (produto_id,)).fetchone()
    if not row or not row["foto"]:
        raise HTTPException(404, "Produto sem foto")
    # O nome do arquivo muda a cada envio, então pode ficar em cache por bastante tempo.
    return FileResponse(
        db.pasta_fotos() / row["foto"],
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


# ---------- Compras (lotes) ----------

@api.post("/produtos/{produto_id}/lotes", status_code=201)
def criar_lote(produto_id: int, l: LoteIn):
    with db.conectar() as conn:
        buscar_produto(conn, produto_id, com_lotes=False)
        inserir_lote(conn, produto_id, l)
        return buscar_produto(conn, produto_id)


def produto_do_lote(conn, lote_id: int) -> int:
    row = conn.execute("SELECT produto_id FROM lotes WHERE id = ?", (lote_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Compra não encontrada")
    return row["produto_id"]


@api.put("/lotes/{lote_id}")
def atualizar_lote(lote_id: int, l: LoteIn):
    with db.conectar() as conn:
        produto_id = produto_do_lote(conn, lote_id)
        conn.execute(
            """UPDATE lotes SET data_compra=?, qtd=?, moeda=?, preco_unit=?, cambio=?,
                                frete_internacional=?, impostos=?, frete_nacional=?
               WHERE id = ?""",
            (l.data_compra.isoformat(), l.qtd, l.moeda.value, l.preco_unit, l.cambio,
             l.frete_internacional, l.impostos, l.frete_nacional, lote_id),
        )
        return buscar_produto(conn, produto_id)


@api.delete("/lotes/{lote_id}")
def excluir_lote(lote_id: int):
    with db.conectar() as conn:
        produto_id = produto_do_lote(conn, lote_id)
        conn.execute("DELETE FROM lotes WHERE id = ?", (lote_id,))
        return buscar_produto(conn, produto_id)


# ---------- Vendas ----------

def filtrar_vendas(mes: str | None, filtro: Filtro | None) -> tuple[str, list]:
    where, params = [], []
    if mes:
        where.append("substr(data_venda, 1, 7) = ?")
        params.append(mes)
    if filtro == Filtro.cancelada:
        where.append("cancelada = 1")
    elif filtro:
        where.append("cancelada = 0")
        if filtro == Filtro.a_receber:
            where.append("pagamento = 'pendente'")
        else:
            where.append("entrega = ?")
            params.append(filtro.value)
    return (" WHERE " + " AND ".join(where)) if where else "", params


def montar_vendas(conn, rows: list[sqlite3.Row]) -> list[dict]:
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    itens: dict[int, list] = {}
    marcadores = ",".join("?" * len(ids))
    for i in conn.execute(f"SELECT * FROM venda_itens WHERE venda_id IN ({marcadores}) ORDER BY id", ids):
        itens.setdefault(i["venda_id"], []).append(
            {"produto_id": i["produto_id"], "produto": i["produto"], "qtd": i["qtd"],
             "custo": i["custo"], "preco": i["preco"], "precos": precos(i["custo"])}
        )
    return [{**dict(r), "cancelada": bool(r["cancelada"]), "itens": itens.get(r["id"], [])} for r in rows]


def buscar_venda(conn, venda_id: int) -> dict:
    row = conn.execute("SELECT * FROM v_vendas WHERE id = ?", (venda_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Venda não encontrada")
    return montar_vendas(conn, [row])[0]


@api.get("/vendas")
def listar_vendas(
    mes: str | None = Query(default=None, pattern=MES_PATTERN),
    filtro: Filtro | None = None,
    offset: int = Query(default=0, ge=0),
    limite: int = Query(default=POR_PAGINA, ge=1, le=200),
):
    where, params = filtrar_vendas(mes, filtro)
    with db.conectar() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM vendas{where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM v_vendas{where} ORDER BY data_venda DESC, id DESC LIMIT ? OFFSET ?",
            [*params, limite, offset],
        ).fetchall()
        return {"vendas": montar_vendas(conn, rows), "total": total}


@api.get("/resumo")
def resumo(mes: str | None = Query(default=None, pattern=MES_PATTERN)):
    """Totais do período, ignorando vendas canceladas."""
    where, params = filtrar_vendas(mes, None)
    where += (" AND " if where else " WHERE ") + "cancelada = 0"
    with db.conectar() as conn:
        r = conn.execute(
            f"""
            SELECT COUNT(*) AS vendas,
                   COALESCE(SUM(itens), 0) AS itens,
                   COALESCE(SUM(total), 0) AS vendido,
                   COALESCE(SUM(lucro), 0) AS lucro,
                   COALESCE(SUM(CASE WHEN pagamento = 'pendente' THEN total END), 0) AS a_receber
            FROM v_vendas{where}
            """,
            params,
        ).fetchone()
    return dict(r)


def gravar_venda(conn, v: VendaIn, venda_id: int | None = None) -> int:
    # Item de produto que já estava na venda mantém o custo gravado; produto novo usa o custo atual.
    custos_anteriores = {}
    if venda_id:
        for i in conn.execute("SELECT produto_id, produto, custo FROM venda_itens WHERE venda_id = ?", (venda_id,)):
            custos_anteriores[i["produto_id"]] = (i["produto"], i["custo"])

    linhas = []
    for item in v.itens:
        if item.produto_id in custos_anteriores:
            nome, custo = custos_anteriores[item.produto_id]
        else:
            p = buscar_produto(conn, item.produto_id, com_lotes=False)
            if p["custo"] is None:
                raise HTTPException(409, f"Registre uma compra de {p['nome']} antes de vender.")
            nome, custo = p["nome"], p["custo"]
        linhas.append((item.produto_id, nome, item.qtd, custo, item.preco))

    subtotal = sum(i.qtd * i.preco for i in v.itens)
    campos = (v.cliente.strip(), v.data_venda.isoformat(), v.forma_pagamento.value, v.taxa_pct,
              taxa(subtotal, v.desconto, v.taxa_pct), v.frete, v.desconto,
              v.pagamento.value, v.entrega.value, int(v.cancelada))
    if venda_id:
        conn.execute(
            """UPDATE vendas SET cliente=?, data_venda=?, forma_pagamento=?, taxa_pct=?, taxa=?, frete=?,
                                 desconto=?, pagamento=?, entrega=?, cancelada=?
               WHERE id = ?""",
            (*campos, venda_id),
        )
        conn.execute("DELETE FROM venda_itens WHERE venda_id = ?", (venda_id,))
    else:
        venda_id = conn.execute(
            """INSERT INTO vendas (cliente, data_venda, forma_pagamento, taxa_pct, taxa, frete,
                                   desconto, pagamento, entrega, cancelada)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            campos,
        ).lastrowid
    conn.executemany(
        "INSERT INTO venda_itens (venda_id, produto_id, produto, qtd, custo, preco) VALUES (?, ?, ?, ?, ?, ?)",
        [(venda_id, *linha) for linha in linhas],
    )
    return venda_id


@api.post("/vendas", status_code=201)
def criar_venda(v: VendaIn):
    with db.conectar() as conn:
        return buscar_venda(conn, gravar_venda(conn, v))


@api.put("/vendas/{venda_id}")
def atualizar_venda(venda_id: int, v: VendaIn):
    with db.conectar() as conn:
        buscar_venda(conn, venda_id)
        return buscar_venda(conn, gravar_venda(conn, v, venda_id))


@api.delete("/vendas/{venda_id}", status_code=204)
def excluir_venda(venda_id: int):
    with db.conectar() as conn:
        buscar_venda(conn, venda_id)
        conn.execute("DELETE FROM vendas WHERE id = ?", (venda_id,))


def reais(centavos: int | None) -> str:
    return "" if centavos is None else f"{centavos / 100:.2f}".replace(".", ",")


ROTULOS = {
    "pendente": "a receber", "pago": "pago",
    "a_enviar": "a enviar", "enviado": "enviado", "entregue": "entregue",
}


@api.get("/vendas.csv")
def exportar_csv(
    mes: str | None = Query(default=None, pattern=MES_PATTERN),
    filtro: Filtro | None = None,
):
    """Uma linha por item. Desconto, taxa e frete da venda são rateados pelo valor de cada item,
    para que a soma das colunas bata com o total das vendas."""
    where, params = filtrar_vendas(mes, filtro)
    with db.conectar() as conn:
        rows = conn.execute(f"SELECT * FROM v_vendas{where} ORDER BY data_venda, id", params).fetchall()
        vendas = montar_vendas(conn, rows)

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Venda", "Cliente", "Data Venda", "Produto", "Custo", "Preço +50%", "Preço +60%",
                "Preço +70%", "Valor Vendido", "Qtd", "Desconto, taxa e frete", "Lucro",
                "Pagamento", "Entrega", "Cancelada"])
    for v in vendas:
        extras = v["desconto"] + v["taxa"] + v["frete"]
        restante = extras
        for n, i in enumerate(v["itens"]):
            bruto = i["qtd"] * i["preco"]
            ultimo = n == len(v["itens"]) - 1
            parte = restante if ultimo else (dividir(extras * bruto, v["subtotal"]) if v["subtotal"] else 0)
            restante -= parte
            w.writerow([
                v["id"], v["cliente"], date.fromisoformat(v["data_venda"]).strftime("%d/%m/%Y"),
                i["produto"], reais(i["custo"]), *(reais(i["precos"][str(p)]) for p in MARKUPS),
                reais(i["preco"]), i["qtd"], reais(parte), reais(bruto - i["qtd"] * i["custo"] - parte),
                ROTULOS[v["pagamento"]], ROTULOS[v["entrega"]], "sim" if v["cancelada"] else "não",
            ])
    nome = f"vendas-{mes or 'todas'}.csv"
    # BOM para o Excel abrir acentos corretamente
    return StreamingResponse(
        iter(["﻿" + buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


# ---------- Painel ----------

@api.get("/painel")
def painel(hoje: date = Query(description="Data local do usuário, para o lucro do dia")):
    dia = hoje.isoformat()
    with db.conectar() as conn:
        produtos = carregar_produtos(conn)
        totais = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN data_venda = :dia THEN lucro END), 0) AS lucro_dia,
                COALESCE(SUM(CASE WHEN data_venda = :dia THEN total END), 0) AS vendido_dia,
                COUNT(CASE WHEN data_venda = :dia THEN 1 END) AS vendas_dia,
                COALESCE(SUM(CASE WHEN substr(data_venda, 1, 7) = :mes THEN lucro END), 0) AS lucro_mes,
                COALESCE(SUM(CASE WHEN substr(data_venda, 1, 7) = :mes THEN total END), 0) AS vendido_mes,
                COUNT(CASE WHEN substr(data_venda, 1, 7) = :mes THEN 1 END) AS vendas_mes,
                COALESCE(SUM(CASE WHEN pagamento = 'pendente' THEN total END), 0) AS a_receber,
                COUNT(CASE WHEN pagamento = 'pendente' THEN 1 END) AS vendas_a_receber,
                COUNT(CASE WHEN entrega = 'a_enviar' THEN 1 END) AS a_enviar
            FROM v_vendas
            WHERE cancelada = 0
            """,
            {"dia": dia, "mes": dia[:7]},
        ).fetchone()
        recentes = montar_vendas(
            conn, conn.execute("SELECT * FROM v_vendas ORDER BY data_venda DESC, id DESC LIMIT 5").fetchall()
        )

    em_estoque = [p for p in produtos if p["estoque"] > 0]
    return {
        **dict(totais),
        "estoque_itens": sum(p["estoque"] for p in em_estoque),
        "estoque_valor": sum(p["valor_estoque"] for p in em_estoque),
        "estoque_produtos": len(em_estoque),
        "estoque_baixo": sorted((p for p in produtos if p["estoque"] <= ESTOQUE_BAIXO), key=lambda p: p["estoque"]),
        "recentes": recentes,
    }


app.include_router(api)


# ---------- Arquivos do app ----------

@app.get("/healthz", include_in_schema=False)
def healthz():
    """Usado pelo HEALTHCHECK do Docker: confirma que o banco abre e responde."""
    with db.conectar() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"ok": True}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    # Precisa ficar na raiz para controlar o app inteiro.
    return FileResponse(STATIC_DIR / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
