# Guia de uso

## Primeiro acesso

Entre com o usuário e a senha criados na instalação ([deploy](deploy.md#usuários)). A sessão dura 30 dias neste aparelho. O botão **Sair** fica no topo da tela Início.

O app tem três telas, na barra inferior do celular ou no topo do computador: **Início**, **Vendas** e **Produtos**. O botão amarelo abre uma nova venda (ou um novo produto, na tela Produtos).

## 1. Cadastrar um produto

Em **Produtos → Novo produto**:

1. **Foto (opcional):** tire uma foto ou escolha da galeria. Ela é reduzida no próprio aparelho antes de enviar.
2. **Produto e observação:** nome e qualquer detalhe útil (cor, tamanho, fornecedor, link).
3. **Primeira compra:**
   - **Data** e **quantidade** comprada.
   - **Comprado em:** Dólar ou Real.
   - **Preço por unidade** na moeda escolhida e, se for dólar, o **câmbio** (quantos reais custou cada dólar).
   - **Frete internacional, impostos e frete até você:** o **total** pago pela compra inteira, não por unidade. Deixe em branco o que não houver.

O quadro **Custo por unidade** mostra o resultado e uma barra com o peso de cada parte (produto, fretes e impostos). A moeda e o câmbio usados ficam lembrados para a próxima compra.

## 2. Registrar uma nova compra de um produto que já existe

Abra o produto e toque em **Registrar compra**. Cada compra fica listada com data, quantidade, custo total e custo por unidade. Toque numa compra para corrigir ou excluir.

No topo do produto aparecem o **estoque**, o **custo atual** e os **preços sugeridos**. O custo atual considera as compras que ainda estão em estoque; veja como em [regras de negócio](regras-de-negocio.md#custo-atual-do-produto).

## 3. Registrar uma venda

Toque em **Nova venda**:

1. **Cliente** e **data**.
2. **Produtos:** digite parte do nome na busca (não precisa de acento) e toque no produto, ou use as setas e Enter. Para cada produto:
   - ajuste a **quantidade**;
   - toque em **+50%, +60% ou +70%** para usar o preço sugerido, ou digite o **valor final por unidade**;
   - o app avisa se a quantidade passar do estoque (a diferença fica como encomenda).
   Adicione quantos produtos quiser; o **×** remove um produto.
3. **Pagamento e custos da venda:**
   - **Forma de pagamento** e **Taxa (%)** cobrada pela maquininha ou plataforma. A taxa de cada forma fica lembrada.
   - **Frete pago por você**, se você pagou o envio ao cliente.
   - **Desconto** dado na venda inteira.
4. Confira a conta: produtos, desconto, taxa, frete, custo e **lucro com margem**.
5. Marque **Pagamento** (a receber ou pago) e **Entrega** (a enviar, enviado, entregue) e salve.

Para atualizar uma venda (por exemplo, marcar como paga ou enviada), toque nela na lista. Na edição aparece também a opção **Venda cancelada**: ela devolve os itens ao estoque e tira a venda dos totais, mas mantém o registro. **Excluir** apaga de vez (pede um segundo toque para confirmar).

## 4. Acompanhar

**Início** mostra:

| Bloco | O que é |
|---|---|
| Lucro hoje | Lucro das vendas com a data de hoje |
| Lucro do mês | Lucro das vendas do mês atual |
| A receber | Total das vendas marcadas como "a receber", de qualquer data. Toque para ver a lista |
| A enviar | Quantidade de vendas ainda não enviadas. Toque para ver a lista |
| Em estoque | Unidades disponíveis e em quantos produtos |
| Valor do estoque | Quanto custou o que está parado em estoque |

Vendas canceladas não entram em nenhum total.

**Vendas** mostra o mês escolhido (setas ‹ ›; toque no nome do mês para ver todas as datas) com os totais do período e filtros: a receber, a enviar, enviadas, entregues e canceladas. A lista carrega 30 vendas por vez; use **Mostrar mais** para as seguintes.

## 5. Exportar para Excel

Em **Vendas**, use **Exportar CSV deste período**. O arquivo respeita o mês e o filtro escolhidos, tem uma linha por produto vendido e abre direto no Excel com acentos. Desconto, taxa e frete aparecem rateados entre os itens da venda; veja [regras](regras-de-negocio.md#csv).

## 6. Instalar no celular

Com o app publicado em HTTPS:

- **Android (Chrome):** menu ⋮ → **Instalar app** ou **Adicionar à tela inicial**.
- **iPhone (Safari):** botão Compartilhar → **Adicionar à Tela de Início**.

O app abre em tela cheia, com ícone próprio. Ele precisa de internet para carregar e salvar dados.

## Dicas

- Números aceitam vírgula ou ponto: `1.234,56`, `1234,56` e `1234.56` são o mesmo valor.
- Produto sem nenhuma compra registrada aparece na busca, mas não pode ser vendido: sem compra, não há custo para calcular o lucro.
- Produto que já tem vendas não pode ser excluído.
