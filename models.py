from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, event
from flask_login import UserMixin
from sqlalchemy.ext.hybrid import hybrid_property
from werkzeug.security import generate_password_hash, check_password_hash
import datetime 
import uuid

db = SQLAlchemy()
from sqlalchemy import CheckConstraint

class Persona(db.Model):
    __tablename__ = 'personas'
    id_persona = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido_p = db.Column(db.String(50), nullable=False)
    apellido_m = db.Column(db.String(50))
    telefono = db.Column(db.String(10), unique=True, nullable=False)
    correo = db.Column(db.String(100), unique=True, nullable=False)
    direccion = db.Column(db.String(200))
    fecha_creacion = db.Column(db.DateTime, default=datetime.datetime.now, nullable=False)

    empleado = db.relationship('Empleado', back_populates='persona', uselist=False)
    cliente = db.relationship('Cliente', back_populates='persona', uselist=False)
    proveedor = db.relationship('Proveedor', back_populates='persona', uselist=False)
    
    __table_args__ = (
        CheckConstraint("telefono REGEXP '^[0-9]{10}$'", name='check_telefono'),
        CheckConstraint("correo REGEXP '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'", name='check_correo_empleado'),
    )

class Rol(db.Model):
    __tablename__ = 'roles'
    id_rol = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    
    usuarios = db.relationship('Usuario', back_populates='rol', lazy=True)

class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    id_usuario = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    contrasena = db.Column(db.Text, nullable=False)
    estado = db.Column(db.Boolean, default=True)
    fs_uniquifier = db.Column(db.String(255), unique=True, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.datetime.now, nullable=False)
    id_rol = db.Column(db.Integer, db.ForeignKey('roles.id_rol'), nullable=False)

    rol = db.relationship('Rol', back_populates='usuarios')
    empleado = db.relationship('Empleado', back_populates='usuario', uselist=False)
    cliente = db.relationship('Cliente', back_populates='usuario', uselist=False)
    producciones = db.relationship('Produccion', back_populates='usuario', lazy=True)
    compras = db.relationship('Compra', back_populates='usuario', lazy=True)
    ventas = db.relationship('Venta', back_populates='usuario', lazy=True)
    cajas = db.relationship('Caja', back_populates='usuario', lazy=True)
    
    # Métodos requeridos por Flask-Login
    def get_id(self):
        """Flask-Login necesita este método para obtener el ID del usuario"""
        return str(self.id_usuario)
    
    @property
    def is_active(self):
        """Flask-Login verifica si la cuenta está activa"""
        return self.estado
    
    # Método para verificar contraseña
    def check_password(self, password):
        """Verifica la contraseña del usuario"""
        return check_password_hash(self.contrasena, password)
    
    # Método para establecer contraseña
    def set_password(self, password):
        """Establece una nueva contraseña hasheada"""
        self.contrasena = generate_password_hash(password)
    
    def __repr__(self):
        return f'<Usuario {self.username}>'
 
