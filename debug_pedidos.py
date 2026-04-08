#!/usr/bin/env python
"""Debug script para verificar estado de pedidos y producciones"""
from app import app
from models import db, Pedido, PedidoMeta, Produccion

with app.app_context():
    # Verificar pedidos Pendiente, Producido, Completado
    pedidos = Pedido.query.filter(Pedido.estado.in_(['Pendiente', 'En Proceso', 'Producido', 'Completado'])).all()
    print(f'\n=== PEDIDOS ===')
    print(f'Total pedidos en esos estados: {len(pedidos)}')
    
    for p in pedidos[:5]:
        meta = PedidoMeta.query.filter_by(id_pedido=p.id_pedido).first()
        metodo = meta.metodo_pago if meta else "NO META"
        print(f'  Pedido {p.id_pedido}: estado={p.estado}, metodo_pago={metodo}')
    
    # Verificar si hay producciones
    prods = Produccion.query.all()
    print(f'\n=== PRODUCCIONES ===')
    print(f'Total producciones: {len(prods)}')
    if prods:
        prod = prods[0]
        print(f'  Producción {prod.id_produccion}: estado={prod.estado}, detalles={len(prod.detalles or [])}')
        if prod.detalles:
            for det in prod.detalles[:2]:
                print(f'    - Detalle {det.id_detalle}: cantidad={det.cantidad}, producida={getattr(det, "cantidad_producida", "N/A")}')
