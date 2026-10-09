# API

Todas as rotas ficam em `/api` e trocam JSON. **Dinheiro é sempre em centavos inteiros**; datas em `AAAA-MM-DD`; meses em `AAAA-MM`.

Exceto `/api/login` e `/api/logout`, toda rota exige o cookie de sessão `sessao` e responde `401` sem ele.

## Erros

| Código | Quando | Corpo |
|---|---|---|
| 401 | Sem sessão, sessão expirada ou senha errada | `{"detail": "mensagem"}` |
| 404 | Produto, compra ou venda inexistente | `{"detail": "mensagem"}` |
| 409 | Ação bloqueada por regra (excluir produto com vendas, vender produto sem compra) | `{"detail": "mensagem"}` |
| 413 / 415 | Foto acima de 1,5 MB / foto que não é JPEG | `{"detail": "mensagem"}` |
| 422 | Dados inválidos | `{"detail": [{"loc": [...], "msg": "..."}]}` |
| 429 | Muitas tentativas de login | `{"detail": "mensagem"}` |

## Login

| Método e rota | Corpo | Resposta |
|---|---|---|
| `POST /api/login` | `{"usuario", "senha"}` | `{"usuario"}` + cookie `sessao` (HttpOnly, SameSite=Lax, 30 dias) |
| `POST /api/logout` | | `204`, apaga a sessão |
| `GET /api/eu` | | `{"usuario"}` |

## Produtos

| Método e rota | Corpo | Resposta |
|---|---|---|
| `GET /api/produtos` | | Lista de Produto (sem `lotes`), por nome |
| `GET /api/produtos/{id}` | | Produto com `lotes` (mais recente primeiro) |
| `POST /api/produtos` | `{"nome", "observacao"?, "compra"?: Compra}` | `201`, Produto com `lotes` |
| `PUT /api/produtos/{id}` | `{"nome", "observacao"?}` | Produto com `lotes` |
| `DELETE /api/produtos/{id}` | | `204`; `409` se houver vendas |
| `PUT /api/produtos/{id}/foto` | multipart, campo `foto` (JPEG, até 1,5 MB) | Produto com `lotes` |
| `DELETE /api/produtos/{id}/foto` | | `204` |
| `GET /api/produtos/{id}/foto` | | `image/jpeg` |

**Produto**

```json
{
  "id": 1,
  "nome": "Fone JBL Tune 520BT",
  "observacao": "Preto",
  "foto_url": "/api/produtos/1/foto?v=1-a1b2c3d4e5f6.jpg",
  "estoque": 7,
  "custo": 28080,
  "precos": {"50": 42120, "60": 44928, "70": 47736},
  "valor_estoque": 196560,
  "vendas": 3,
  "ultima_compra": "2026-10-09",
  "lotes": [Compra, ...]
}
```

`custo`, `precos` são `null` se não houver compra. `estoque` pode ser negativo (encomenda). `vendas` é o número de itens de venda que usam o produto.

## Compras (lotes)

| Método e rota | Corpo | Resposta |
|---|---|---|
| `POST /api/produtos/{id}/lotes` | Compra | `201`, Produto com `lotes` |
| `PUT /api/lotes/{id}` | Compra | Produto com `lotes` |
| `DELETE /api/lotes/{id}` | | Produto com `lotes` |

**Compra (envio)**

```json
{
  "data_compra": "2026-10-09",
  "qtd": 4,
  "moeda": "USD",
  "preco_unit": 3250,
  "cambio": 53800,
  "frete_internacional": 9000,
  "impostos": 35000,
  "frete_nacional": 2500
}
```

`moeda`: `USD` ou `BRL`. `preco_unit` em centavos da moeda. `cambio` em reais × 10000 (5,38 → `53800`); ignorado em `BRL`. Fretes e impostos são o total da compra, em centavos de real.

**Compra (resposta)** traz os mesmos campos mais `id`, `produto_id`, `partes` (`produto`, `frete_internacional`, `impostos`, `frete_nacional`), `custo_total` e `custo_unit`.

## Vendas

| Método e rota | Parâmetros / corpo | Resposta |
|---|---|---|
| `GET /api/vendas` | `mes?`, `filtro?`, `offset=0`, `limite=30` (máx. 200) | `{"vendas": [Venda], "total": N}` |
| `POST /api/vendas` | Venda (envio) | `201`, Venda |
| `PUT /api/vendas/{id}` | Venda (envio) | Venda |
| `DELETE /api/vendas/{id}` | | `204` |
| `GET /api/vendas.csv` | `mes?`, `filtro?` | CSV (`;`, UTF-8 com BOM) |
| `GET /api/resumo` | `mes?` | `{"vendas", "itens", "vendido", "lucro", "a_receber"}` |

`filtro`: `a_receber`, `a_enviar`, `enviado`, `entregue`, `cancelada`. Sem filtro, lista todas (inclusive canceladas). Ordem: data mais recente primeiro.

**Venda (envio)**

```json
{
  "cliente": "Carlos Mendes",
  "data_venda": "2026-10-09",
  "itens": [
    {"produto_id": 2, "qtd": 1, "preco": 102733},
    {"produto_id": 1, "qtd": 1, "preco": 42000}
  ],
  "forma_pagamento": "credito",
  "taxa_pct": 499,
  "frete": 0,
  "desconto": 0,
  "pagamento": "pendente",
  "entrega": "a_enviar",
  "cancelada": false
}
```

| Campo | Valores |
|---|---|
| `forma_pagamento` | `pix`, `dinheiro`, `debito`, `credito`, `link`, `outro` |
| `taxa_pct` | Centésimos de por cento: 4,99% → `499` (0 a 10000) |
| `pagamento` | `pendente`, `pago` |
| `entrega` | `a_enviar`, `enviado`, `entregue` |
| `itens` | 1 a 50 itens |

**Venda (resposta)** traz os campos acima mais `id`, `taxa` (em centavos), `subtotal`, `total`, `custo_itens` e `lucro`. Cada item de `itens` traz também `produto` (nome gravado), `custo` (gravado) e `precos`.

## Painel

`GET /api/painel?hoje=AAAA-MM-DD` (data local do aparelho)

```json
{
  "lucro_dia": 75526, "vendido_dia": 228500, "vendas_dia": 2,
  "lucro_mes": 91218, "vendido_mes": 308400, "vendas_mes": 3,
  "a_receber": 121900, "vendas_a_receber": 2, "a_enviar": 2,
  "estoque_itens": 10, "estoque_valor": 386024, "estoque_produtos": 3,
  "estoque_baixo": [Produto, ...],
  "recentes": [Venda, ...]
}
```

`estoque_baixo`: produtos com 2 unidades ou menos. `recentes`: as 5 últimas vendas.

## Rotas fora de `/api`

| Rota | Uso |
|---|---|
| `GET /` | App |
| `GET /healthz` | Healthcheck, `{"ok": true}`, sem login |
| `GET /sw.js`, `GET /manifest.webmanifest` | PWA |
| `/static/...` | CSS, JS e ícones |
