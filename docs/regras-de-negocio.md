# Regras de negócio

Todas as contas são feitas em **centavos inteiros**. Arredondamentos usam "meio centavo para cima", iguais no servidor (`app/calculos.py`) e no navegador (`app/static/app.js`), para que o valor mostrado na tela seja o mesmo que fica salvo.

## Custo de uma compra

Cada compra (lote) guarda: quantidade, moeda (USD ou BRL), preço unitário na moeda, câmbio e três custos **totais** da compra: frete internacional, impostos e frete até você.

```
produto      = preço unitário × quantidade × câmbio
custo total  = produto + frete internacional + impostos + frete até você
custo/unid.  = custo total ÷ quantidade
```

Compra em reais usa câmbio 1 (o campo câmbio é ignorado).

**Exemplo:** 4 fones a US$ 32,50 com câmbio R$ 5,38, frete internacional R$ 90, impostos R$ 350, frete até você R$ 25.

| Parte | Valor | Peso |
|---|---|---|
| Produto (32,50 × 4 × 5,38) | R$ 699,40 | 60,1% |
| Frete internacional | R$ 90,00 | 7,7% |
| Impostos | R$ 350,00 | 30,1% |
| Frete até você | R$ 25,00 | 2,1% |
| **Total** | **R$ 1.164,40** | |
| **Por unidade** | **R$ 291,10** | |

## Estoque

```
estoque = soma das quantidades compradas − soma das quantidades vendidas (vendas não canceladas)
```

O estoque não é digitado: é sempre calculado. Por isso cancelar, editar ou excluir uma venda devolve as unidades automaticamente, e corrigir uma compra corrige o estoque.

Vender mais do que há em estoque é permitido. O estoque fica negativo e aparece como **"N sob encomenda"**.

## Custo atual do produto

É o custo usado nos preços sugeridos e gravado nas vendas novas.

Considera-se que as vendas saem das **compras mais antigas primeiro**. Assim, o que está em estoque hoje veio das compras mais recentes. O custo atual é a média ponderada dessas unidades:

1. Percorre as compras da mais nova para a mais antiga.
2. Pega unidades até completar o estoque atual.
3. Custo atual = soma do custo dessas unidades ÷ estoque.

Sem estoque (zero ou negativo), vale o custo por unidade da **última compra**. Sem nenhuma compra, o produto não tem custo e não pode ser vendido.

**Exemplo:** compra A em setembro, 10 un. a R$ 180; compra B em outubro, 5 un. a R$ 220. Foram vendidas 12 unidades.

- Estoque = 15 − 12 = 3.
- As 3 unidades vêm da compra B → custo atual = R$ 220.
- Com 7 unidades vendidas, o estoque seria 8: 5 de B + 3 de A → (5 × 220 + 3 × 180) ÷ 8 = R$ 205.

## Valor do estoque

Soma do custo das unidades em estoque, pela mesma regra acima. Produtos com estoque zero ou negativo não entram.

## Preço sugerido

```
preço +P% = custo atual × (100 + P) ÷ 100      P ∈ {50, 60, 70}
```

É uma margem sobre o custo (markup), não sobre o preço. +50% sobre R$ 100 sugere R$ 150, cuja margem sobre a venda é 33,3%.

## Venda

Uma venda tem um ou mais itens. Cada item grava, no momento da venda: nome do produto, quantidade, **custo unitário** e preço final.

```
subtotal          = Σ quantidade × preço final
total (cliente)   = subtotal − desconto
taxa              = total × taxa% ÷ 100
custo dos itens   = Σ quantidade × custo unitário gravado
lucro             = total − taxa − frete pago por você − custo dos itens
margem            = lucro ÷ total
```

- A taxa incide sobre o valor **depois do desconto** e é gravada em reais no momento em que a venda é salva.
- O desconto não pode ser maior que o subtotal.
- **Custo gravado:** comprar mais caro depois não muda o lucro de vendas antigas. Ao editar uma venda, os produtos que já estavam nela mantêm o custo gravado; um produto novo adicionado na edição usa o custo atual.

**Exemplo:** 1 perfume a R$ 1.027,33 (custo R$ 642,08) e 1 fone a R$ 420,00 (custo R$ 267,06), cartão de crédito com taxa de 4,99%, sem desconto nem frete.

| | |
|---|---|
| Produtos | R$ 1.447,33 |
| Taxa (4,99%) | − R$ 72,22 |
| Custo dos produtos | − R$ 909,14 |
| **Lucro** | **R$ 465,97 (32,2%)** |

## Status

| Campo | Valores | Efeito |
|---|---|---|
| Pagamento | a receber, pago | "A receber" soma no bloco e no filtro A receber |
| Entrega | a enviar, enviado, entregue | "A enviar" soma no bloco e no filtro A enviar |
| Cancelada | sim, não | Sai de todos os totais e devolve as unidades ao estoque |

## Totais

Todos os totais (Início, resumo do mês em Vendas) **ignoram vendas canceladas**.

- **Lucro hoje** usa a data local do aparelho.
- **A receber** e **A enviar** consideram todas as datas, não só o mês.
- **Vendido** no resumo do mês é a soma do total pago pelos clientes (depois do desconto).

## CSV

Uma linha por item vendido, com as colunas: Venda, Cliente, Data Venda, Produto, Custo, Preço +50%, Preço +60%, Preço +70%, Valor Vendido, Qtd, Desconto taxa e frete, Lucro, Pagamento, Entrega, Cancelada.

Desconto, taxa e frete pertencem à venda inteira. Para que a soma das colunas bata com os totais, esses valores são **rateados entre os itens** pelo valor de cada um (quantidade × preço). O último item recebe o resto do arredondamento.

**Exemplo:** venda com item A (R$ 300) e item B (R$ 100), desconto R$ 10 e frete R$ 10 → A recebe R$ 15 e B recebe R$ 5.

O arquivo usa `;` como separador, vírgula decimal e marca UTF-8 (BOM) para o Excel reconhecer os acentos.

## Exclusões

| O quê | Permitido? |
|---|---|
| Produto sem vendas | Sim (apaga também as compras e a foto) |
| Produto com vendas | Não. Mantém o histórico das vendas |
| Compra | Sim. O estoque e o custo atual são recalculados; vendas já feitas não mudam |
| Venda | Sim, de vez. Para manter o registro, prefira marcar como cancelada |
