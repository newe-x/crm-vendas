import importlib

import pytest
from fastapi.testclient import TestClient

SENHA = "senha-de-teste-123"


def carregar_app(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "teste.db"))
    import app.auth
    import app.main

    importlib.reload(app.auth)
    main = importlib.reload(app.main)
    app.auth.criar_usuario("pedro", SENHA)
    return main


@pytest.fixture
def anon(tmp_path, monkeypatch):
    return TestClient(carregar_app(tmp_path, monkeypatch).app)


@pytest.fixture
def client(anon):
    assert anon.post("/api/login", json={"usuario": "pedro", "senha": SENHA}).status_code == 200
    return anon


COMPRA = {"data_compra": "2026-10-01", "qtd": 10, "moeda": "USD", "preco_unit": 2000,
          "cambio": 55000, "frete_internacional": 15000, "impostos": 50000, "frete_nacional": 5000}
# custo do lote: 20 USD x 10 x 5,50 = 1100,00 + 150 + 500 + 50 = 1800,00 -> 180,00/un


def novo_produto(client, nome="Fone JBL", compra=COMPRA):
    r = client.post("/api/produtos", json={"nome": nome, "observacao": "", "compra": compra})
    assert r.status_code == 201, r.text
    return r.json()


def nova_venda(client, itens, **extra):
    dados = {"cliente": "Maria", "data_venda": "2026-10-09", "itens": itens, **extra}
    r = client.post("/api/vendas", json=dados)
    assert r.status_code == 201, r.text
    return r.json()


# ---------- Login ----------

def test_api_exige_login(anon):
    assert anon.get("/api/produtos").status_code == 401
    assert anon.get("/").status_code == 200  # a tela de login é servida pelo app


def test_login_errado_e_bloqueio(anon):
    for _ in range(5):
        assert anon.post("/api/login", json={"usuario": "pedro", "senha": "errada"}).status_code == 401
    r = anon.post("/api/login", json={"usuario": "pedro", "senha": SENHA})
    assert r.status_code == 429


def test_logout_encerra_sessao(client):
    assert client.get("/api/eu").json() == {"usuario": "pedro"}
    client.post("/api/logout")
    assert client.get("/api/eu").status_code == 401


def test_cookie_httponly(anon):
    r = anon.post("/api/login", json={"usuario": "pedro", "senha": SENHA})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


# ---------- Produtos e compras ----------

def test_custo_composto_do_lote(client):
    p = novo_produto(client)
    lote = p["lotes"][0]
    assert lote["partes"] == {"produto": 110000, "frete_internacional": 15000,
                              "impostos": 50000, "frete_nacional": 5000}
    assert lote["custo_unit"] == 18000
    assert p["custo"] == 18000 and p["estoque"] == 10
    assert p["precos"] == {"50": 27000, "60": 28800, "70": 30600}


def test_compra_em_reais_ignora_cambio(client):
    p = novo_produto(client, compra={**COMPRA, "moeda": "BRL", "preco_unit": 10000, "cambio": 99999,
                                     "frete_internacional": 0, "impostos": 0, "frete_nacional": 0})
    assert p["custo"] == 10000


def test_estoque_vem_das_compras_mais_recentes(client):
    p = novo_produto(client)  # 10 un a 180,00
    client.post(f"/api/produtos/{p['id']}/lotes",
                json={**COMPRA, "data_compra": "2026-10-05", "qtd": 5, "preco_unit": 4000,
                      "frete_internacional": 0, "impostos": 0, "frete_nacional": 0})  # 5 un a 220,00
    nova_venda(client, [{"produto_id": p["id"], "qtd": 12, "preco": 30000}])
    p = client.get(f"/api/produtos/{p['id']}").json()
    # sobram 3, todas do lote mais recente
    assert p["estoque"] == 3
    assert p["custo"] == 22000
    assert p["valor_estoque"] == 66000


def test_excluir_produto(client):
    p = novo_produto(client)
    nova_venda(client, [{"produto_id": p["id"], "qtd": 1, "preco": 30000}])
    assert client.delete(f"/api/produtos/{p['id']}").status_code == 409
    q = novo_produto(client, "Outro")
    assert client.delete(f"/api/produtos/{q['id']}").status_code == 204


def test_foto(client):
    p = novo_produto(client)
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 100
    r = client.put(f"/api/produtos/{p['id']}/foto", files={"foto": ("f.jpg", jpeg, "image/jpeg")})
    assert r.status_code == 200
    url = r.json()["foto_url"]
    assert client.get(url).content == jpeg
    r = client.put(f"/api/produtos/{p['id']}/foto", files={"foto": ("x.svg", b"<svg/>", "image/svg+xml")})
    assert r.status_code == 415


# ---------- Vendas ----------

