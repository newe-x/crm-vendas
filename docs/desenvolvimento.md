# Desenvolvimento

## Ambiente

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m app.usuarios dev            # usuário local
.venv/bin/uvicorn app.main:app --reload --port 8000
.venv/bin/python -m pytest -q
```

Use `DB_PATH=/caminho/outro.db` para trabalhar num banco separado. As fotos ficam numa pasta `fotos/` ao lado do banco.

## Estrutura

```
app/
  main.py          rotas da API, modelos (Pydantic), CSV, painel, arquivos do app
  calculos.py      contas de custo, preço sugerido, taxa e custo do estoque
  db.py            conexão SQLite, esquema e versão do esquema
  auth.py          senhas (scrypt), sessões, limite de tentativas
  usuarios.py      comando para criar usuário / trocar senha
  static/
    index.html     todas as telas e folhas (dialog) do app
    app.js         lógica do navegador, sem framework e sem build
    styles.css     estilos, mobile first; planilha a partir de 960 px
    sw.js          service worker (PWA)
    manifest.webmanifest, icones/
tests/test_api.py  testes da API
docs/              esta documentação
```

## Banco

SQLite, esquema em `app/db.py`. A versão fica em `PRAGMA user_version` (hoje 2).

| Tabela | Conteúdo |
|---|---|
| `usuarios` | usuário e hash da senha |
| `sessoes` | hash SHA-256 do token, usuário, expiração |
| `produtos` | nome, observação, nome do arquivo da foto |
| `lotes` | compras: quantidade, moeda, preço, câmbio, fretes, impostos |
| `vendas` | cliente, data, forma de pagamento, taxa, frete, desconto, pagamento, entrega, cancelada |
| `venda_itens` | produto, nome e custo gravados, quantidade, preço |
| `v_vendas` (view) | venda + subtotal, total, custo dos itens, quantidade e lucro |

Estoque e custo atual **não são guardados**: são calculados a partir de `lotes` e `venda_itens` em `carregar_produtos()` e `calculos.custo_do_estoque()`.

**Mudando o esquema:** aumente `VERSAO_ESQUEMA` e escreva a migração em `db.iniciar()`. Nunca descarte tabelas que tenham dados.

## Convenções

- **Dinheiro em centavos inteiros**, câmbio × 10000, percentuais em centésimos de % (4,99% = 499). Nada de `float` para valores.
- **Arredondamento igual dos dois lados:** `dividir()` em `calculos.py` e em `app.js` arredondam meio para cima. Ao mudar uma conta, mude nos dois e cubra com teste.
- **Valores gravados na venda:** custo e nome do produto ficam no item para não reescrever o passado.
- **Interface em português**, frases curtas, botões dizem o que fazem ("Salvar venda", "Registrar compra").
- **Sem diálogos do navegador:** a exclusão pede um segundo toque no próprio botão.
- **Fotos:** o navegador reduz para no máximo 1000 px e converte para JPEG; o servidor só aceita JPEG até 1,5 MB e gera nomes aleatórios.

## Testes

`tests/test_api.py` cobre login e bloqueio, cookie, custo composto, compra em reais, custo pelo estoque mais recente, exclusões, foto, venda com vários itens e custos, desconto inválido, produto sem compra, custo gravado na edição, cancelamento, filtros e paginação, painel e rateio do CSV.

Cada teste usa um banco temporário próprio (`DB_PATH` + `importlib.reload`).

O frontend não tem testes automatizados. Antes de publicar uma mudança de tela, teste no navegador em largura de celular (390 px) e de computador.

## Frontend

- Telas: `#inicio`, `#vendas`, `#produtos` (hash na URL).
- Folhas (`<dialog>`): produto, compra e venda. Os campos de compra vêm do `<template id="tpl-compra">`, reutilizado no cadastro do produto e em "Registrar compra".
- `api()` centraliza as chamadas; um `401` leva à tela de login.
- Preferências em `localStorage`: última moeda, último câmbio e taxa por forma de pagamento.

### Design

Paleta inspirada em documentos de embarque: papel azulado `#E9EDF1`, tinta marinho `#18212E`, amarelo de carga `#F0B400` (ação principal e preço escolhido), verde `#1D7046` para lucro e vermelho `#B42318` para prejuízo. Tipografia Barlow Condensed para números e títulos, Barlow para texto. Status aparecem como carimbos; tracejado indica pendência.

## Ícones

Os PNGs em `app/static/icones/` foram gerados por script (caixa amarela sobre fundo marinho). Para trocar, substitua os arquivos mantendo os tamanhos 180, 192 e 512 (e a versão `mascara`, com margem de segurança de 10%).
