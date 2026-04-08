# Documentacion funcional por modulo

## Vision general
La aplicacion esta organizada por modulos Flask (blueprints) dentro de `modules/`.
Cada modulo encapsula rutas HTTP y, en la mayoria de casos, una capa de servicios para la logica de negocio.

## alertas
- Proposito: centralizar alertas de negocio (stock bajo, pendientes, notificaciones) y su estado de lectura.
- Rutas:
  - `GET /marcar-vistas`: marca alertas como vistas para el usuario actual.
- Servicios clave:
  - `construir_contexto_alertas(user)`: arma el contexto de alertas para UI.
  - `marcar_alertas_vistas(user, session_obj)`: persiste el estado de alertas vistas.

## auth
- Proposito: autenticacion, recuperacion de cuenta y control de acceso.
- Rutas:
  - `GET/POST /login`: login con validacion CAPTCHA.
  - `GET/POST /2fa`: verificacion de segundo factor por codigo.
  - `POST /2fa/reenviar`: reenvio de codigo 2FA.
  - `GET/POST /forgot-password`: solicitud de recuperacion de contrasena.
  - `GET/POST /reset-password/<token>`: restablecimiento de contrasena.
  - `GET/POST /crearCuenta`: alta de cuenta cliente.
  - `GET /miPerfil`, `GET/POST /editarPerfil`, `GET /logout`, `GET /redirigir`.
- Servicios/auxiliares clave:
  - Verificacion Turnstile.
  - Envio de correo para 2FA/recuperacion.
  - Resolucion de usuario por correo.
  - Generacion y validacion de token de recuperacion.

## caja
- Proposito: gestion operativa de caja diaria.
- Rutas:
  - `GET /`: vista principal de caja.
  - `POST /abrir`: apertura de caja.
  - `POST /salida-proveedor`: egresos a proveedor.
  - `GET /cierre`, `POST /cierre`: pre-cierre y confirmacion de cierre.
  - `GET /historial`, `GET /ver-cierre/<id_caja>`.
  - `GET /anular/<id_venta>`.
  - `GET /pedidos-completados`.
  - `GET/POST /procesar-pago/<id_pedido>`.
- Logica destacada:
  - Calcula periodos de caja.
  - Integra ingresos por pedidos y egresos por compras.
  - Validaciones por rol y disponibilidad de caja.

## categorias
- Proposito: CRUD de categorias de platillos/productos.
- Rutas:
  - `GET /`, `GET/POST /crear`, `GET /detalles`, `GET/POST /editar`, `POST /desactivar`, `POST /activar`.
- Servicios clave:
  - Crear, listar, obtener, filtrar, actualizar, activar/desactivar categoria.

## clientes
- Proposito: administracion de clientes por backoffice.
- Rutas:
  - `GET /`, `GET/POST /crear`, `GET /ver/<id_cliente>`, `GET/POST /editar/<id_cliente>`, `POST /eliminar/<id_cliente>`, `POST /activar/<id_cliente>`.
- Servicios clave:
  - Listado con filtros.
  - Alta/edicion con validaciones de usuario/persona.
  - Activacion/desactivacion con trazabilidad.

## compras
- Proposito: ciclo de compras de materias primas.
- Rutas:
  - `GET /`, `GET/POST /crear`, `GET /ver/<id>`, `POST /actualizar/<id>`, `POST /completar/<id>`.
  - `POST /detalle/<id_compra>/<id_detalle>` para recepcion por detalle.
  - `POST /guardar_pago/<id>`.
  - `GET /alerta/<id_materia>` para compra sugerida por alerta.
  - `POST /eliminar/<id>`.
- Servicios clave:
  - Solicitud manual y desde alertas.
  - Control de efectivo disponible en caja.
  - Recepcion parcial/completa por detalle.
  - Normalizacion de metodos de pago y ajustes de esquema.

## cuenta
- Proposito: autoservicio de cuenta del usuario/cliente.
- Rutas:
  - `GET /perfil`, `GET/POST /crear`, `GET/POST /editar`.
- Servicios clave:
  - Ver perfil.
  - Crear cliente en flujo de autoservicio.
  - Actualizar datos personales y credenciales con validaciones.

## dashboard
- Proposito: panel ejecutivo/operativo y bitacora.
- Rutas:
  - `GET/POST /`: dashboard principal.
  - `GET /bitacora`: trazabilidad de acciones/eventos.
- Servicios clave:
  - Estadisticas de ventas.
  - Resumen de ventas.
  - Ventas por producto.

## ingredientes
- Proposito: catalogo de materias primas/ingredientes.
- Rutas:
  - `GET/POST /`, `GET/POST /crear`, `GET/POST /editar/<id>`, `POST /desactivar`, `POST /activar`, `GET /detalle/<id>`.
  - Endpoints auxiliares por proveedor:
    - `GET /sugerir-categoria/<id_proveedor>`
    - `GET /categorias-por-proveedor/<id_proveedor>`
