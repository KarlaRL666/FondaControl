# Especificacion Tecnica por Modulo

## Alcance
Documento tecnico del sistema modular Flask ubicado en `modules/`, orientado a mantenimiento, auditoria y transferencia de conocimiento.

## Convenciones
- Entradas: parametros de ruta, formularios, sesion, usuario autenticado.
- Salidas: HTML renderizado, redirecciones, cambios en BD, mensajes flash.
- Dependencias comunes: `models.py`, Flask-Login, WTForms, SQLAlchemy, utilidades de seguridad/bitacora.

---

## 1. auth
- Objetivo: autenticacion, autorizacion inicial, recuperacion de contrasena y 2FA.
- Entradas:
  - `username`, `contrasena`, token Turnstile (`cf-turnstile-response`), codigo 2FA, correo de recuperacion, token de reset.
- Salidas:
  - Inicio de sesion por rol, desafio 2FA, envio de correos, cambio de contrasena, cierre de sesion.
- Reglas de negocio:
  - CAPTCHA obligatorio cuando `LOGIN_CAPTCHA_ENABLED=true`.
  - 2FA por correo cuando `LOGIN_2FA_ENABLED=true`.
  - Tokens de reset con expiracion (`RESET_PASSWORD_TOKEN_MAX_AGE`).
- Dependencias:
  - `forms.py` (Login/Recuperar/Reset/2FA), `Persona`/`Usuario`, SMTP config, `itsdangerous`.

## 2. cuenta
- Objetivo: autoservicio de perfil y registro de cliente.
- Entradas: formularios de alta/edicion, `id_usuario` actual.
- Salidas: perfil renderizado, actualizacion de datos personales y de cuenta.
- Reglas de negocio: validaciones de unicidad (correo/username/telefono) y consistencia persona-usuario.
- Dependencias: `modules/cuenta/services.py`, `forms.py`, `models.py`.

## 3. usuarios
- Objetivo: administracion de usuarios internos y roles.
- Entradas: filtros, formularios CRUD, `id_usuario`.
- Salidas: listado, alta, edicion, activacion/desactivacion.
- Reglas de negocio: control por rol administrador para operaciones criticas.
- Dependencias: `modules/usuarios/services.py`, `Rol`, `Usuario`, `Persona`.

## 4. clientes
- Objetivo: administracion de clientes desde backoffice.
- Entradas: filtros (`q`, `estado`), formularios de cliente.
- Salidas: CRUD cliente y estado activo/inactivo.
- Reglas de negocio: integridad entre tablas Persona/Usuario/Cliente.
- Dependencias: `modules/clientes/services.py`, `forms.py`, bitacora.

## 5. categorias
- Objetivo: CRUD de categorias de productos/platillos.
- Entradas: formularios y busquedas por nombre.
- Salidas: altas, ediciones, desactivacion/reactivacion.
- Reglas de negocio: evitar duplicados logicos por nombre.
- Dependencias: `modules/categorias/services.py`, `CategoriaPlatillo`.

## 6. productos
- Objetivo: gestion de catalogo de productos vendibles.
- Entradas: formularios de producto, imagen, categoria existente/nueva, filtros de estado.
- Salidas: listado, detalle, alta, edicion, activacion/desactivacion.
- Reglas de negocio:
  - costo calculado segun receta/insumos cuando aplica.
  - categoria obligatoria o creacion de nueva categoria segun formulario.
- Dependencias: `modules/productos/services.py`, `recetas`, `CategoriaPlatillo`, archivos estaticos.

## 7. recetas
- Objetivo: definicion de receta por producto y calculo de costo/rendimiento.
- Entradas: `id_producto`, `id_receta`, detalles de materias y unidades.
- Salidas: receta creada/editada y costo total calculado.
- Reglas de negocio:
  - normalizacion de unidades y cantidades.
  - consistencia de rendimiento/cantidad produccion.
- Dependencias: `modules/recetas/services.py`, `Producto`, `DetalleReceta`, `MateriaPrima`.

## 8. ingredientes
- Objetivo: administracion de materias primas.
- Entradas: formularios, proveedor asociado, categoria sugerida.
- Salidas: CRUD de ingrediente y endpoints auxiliares por proveedor.
- Reglas de negocio: umbral de stock minimo y estado activo/inactivo.
- Dependencias: `modules/ingredientes/services.py`, `Proveedor`, `CategoriaIngrediente`.