class Empleado(db.Model):
    __tablename__ = 'empleados'
    id_empleado = db.Column(db.Integer, primary_key=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    id_persona = db.Column(db.Integer, db.ForeignKey('personas.id_persona'), nullable=False)
    
    usuario = db.relationship('Usuario', back_populates='empleado')
    persona = db.relationship('Persona', back_populates='empleado')
    
class Cliente(db.Model):
    __tablename__ = 'clientes'
    id_cliente = db.Column(db.Integer, primary_key=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    id_persona = db.Column(db.Integer, db.ForeignKey('personas.id_persona'), nullable=False)
    
    usuario = db.relationship('Usuario', back_populates='cliente')
    persona = db.relationship('Persona', back_populates='cliente')
    carrito = db.relationship('Carrito', back_populates='cliente', uselist=False)
    pedidos = db.relationship('Pedido', back_populates='cliente', lazy=True)
      
class Proveedor(db.Model):
    __tablename__ = 'proveedores'
    id_proveedor = db.Column(db.Integer, primary_key=True)
    id_persona = db.Column(db.Integer, db.ForeignKey('personas.id_persona'), nullable=False)
    id_categoria_proveedor = db.Column(db.Integer, db.ForeignKey('categorias_proveedor.id_categoria_proveedor'), nullable=False)
    estado = db.Column(db.Boolean, default=True)
    
    persona = db.relationship('Persona', back_populates='proveedor')
    categoria_proveedor = db.relationship('CategoriaProveedor', back_populates='proveedores')
    materias_primas = db.relationship('MateriaPrima', back_populates='proveedor', lazy=True)
    compras = db.relationship('Compra', back_populates='proveedor', lazy=True)


class CategoriaProveedor(db.Model):
    __tablename__ = 'categorias_proveedor'
    id_categoria_proveedor = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    descripcion = db.Column(db.Text)
    estado = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.datetime.now, nullable=False)

    proveedores = db.relationship('Proveedor', back_populates='categoria_proveedor', lazy=True)


class CategoriaIngrediente(db.Model):
    __tablename__ = 'categorias_ingrediente'
    id_categoria_ingrediente = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    descripcion = db.Column(db.Text)
    estado = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.datetime.now, nullable=False)

    materias_primas = db.relationship('MateriaPrima', back_populates='categoria_ingrediente', lazy=True)


class CategoriaPlatillo(db.Model):
    __tablename__ = 'categorias_platillo'
    id_categoria_platillo = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    descripcion = db.Column(db.Text)
    estado = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.datetime.now, nullable=False)

    productos = db.relationship('Producto', back_populates='categoria_platillo', lazy=True)
      
class Categoria(db.Model):
    __tablename__ = 'categorias'
    id_categoria = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    tipo_categoria = db.Column(db.String(20), default='platillo', nullable=False)  # 'platillo' | 'ingrediente'
    estado = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.datetime.now, nullable=False)
    
    __table_args__ = (
        CheckConstraint("tipo_categoria IN ('platillo', 'ingrediente')", name='check_tipo_categoria'),
    )
    
class MateriaPrima(db.Model):
    __tablename__ = 'materias_primas'
    id_materia = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    unidad_medida = db.Column(db.String(20), nullable=False)
    stock_actual = db.Column(db.Float, default=0, nullable=False)
    stock_minimo = db.Column(db.Float, nullable=False)
    precio = db.Column(db.Float, default=0, nullable=False)
    porcentaje_merma = db.Column(db.Float, default=0, nullable=False)
    factor_conversion = db.Column(db.Float, default=1, nullable=False)
    estado = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.datetime.now, nullable=False)

    id_categoria_ingrediente = db.Column(db.Integer, db.ForeignKey('categorias_ingrediente.id_categoria_ingrediente'), nullable=False)
    id_proveedor = db.Column(db.Integer, db.ForeignKey('proveedores.id_proveedor'), nullable=False)

    categoria_ingrediente = db.relationship('CategoriaIngrediente', back_populates='materias_primas')
    proveedor = db.relationship('Proveedor', back_populates='materias_primas')
    detalle_recetas = db.relationship('RecetaDetalle', back_populates='materia_prima', lazy=True)
    detalle_compras = db.relationship('DetalleCompra', back_populates='materia_prima', lazy=True)
    detalle_producciones = db.relationship('DetalleProduccion', back_populates='materia_prima', lazy=True)  

    __table_args__ = (
        CheckConstraint('stock_actual >= 0', name='check_stock_actual_materia_no_negativo'),
        CheckConstraint('stock_minimo >= 0', name='check_stock_minimo_materia_no_negativo'),
        CheckConstraint('porcentaje_merma >= 0 AND porcentaje_merma <= 100', name='check_porcentaje_merma_valido'),
        CheckConstraint('factor_conversion > 0', name='check_factor_conversion_positivo'),
        CheckConstraint("unidad_medida IN ('kg', 'g', 'l', 'ml', 'pz', 'unidad', 'botella', 'bulto', 'paquete', 'docena', 'caja', 'bolsa', 'costal')", name='check_unidad_medida_materia')
    )
    
    def convertir_a_gramos(self, cantidad: float) -> float:
        """Convierte cualquier cantidad a gramos (estándar interno)"""
        if self.unidad_medida in ['g', 'unidad', 'pz']:
            return cantidad
        elif self.unidad_medida == 'kg':
            return cantidad * 1000
        elif self.unidad_medida == 'l':
            return cantidad * 1000   # asumimos densidad 1 para líquidos (ajustable después)
        elif self.unidad_medida == 'ml':
            return cantidad
        elif self.unidad_medida in ['bulto', 'paquete', 'caja', 'docena']:
            return cantidad * self.factor_conversion
        return cantidad * self.factor_conversion

    def stock_real_disponible(self):
        """Stock usable después de aplicar merma"""
        stock_gramos = self.convertir_a_gramos(self.stock_actual)
        return stock_gramos * (1 - self.porcentaje_merma / 100)
    