- Servicios clave:
  - CRUD de ingrediente.
  - Filtros y validaciones.
  - Reglas de stock minimo.

## inventario
- Proposito: vista consolidada de inventario.
- Rutas:
  - `GET /`: tablero/listado de inventario.
- Nota:
  - No tiene `services.py` propio en este modulo.

## pedidos
- Proposito: gestion integral de pedidos (cliente y operacion interna).
- Rutas:
  - `GET /`, `GET /mis_pedidos`, `GET /detalles/<id_pedido>`, `GET /ticket/<id_pedido>`.
  - `POST /crear`, `POST /procesar`, `POST /cancelar/<id_pedido>`, `GET/POST /editar/<id_pedido>`.
  - `POST /detalle/<id_pedido>/<id_detalle>`.
  - `POST /calificar/<id_pedido>`, `GET /calificaciones`.
- Servicios clave:
  - Creacion manual y ciclo de vida del pedido.
  - Integracion con produccion y pagos.
  - Validacion de tarjeta y metadatos de pago.
  - Completar/cancelar/editar pedido y procesar detalles.

## produccion
- Proposito: ordenes de produccion y abastecimiento ligado a compras.
- Rutas:
  - `GET /`, `GET /ver/<id>`, `GET /iniciar/<id>`, `POST /completar/<id>`, `POST /detalle/<id_produccion>/<id_detalle>`, `GET /cancelar/<id>`.
  - `GET/POST /alerta/<id_producto>` para generar produccion desde alerta.
- Servicios clave:
  - Crear solicitudes de produccion por alerta.
  - Calcular progreso y requerimientos.
  - Procesar detalle y disparar compra cuando aplica.
  - Ver y cerrar ordenes.

## productos
- Proposito: catalogo de productos/platillos vendibles.
- Rutas:
  - `GET /`, `GET/POST /crear`, `GET/POST /editar`, `POST /desactivar`, `POST /activar`, `GET /detalles`.
- Servicios clave:
  - Crear/editar/listar productos.
  - Calculo de costos del producto.
  - Busqueda y filtrado.
  - Gestion de categoria existente o nueva.

## proveedores
- Proposito: gestion de proveedores y su clasificacion.
- Rutas:
  - `GET /`, `GET/POST /crear`, `GET /detalles`, `GET/POST /editar`, `POST /desactivar`, `POST /activar`.
- Servicios clave:
  - Crear/actualizar proveedor.
  - Activar/desactivar proveedor.
  - Filtrar y listar proveedores.
  - Resolver categoria de proveedor (existente o nueva).

## recetas
- Proposito: definicion de recetas y costos por producto.
- Rutas:
  - `GET /`, `GET /ver/<id_receta>`, `GET/POST /crear/<id_producto>`, `GET/POST /editar/<id_receta>`.
- Servicios clave:
  - Crear/editar receta completa.
  - Agregar ingredientes por unidad/cantidad normalizada.
  - Calcular costo y rendimiento.
  - Serializar y consultar detalle de receta.

## tienda
- Proposito: experiencia de cliente (menu, carrito, checkout, contacto).
- Rutas:
  - `GET/POST /`, `GET /menu`, `GET /carrito`.
  - `POST /agregar/<id>`, `GET/POST /reducir/<id>`, `GET/POST /aumentar/<id>`, `POST /actualizar_cantidad/`.
  - `POST /finalizar` (checkout).
  - `GET /materias-primas`.
  - `POST /contacto/enviar`.
- Servicios clave:
  - Obtener menu/categorias.
  - Gestion de carrito.
  - Finalizacion de pedido con validaciones de pago.
  - Flujo de contacto por correo.

## usuarios
- Proposito: administracion de usuarios internos y roles.
- Rutas:
  - `GET /`, `GET/POST /crear`, `GET /detalles`, `GET/POST /editar`, `POST /desactivar`, `POST /activar`.
- Servicios clave:
  - CRUD de usuario.
  - Activar/desactivar cuenta.
  - Obtener roles y nombres de rol.

## ventas
- Proposito: gestion de ventas internas y detalle de venta.
- Rutas:
  - `GET /`, `GET /detalles/<id_venta>`, `GET /nueva`, `POST /guardar`, `POST /completar/<id_venta>`, `POST /eliminar`.
- Servicios clave:
  - Crear y completar venta.
  - Calculo de costos/totales.
  - Disminucion de stock.
  - Agregar productos y editar venta.

## Notas de arquitectura
- Los modulos sin `services.py` delegan logica en rutas o utilidades compartidas.
- Varias capas comparten entidades SQLAlchemy definidas en `models.py`.
- Seguridad y permisos se apoyan en `flask_login` y utilidades de rol.
