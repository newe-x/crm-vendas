"""Conexão e esquema do SQLite."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path



def caminho_db() -> Path:
    return Path(os.getenv("DB_PATH", Path(__file__).parent.parent / "data" / "vendas.db"))


def pasta_fotos() -> Path:
    return caminho_db().parent / "fotos"


VERSAO_ESQUEMA = 2

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
    senha_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessoes (
    token_hash TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    expira_em INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    observacao TEXT NOT NULL DEFAULT '',
    foto TEXT
);

-- Cada compra (lote) tem seu próprio custo. Valores em centavos; câmbio x10000.
-- Fretes e impostos são o total pago pelo lote, não por unidade.
CREATE TABLE IF NOT EXISTS lotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id INTEGER NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    data_compra TEXT NOT NULL,
    qtd INTEGER NOT NULL,
    moeda TEXT NOT NULL DEFAULT 'USD',
    preco_unit INTEGER NOT NULL,
    cambio INTEGER NOT NULL DEFAULT 10000,
    frete_internacional INTEGER NOT NULL DEFAULT 0,
    impostos INTEGER NOT NULL DEFAULT 0,
    frete_nacional INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_lotes_produto ON lotes(produto_id, data_compra);

-- taxa é o valor em centavos calculado de taxa_pct (centésimos de %) ao salvar.
CREATE TABLE IF NOT EXISTS vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente TEXT NOT NULL,
    data_venda TEXT NOT NULL,
    forma_pagamento TEXT NOT NULL DEFAULT 'pix',
    taxa_pct INTEGER NOT NULL DEFAULT 0,
    taxa INTEGER NOT NULL DEFAULT 0,
    frete INTEGER NOT NULL DEFAULT 0,
    desconto INTEGER NOT NULL DEFAULT 0,
    pagamento TEXT NOT NULL DEFAULT 'pendente',
    entrega TEXT NOT NULL DEFAULT 'a_enviar',
    cancelada INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_vendas_data ON vendas(data_venda);

-- produto e custo ficam gravados no item: mudar o produto depois
-- não reescreve o lucro de vendas antigas.
CREATE TABLE IF NOT EXISTS venda_itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id INTEGER NOT NULL REFERENCES vendas(id) ON DELETE CASCADE,
    produto_id INTEGER NOT NULL REFERENCES produtos(id) ON DELETE RESTRICT,
    produto TEXT NOT NULL,
    qtd INTEGER NOT NULL,
    custo INTEGER NOT NULL,
    preco INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_itens_venda ON venda_itens(venda_id);
CREATE INDEX IF NOT EXISTS idx_itens_produto ON venda_itens(produto_id);

DROP VIEW IF EXISTS v_vendas;
CREATE VIEW v_vendas AS
SELECT v.*,
       COALESCE(i.subtotal, 0) AS subtotal,
       COALESCE(i.custo_itens, 0) AS custo_itens,
       COALESCE(i.itens, 0) AS itens,
       COALESCE(i.subtotal, 0) - v.desconto AS total,
       COALESCE(i.subtotal, 0) - v.desconto - v.taxa - v.frete - COALESCE(i.custo_itens, 0) AS lucro
FROM vendas v
LEFT JOIN (
    SELECT venda_id, SUM(qtd * preco) AS subtotal, SUM(qtd * custo) AS custo_itens, SUM(qtd) AS itens
    FROM venda_itens GROUP BY venda_id
) i ON i.venda_id = v.id;
"""


@contextmanager
def conectar():
    conn = sqlite3.connect(caminho_db())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def iniciar():
    pasta_fotos().mkdir(parents=True, exist_ok=True)
    with conectar() as conn:
        versao = conn.execute("PRAGMA user_version").fetchone()[0]
        tabelas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if versao < VERSAO_ESQUEMA and "vendas" in tabelas:
            # Esquema da primeira versão (uma venda = um produto). Só descarta se estiver vazio.
            if conn.execute("SELECT COUNT(*) FROM vendas").fetchone()[0] or conn.execute(
                "SELECT COUNT(*) FROM produtos"
            ).fetchone()[0]:
                raise RuntimeError("Banco da versão 1 com dados: migração não implementada.")
            conn.executescript("DROP TABLE vendas; DROP TABLE produtos;")
        conn.executescript(ESQUEMA)
        conn.execute(f"PRAGMA user_version = {VERSAO_ESQUEMA}")
