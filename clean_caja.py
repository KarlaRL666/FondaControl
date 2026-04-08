#!/usr/bin/env python
"""Clean duplicate lines in caja/routes.py"""

with open('modules/caja/routes.py', 'r') as f:
    lines = f.readlines()

# Remover líneas duplicadas
output = []
last_line = None
for line in lines:
    if line != last_line or not line.strip().startswith('pedidos_data'):
        output.append(line)
    last_line = line

with open('modules/caja/routes.py', 'w') as f:
    f.writelines(output)

print("✓ Duplicados removidos")