class Producto(db.Model):
    __tablename__ = 'productos'
    id_producto = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    descripcion = db.Column(db.Text)
    precio = db.Column(db.Float, nullable=False)
    stock_actual = db.Column(db.Float, default=0, nullable=False)
    stock_minimo = db.Column(db.Float, nullable=False)
    imagen = db.Column(db.String(255))
    estado = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.datetime.now, nullable=False)
    
    id_categoria_platillo = db.Column(db.Integer, db.ForeignKey('categorias_platillo.id_categoria_platillo'), nullable=False)
   
    categoria_platillo = db.relationship('CategoriaPlatillo', back_populates='productos')
    recetas = db.relationship('Receta', back_populates='producto', lazy=True)
    detalle_ventas = db.relationship('DetalleVenta', back_populates='producto', lazy=True)
    detalle_producciones = db.relationship('DetalleProduccion', back_populates='producto', lazy=True)
    detalle_pedidos = db.relationship('DetallePedido', back_populates='producto', lazy=True)    
    detalle_carritos = db.relationship('DetalleCarrito', back_populates='producto', lazy=True)
    
    __table_args__ = (
        CheckConstraint('precio >= 0', name='check_precio_producto_no_negativo'),
        CheckConstraint('stock_actual >= 0', name='check_stock_actual_producto_no_negativo'),
        CheckConstraint('stock_minimo >= 0', name='check_stock_minimo_producto_no_negativo'),
        CheckConstraint("imagen REGEXP '^((https?://.*\\.(png|jpg|jpeg|gif|svg|webp))|(uploads/.*\\.(png|jpg|jpeg|gif|svg|webp)))$'", name='check_formato_imagen'),
    )   

class Receta(db.Model):
    __tablename__ = 'recetas'
    id_receta = db.Column(db.Integer, primary_key=True)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False)
    rendimiento = db.Column(db.Float, default=0, nullable=False)
    cantidad_produccion = db.Column(db.Float, default=1, nullable=False)
    unidad_produccion = db.Column(db.String(20), default='pz', nullable=False)
    nota = db.Column(db.Text)
    estado = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.datetime.now, nullable=False)
    
    detalles = db.relationship('RecetaDetalle', back_populates='receta', cascade="all, delete-orphan")
    producto = db.relationship('Producto', back_populates='recetas')
    
    def calcular_rendimiento_automatico(self):
        """Calcula el rendimiento basado en el total de ingredientes"""
        if not self.detalles:
            return 0
        total_ingredientes = sum(d.cantidad for d in self.detalles)
        return 100.0 if total_ingredientes > 0 else 0