## 9. inventario
- Objetivo: consulta consolidada de existencias.
- Entradas: datos de inventario desde modelos.
- Salidas: tablero/listado de inventario.
- Reglas de negocio: visualizacion operativa (sin flujo transaccional propio).
- Dependencias: `modules/inventario/routes.py`, modelos de stock.

## 10. compras
- Objetivo: ciclo de compras y recepcion de insumos.
- Entradas:
  - solicitud manual, alertas de faltantes, metodo de pago, recepcion por detalle.
- Salidas:
  - compra creada, detalle recibido, compra completada/eliminada, pago guardado.
- Reglas de negocio:
  - validacion de efectivo disponible en caja para pagos en efectivo.
  - recepcion parcial/completa por detalle.
- Dependencias:
  - `modules/compras/services.py`, `caja`, `produccion`, proveedores, materias primas.

## 11. produccion
- Objetivo: gestion de ordenes de produccion y enlace con compras.
- Entradas: solicitud por alerta, avance por detalle, fechas requeridas.
- Salidas: orden iniciada/completada/cancelada, compras disparadas por faltantes.
- Reglas de negocio:
  - avance por detalle con calculo de progreso.
  - si faltan insumos, derivar a compra.
- Dependencias: `modules/produccion/services.py`, `compras`, `productos`, `recetas`.

## 12. pedidos
- Objetivo: ciclo completo de pedidos de clientes y operacion interna.
- Entradas:
  - carrito/productos, metodo de pago, datos tarjeta, acciones de editar/cancelar/procesar.
- Salidas:
  - pedido creado, ticket, estados actualizados, calificacion de servicio.
- Reglas de negocio:
  - validacion de pago y metadatos.
  - transicion de estados de pedido y detalle.
  - integracion con produccion y caja segun flujo.
- Dependencias: `modules/pedidos/services.py`, `tienda`, `caja`, `produccion`, ventas.

## 13. caja
- Objetivo: control de apertura/cierre de caja y operaciones de cobro/egreso.
- Entradas: monto inicial, pagos de pedidos, egresos, confirmacion de cierre.
- Salidas: corte, historial, anulaciones, cierre diario.
- Reglas de negocio:
  - ventanas horarias operativas.
  - cierres con conciliacion ingresos-egresos.
- Dependencias: `modules/caja/routes.py`, `utils/caja_movimientos.py`, pedidos, compras.

## 14. ventas
- Objetivo: administracion de ventas internas.
- Entradas: productos y cantidades, metodo de pago, fecha necesaria.
- Salidas: venta guardada/completada, detalle y eliminacion.
- Reglas de negocio:
  - ajuste de total, costo y stock al completar.
- Dependencias: `modules/ventas/services.py`, `Producto`, `DetalleVenta`, inventario.

## 15. tienda
- Objetivo: front de cliente (menu, carrito, checkout y contacto).
- Entradas: operaciones de carrito, checkout, formulario de contacto.
- Salidas: pedido finalizado, carrito actualizado, correo de contacto enviado.
- Reglas de negocio:
  - validacion de tarjeta en checkout.
  - control de cantidades y existencia en carrito.
- Dependencias: `modules/tienda/services.py`, `pedidos`, SMTP, catalogos.

## 16. dashboard
- Objetivo: panel de indicadores y bitacora.
- Entradas: datos agregados de BD SQL/Mongo.
- Salidas: KPIs, resumenes, vistas historicas.
- Reglas de negocio: mostrar indicadores por rol y disponibilidad de datos.
- Dependencias: `modules/dashboard/services.py`, MongoDB, ventas/pedidos/caja.

## 17. alertas
- Objetivo: gestion de estado visual de alertas del sistema.
- Entradas: usuario actual y sesion.
- Salidas: contexto para UI y marcado de alertas vistas.
- Reglas de negocio: alertas por rol y por estado operativo.
- Dependencias: `modules/alertas/services.py`, `session`, Mongo/SQL.

## Matriz de dependencias transversales
- Seguridad: `utils/security.py`, Flask-Login, validaciones WTForms.
- Persistencia: SQLAlchemy (principal), MongoDB (bitacora/analitica).
- Comunicacion: SMTP para contacto y seguridad (2FA/reset).
- UI: plantillas Jinja en `templates/`, CSS en `static/style`.

## Recomendaciones operativas
- Mantener logica de negocio en `services.py` y rutas delgadas.
- Centralizar validaciones reutilizables (tarjeta, fechas, estados).
- Definir contratos de entrada/salida por servicio para pruebas unitarias.
- Documentar cambios de estado criticos (pedido, compra, produccion, caja).
