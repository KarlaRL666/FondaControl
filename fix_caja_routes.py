#!/usr/bin/env python
"""Fix script para remover el filtro de metodo_pago en caja/routes.py"""

with open('modules/caja/routes.py', 'r') as f:
    content = f.read()

# Encontrar y reemplazar la sección problemática
old_query = '''        pedidos = (
            Pedido.query
            .filter(Pedido.estado.in_(['Pendiente', 'En Proceso', 'Producido', 'Completado']))
            .outerjoin(PedidoMeta)
            .filter((PedidoMeta.metodo_pago == None) | (PedidoMeta.metodo_pago == ''))
            .order_by(Pedido.fecha.asc())
            .all()
        )'''

new_query = '''        # Get all pedidos that are completable in caja
        all_pedidos = (
            Pedido.query
            .filter(Pedido.estado.in_(['Pendiente', 'En Proceso', 'Producido', 'Completado']))
            .order_by(Pedido.fecha.asc())
            .all()
        )'''

if old_query in content:
    content = content.replace(old_query, new_query)
    print("✓ Query actualizado")
else:
    print("✗ No se encontró el patrón exacto")
    print("\nBuscando alternativas...")
    if "metodo_pago == None" in content:
        print("Encontrado: metodo_pago == None")

# También reemplazar donde se usa "pedidos" por "all_pedidos"
content = content.replace('''        for pedido in pedidos:
            if not _pedido_es_completable_en_caja(pedido):
                continue''', 
'''        pedidos_data = []
        for pedido in all_pedidos:
            # Check if this pedido can be processed
            if not _pedido_es_completable_en_caja(pedido):
                continue''')

if "pedidos_data = []" in content:
    print("✓ Loop actualizado")

with open('modules/caja/routes.py', 'w') as f:
    f.write(content)

print("✓ Archivo guardado")