class RecetaDetalle(db.Model):
    __tablename__ = 'receta_detalle'
    id_detalle = db.Column(db.Integer, primary_key=True)
    cantidad = db.Column(db.Float, nullable=False)
    id_receta = db.Column(db.Integer, db.ForeignKey('recetas.id_receta'), nullable=False)
    id_materia = db.Column(db.Integer, db.ForeignKey('materias_primas.id_materia'), nullable=False)
    unidad_medida = db.Column(db.String(20), default='g', nullable=False)
    cantidad_requerida = db.Column(db.Float, default=0, nullable=False)

    receta = db.relationship('Receta', back_populates='detalles')
    materia_prima = db.relationship('MateriaPrima', back_populates='detalle_recetas')
    
    def cantidad_ajustada_merma(self):
        """Compatibilidad: devuelve la cantidad requerida actual sin ajustes de merma."""
        return self.cantidad_requerida or self.cantidad
    
class Produccion(db.Model):
    __tablename__ = 'producciones'
    id_produccion = db.Column(db.Integer, primary_key=True)
    fecha_solicitud = db.Column(db.DateTime, nullable=False)
    fecha_completada = db.Column(db.DateTime)
    fecha_necesaria = db.Column(db.DateTime, nullable=False)
    estado = db.Column(db.String(50), nullable=False, default='Solicitada')
    id_pedido = db.Column(db.Integer, db.ForeignKey('pedidos.id_pedido'))
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.datetime.now, nullable=False)
    pedido=db.relationship('Pedido', back_populates='produccion', uselist=False)
    detalles = db.relationship('DetalleProduccion', back_populates='produccion', cascade="all, delete-orphan")
    usuario = db.relationship('Usuario', back_populates='producciones')
    
    __table_args__ = (
        CheckConstraint("estado IN ('Solicitada', 'En Proceso', 'Completada')", name='check_estado_produccion'),
    )

class DetalleProduccion(db.Model):
    __tablename__ = 'detalle_produccion'
    id_detalle = db.Column(db.Integer, primary_key=True)
    cantidad = db.Column(db.Float, nullable=False)
    id_produccion = db.Column(db.Integer, db.ForeignKey('producciones.id_produccion'), nullable=False)
    id_materia = db.Column(db.Integer, db.ForeignKey('materias_primas.id_materia'), nullable=True)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False)
    completado = db.Column(db.Boolean, default=False, nullable=False)
    cantidad_producida = db.Column(db.Float, default=0, nullable=False)

    produccion = db.relationship('Produccion', back_populates='detalles')
    materia_prima = db.relationship('MateriaPrima', back_populates='detalle_producciones')
    producto = db.relationship('Producto', back_populates='detalle_producciones')

class Compra(db.Model):
    __tablename__ = 'compras'
    id_compra = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, nullable=False)
    total = db.Column(db.Float, nullable=False)
    fecha_entrega = db.Column(db.DateTime)
    metodo_pago = db.Column(db.String(50))
    tarjeta_titular = db.Column(db.String(120))
    tarjeta_ultimos4 = db.Column(db.String(4))
    tarjeta_vencimiento = db.Column(db.String(5))
    estado = db.Column(db.String(50), nullable=False, default='Solicitada')
    desde_produccion = db.Column(db.Boolean, nullable=False, default=False)
    id_proveedor = db.Column(db.Integer, db.ForeignKey('proveedores.id_proveedor'))
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.datetime.now, nullable=False)

    proveedor = db.relationship('Proveedor', back_populates='compras')
    detalles = db.relationship('DetalleCompra', back_populates='compra', cascade="all, delete-orphan")
    usuario = db.relationship('Usuario', back_populates='compras')

    __table_args__ = (
        CheckConstraint("estado IN ('Solicitada', 'En Camino', 'Completada', 'Cancelada')", name='check_estado_compra'),
        CheckConstraint("metodo_pago IN ('Efectivo', 'Tarjeta', 'Transferencia')", name='check_metodo_pago_compra'),
        CheckConstraint('total >= 0', name='check_total_compra_no_negativo'),
    )
    
