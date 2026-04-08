from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from models import Receta


def convertir_a_gramos(cantidad: float, unidad: str, factor_conversion: float = 1.0) -> float:
    """Normaliza una cantidad a unidad base operativa (g/ml/pz-base)."""
    cantidad = float(cantidad or 0)
    unidad = (unidad or "").strip().lower()
    factor_conversion = float(factor_conversion or 1)

    if unidad == "kg":
        return cantidad * 1000.0
    if unidad == "g":
        return cantidad
    if unidad == "l":
        return cantidad * 1000.0
    if unidad == "ml":
        return cantidad
    if unidad == "pz":
        return cantidad * factor_conversion
    return cantidad


def convertir_desde_base(cantidad_base: float, unidad: str, factor_conversion: float = 1.0) -> float:
    """Convierte desde unidad base operativa hacia la unidad de stock declarada."""
    cantidad_base = float(cantidad_base or 0)
    unidad = (unidad or "").strip().lower()
    factor_conversion = float(factor_conversion or 1)

    if unidad == "kg":
        return cantidad_base / 1000.0
    if unidad == "g":
        return cantidad_base
    if unidad == "l":
        return cantidad_base / 1000.0
    if unidad == "ml":
        return cantidad_base
    if unidad == "pz":
        return cantidad_base / factor_conversion if factor_conversion > 0 else cantidad_base
    return cantidad_base


def obtener_receta_vigente(producto) -> Optional[Receta]:
    if not producto or not getattr(producto, "recetas", None):
        return None

    activas = [r for r in producto.recetas if getattr(r, "estado", True)]
    recetas = activas or list(producto.recetas)
    if not recetas:
        return None

    recetas.sort(key=lambda r: (getattr(r, "fecha_creacion", None) or 0), reverse=True)
    return recetas[0]


def calcular_requerimientos_para_producto(producto, cantidad_objetivo: float) -> Tuple[List[Dict], Optional[str]]:
    receta = obtener_receta_vigente(producto)
    if not receta:
        return [], "El producto no tiene receta activa"

    cantidad_objetivo = float(cantidad_objetivo or 0)
    cantidad_receta = float(receta.cantidad_produccion or 0)
    if cantidad_objetivo <= 0:
        return [], "La cantidad a producir debe ser mayor a cero"
    if cantidad_receta <= 0:
        return [], "La receta tiene cantidad de producción inválida"

    escala = cantidad_objetivo / cantidad_receta
    filas: List[Dict] = []

    for detalle in receta.detalles:
        materia = detalle.materia_prima
        if not materia:
            continue

        cantidad_base_receta = float(detalle.cantidad_requerida or detalle.cantidad or 0)
        merma_pct = float(materia.porcentaje_merma or 0)
        requerido_sin_merma = cantidad_base_receta * escala
        requerido_con_merma = requerido_sin_merma * (1 + (merma_pct / 100.0))

        unidad_materia = (materia.unidad_medida or "g").lower()
        factor = float(materia.factor_conversion or 1)

        requerido_base = convertir_a_gramos(requerido_con_merma, unidad_materia, factor)
        stock_base = convertir_a_gramos(float(materia.stock_actual or 0), unidad_materia, factor)
        faltante_base = max(0.0, requerido_base - stock_base)

        filas.append({
            "materia": materia,
            "requerido": round(requerido_con_merma, 6),
            "requerido_base": round(requerido_base, 6),
            "stock_base": round(stock_base, 6),
            "faltante_base": round(faltante_base, 6),
            "faltante": round(convertir_desde_base(faltante_base, unidad_materia, factor), 6),
            "unidad": unidad_materia,
            "merma_pct": merma_pct,
        })

    if not filas:
        return [], "El producto no tiene ingredientes configurados en su receta"

    return filas, None