def test_venda_com_varios_itens_e_custos(client):
    a = novo_produto(client, "A")  # custo 180,00
    b = novo_produto(client, "B")
    v = nova_venda(
        client,
        [{"produto_id": a["id"], "qtd": 2, "preco": 30000}, {"produto_id": b["id"], "qtd": 1, "preco": 25000}],
        desconto=5000, taxa_pct=499, frete=2000, forma_pagamento="credito",
    )
    assert v["subtotal"] == 85000
    assert v["total"] == 80000
    assert v["taxa"] == 3992  # 4,99% de 800,00
    assert v["custo_itens"] == 54000
    assert v["lucro"] == 80000 - 3992 - 2000 - 54000
    assert len(v["itens"]) == 2


def test_desconto_maior_que_venda(client):
    a = novo_produto(client)
    r = client.post("/api/vendas", json={"cliente": "X", "data_venda": "2026-10-09", "desconto": 99999,
                                         "itens": [{"produto_id": a["id"], "qtd": 1, "preco": 100}]})
    assert r.status_code == 422


def test_produto_sem_compra_nao_vende(client):
    p = client.post("/api/produtos", json={"nome": "Sem compra"}).json()
    r = client.post("/api/vendas", json={"cliente": "X", "data_venda": "2026-10-09",
                                         "itens": [{"produto_id": p["id"], "qtd": 1, "preco": 100}]})
    assert r.status_code == 409


def test_editar_venda_mantem_custo_gravado(client):
    a = novo_produto(client)
    v = nova_venda(client, [{"produto_id": a["id"], "qtd": 1, "preco": 30000}])
    client.post(f"/api/produtos/{a['id']}/lotes", json={**COMPRA, "data_compra": "2026-10-08", "preco_unit": 9000})
    r = client.put(f"/api/vendas/{v['id']}", json={
        "cliente": "Maria", "data_venda": "2026-10-09", "pagamento": "pago",
        "itens": [{"produto_id": a["id"], "qtd": 2, "preco": 30000}]})
    assert r.json()["itens"][0]["custo"] == 18000


def test_cancelar_devolve_estoque(client):
    a = novo_produto(client)
    v = nova_venda(client, [{"produto_id": a["id"], "qtd": 4, "preco": 30000}])
    assert client.get(f"/api/produtos/{a['id']}").json()["estoque"] == 6
    client.put(f"/api/vendas/{v['id']}", json={
        "cliente": "Maria", "data_venda": "2026-10-09", "cancelada": True,
        "itens": [{"produto_id": a["id"], "qtd": 4, "preco": 30000}]})
    assert client.get(f"/api/produtos/{a['id']}").json()["estoque"] == 10


def test_filtros_e_paginacao(client):
    a = novo_produto(client, compra={**COMPRA, "qtd": 100})
    for n in range(35):
        nova_venda(client, [{"produto_id": a["id"], "qtd": 1, "preco": 30000}],
                   pagamento="pago" if n % 2 else "pendente", entrega="enviado" if n < 5 else "a_enviar")
    r = client.get("/api/vendas", params={"mes": "2026-10"}).json()
    assert r["total"] == 35 and len(r["vendas"]) == 30
    r = client.get("/api/vendas", params={"mes": "2026-10", "offset": 30}).json()
    assert len(r["vendas"]) == 5
    assert client.get("/api/vendas", params={"filtro": "a_receber"}).json()["total"] == 18
    assert client.get("/api/vendas", params={"filtro": "enviado"}).json()["total"] == 5


def test_painel(client):
    a = novo_produto(client)  # 10 un a 180,00
    nova_venda(client, [{"produto_id": a["id"], "qtd": 2, "preco": 30000}])                 # hoje, a receber
    nova_venda(client, [{"produto_id": a["id"], "qtd": 1, "preco": 30000}],
               data_venda="2026-10-01", pagamento="pago", entrega="entregue")              # mesmo mês
    nova_venda(client, [{"produto_id": a["id"], "qtd": 1, "preco": 30000}], data_venda="2026-09-30")
    nova_venda(client, [{"produto_id": a["id"], "qtd": 1, "preco": 30000}], cancelada=True)
    r = client.get("/api/painel", params={"hoje": "2026-10-09"}).json()
    assert r["lucro_dia"] == 24000
    assert r["lucro_mes"] == 36000
    assert r["a_receber"] == 90000 and r["vendas_a_receber"] == 2
    assert r["a_enviar"] == 2
    assert r["estoque_itens"] == 6 and r["estoque_valor"] == 108000


def test_csv_rateia_custos_da_venda(client):
    a = novo_produto(client, "A")
    b = novo_produto(client, "B")
    nova_venda(client, [{"produto_id": a["id"], "qtd": 1, "preco": 30000},
                        {"produto_id": b["id"], "qtd": 1, "preco": 10000}], desconto=1000, frete=1000)
    linhas = client.get("/api/vendas.csv").text.lstrip("﻿").splitlines()
    assert linhas[0].startswith("Venda;Cliente;Data Venda;Produto;Custo;Preço +50%")
    a_linha, b_linha = (l.split(";") for l in linhas[1:])
    assert a_linha[10] == "15,00" and b_linha[10] == "5,00"
    lucro_total = sum(float(l[11].replace(",", ".")) for l in (a_linha, b_linha))
    assert lucro_total == (40000 - 2000 - 36000) / 100
