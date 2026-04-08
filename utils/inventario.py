def cantidad_stock_neta_desde_compra(cantidad_compra, materia):
    """Devuelve la cantidad neta comprada sin ajustes de merma/conversión."""
    cantidad = float(cantidad_compra or 0)
    if cantidad <= 0:
        return 0.0

    return cantidad


def cantidad_compra_para_stock_objetivo(cantidad_stock_objetivo, materia):
    """Calcula cuánta cantidad de compra se necesita para cubrir un objetivo de stock."""
    objetivo = float(cantidad_stock_objetivo or 0)
    if objetivo <= 0:
        return 0.0

    return objetivo