class DetalleCompra(db.Model):
    __tablename__ = 'detalle_compra'
    id_detalle = db.Column(db.Integer, primary_key=True)
    id_compra = db.Column(db.Integer, db.ForeignKey('compras.id_compra'), nullable=False)
    id_materia = db.Column(db.Integer, db.ForeignKey('materias_primas.id_materia'), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    precio_u = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    recibido = db.Column(db.Boolean, default=False, nullable=False)
  
    compra = db.relationship('Compra', back_populates='detalles')
    materia_prima = db.relationship('MateriaPrima', back_populates='detalle_compras')
    
    __table_args__ = (
        CheckConstraint('cantidad > 0', name='check_cantidad_positiva'),
        CheckConstraint('precio_u >= 0', name='check_precio_u_no_negativo'),
        CheckConstraint('subtotal >= 0', name='check_subtotal_no_negativo'),
    )
    
class Venta(db.Model):
    __tablename__ = 'ventas'
    id_venta = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, nullable=False)
    total = db.Column(db.Float, nullable=False)
    metodo_pago = db.Column(db.String(50), nullable=False)
    estado = db.Column(db.String(50), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.datetime.now, nullable=False)
    # Datos de tarjeta (solo si metodo_pago es 'Tarjeta')
    tarjeta_titular = db.Column(db.String(120))
    tarjeta_numero = db.Column(db.String(4))  # Guardamos solo los últimos 4 dígitos por seguridad
    tarjeta_vencimiento = db.Column(db.String(5))  # MM/YY

    usuario = db.relationship('Usuario', back_populates='ventas')
    detalles = db.relationship('DetalleVenta', back_populates='venta', cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint("estado IN ('Pendiente', 'Completada', 'Cancelada')", name='check_estado_venta'),
        CheckConstraint("metodo_pago IN ('Efectivo', 'Tarjeta', 'Transferencia')", name='check_metodo_pago_venta'),
        CheckConstraint('total >= 0', name='check_total_venta_no_negativo'),
    )
    
class DetalleVenta(db.Model):
    __tablename__ = 'detalle_venta'
    id_detalle = db.Column(db.Integer, primary_key=True)
    cantidad = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    id_venta = db.Column(db.Integer, db.ForeignKey('ventas.id_venta'), nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False)
    
    venta = db.relationship('Venta', back_populates='detalles')
    producto= db.relationship('Producto', back_populates='detalle_ventas')
    
    __table_args__ = (
        CheckConstraint('cantidad > 0', name='check_cantidad_venta_positiva'),
        CheckConstraint('subtotal >= 0', name='check_subtotal_venta_no_negativo'),
    )
 
class Pedido(db.Model):
    __tablename__ = 'pedidos'
    id_pedido = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, nullable=False)
    fecha_entrega = db.Column(db.DateTime)
    estado = db.Column(db.String(50), nullable=False, default='Pendiente')
    id_cliente = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente'), nullable=False, default=1)
    requiere_produccion = db.Column(db.Boolean, default=False)
    total = db.Column(db.Float, nullable=False)
    cliente = db.relationship('Cliente', back_populates='pedidos')
    produccion = db.relationship('Produccion', back_populates='pedido', uselist=False, cascade="all, delete-orphan")
    detalles = db.relationship('DetallePedido', back_populates='pedido', cascade="all, delete-orphan")
    meta_pedido = db.relationship('PedidoMeta', back_populates='pedido', uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("estado IN ('Pendiente', 'En Proceso', 'Producido', 'Completado', 'Pagado', 'Cancelado')", name='check_estado_pedido'),
        CheckConstraint('total >= 0', name='check_total_pedido_no_negativo'),
    )


class PedidoMeta(db.Model):
    __tablename__ = 'pedidos_meta'
    id_pedido = db.Column(db.Integer, db.ForeignKey('pedidos.id_pedido'), primary_key=True)
    metodo_pago = db.Column(db.String(50), nullable=False, default='Efectivo')
    tarjeta_titular = db.Column(db.String(120))
    tarjeta_ultimos4 = db.Column(db.String(4))
    tarjeta_vencimiento = db.Column(db.String(5))
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)

    pedido = db.relationship('Pedido', back_populates='meta_pedido')
    usuario = db.relationship('Usuario')

    __table_args__ = (
        CheckConstraint("metodo_pago IN ('Efectivo', 'Tarjeta', 'Transferencia')", name='check_metodo_pago_pedido_meta'),
    )
    
