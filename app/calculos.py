"""Cálculos de custo, preço e taxa. Tudo em centavos inteiros."""

MARKUPS = (50, 60, 70)


def dividir(a: int, b: int) -> int:
    """Divisão inteira arredondando meio para cima, igual ao Math.round do frontend."""
    return (2 * a + b) // (2 * b)


def preco_com_markup(custo: int, pct: int) -> int:
    return dividir(custo * (100 + pct), 100)


def precos(custo: int | None) -> dict[str, int] | None:
    if custo is None:
        return None
    return {str(p): preco_com_markup(custo, p) for p in MARKUPS}


def partes_lote(lote) -> dict[str, int]:
    """Custo total do lote, separado por origem."""
    return {
        "produto": dividir(lote["preco_unit"] * lote["qtd"] * lote["cambio"], 10000),
        "frete_internacional": lote["frete_internacional"],
        "impostos": lote["impostos"],
        "frete_nacional": lote["frete_nacional"],
    }


def custo_unit_lote(lote) -> int:
    return dividir(sum(partes_lote(lote).values()), lote["qtd"])


def custo_do_estoque(lotes: list, estoque: int) -> tuple[int | None, int]:
    """Custo unitário médio e valor do que está em estoque agora.

    Considera que as unidades vendidas saíram dos lotes mais antigos, então o
    estoque atual vem das compras mais recentes. Sem estoque, usa o custo da
    última compra. `lotes` deve vir em ordem de compra (mais antigo primeiro).
    """
    if not lotes:
        return None, 0
    if estoque <= 0:
        return custo_unit_lote(lotes[-1]), 0
    falta, valor, unidades = estoque, 0, 0
    for lote in reversed(lotes):
        usar = min(falta, lote["qtd"])
        valor += usar * custo_unit_lote(lote)
        unidades += usar
        falta -= usar
        if not falta:
            break
    return dividir(valor, unidades), valor


def taxa(subtotal: int, desconto: int, taxa_pct: int) -> int:
    """taxa_pct em centésimos de por cento (4,99% = 499)."""
    base = max(0, subtotal - desconto)
    return dividir(base * taxa_pct, 10000)