class DetallePedido(db.Model):
    __tablename__ = 'detalle_pedido'
    id_detalle = db.Column(db.Integer, primary_key=True)
    cantidad = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    id_pedido = db.Column(db.Integer, db.ForeignKey('pedidos.id_pedido'), nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False)
    atendido = db.Column(db.Boolean, default=False, nullable=False)
    en_produccion = db.Column(db.Boolean, default=False, nullable=False)

    pedido = db.relationship('Pedido', back_populates='detalles')
    producto= db.relationship('Producto', back_populates='detalle_pedidos')

    __table_args__ = (
        CheckConstraint('cantidad > 0', name='check_cantidad_pedido_positiva'),
        CheckConstraint('subtotal >= 0', name='check_subtotal_pedido_no_negativo'),
    )
 
class Carrito(db.Model):
    __tablename__ = 'carritos'
    id_carrito = db.Column(db.Integer, primary_key=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.datetime.now, nullable=False)
    estado = db.Column(db.String(20), nullable=False, default='Abierto')
    total = db.Column(db.Float, default=0, nullable=False)
    metodo_pago = db.Column(db.String(50))
    id_cliente = db.Column(db.Integer, db.ForeignKey('clientes.id_cliente'), nullable=False)
    
    cliente = db.relationship('Cliente', back_populates='carrito')
    detalles = db.relationship('DetalleCarrito', back_populates='carrito', lazy=True, cascade="all, delete-orphan")
    
class DetalleCarrito(db.Model):
    __tablename__ = 'detalle_carrito'
    id_detalle = db.Column(db.Integer, primary_key=True)
    cantidad = db.Column(db.Integer, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    id_carrito = db.Column(db.Integer, db.ForeignKey('carritos.id_carrito'), nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey('productos.id_producto'), nullable=False)

    carrito = db.relationship('Carrito', back_populates='detalles')
    producto = db.relationship('Producto', back_populates='detalle_carritos')

    __table_args__ = (
        CheckConstraint('cantidad > 0', name='check_cantidad_carrito_positiva'),
        CheckConstraint('subtotal >= 0', name='check_subtotal_carrito_no_negativo'),
    )
 
class Caja(db.Model):
    __tablename__ = 'caja'
    id_caja = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, nullable=False)
    monto_inicial = db.Column(db.Float, nullable=False)
    monto_final = db.Column(db.Float, nullable=True)
    estado = db.Column(db.String(20), nullable=False, default='Abierta')
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuarios.id_usuario'), nullable=False)

    usuario = db.relationship('Usuario', back_populates='cajas')
    movimientos = db.relationship('MovimientoCaja', back_populates='caja', lazy=True, cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("estado IN ('Abierta', 'Cerrada')", name='check_estado_caja'),
        CheckConstraint('monto_inicial >= 0', name='check_monto_inicial_no_negativo'),
        CheckConstraint('monto_final >= 0', name='check_monto_final_no_negativo'),
    )

class MovimientoCaja(db.Model):
    __tablename__ = 'movimientos_caja'
    id_movimiento = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # Ingreso o Egreso
    monto = db.Column(db.Float, nullable=False)
    descripcion = db.Column(db.Text)
    id_caja = db.Column(db.Integer, db.ForeignKey('caja.id_caja'), nullable=False)

    caja = db.relationship('Caja', back_populates='movimientos')

    __table_args__ = (
        CheckConstraint("tipo IN ('Ingreso', 'Egreso')", name='check_tipo_movimiento'),
        CheckConstraint('monto >= 0', name='check_monto_movimiento_no_negativo'),
    )

