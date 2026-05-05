# FondaControl – Sistema POS & Control Productivo para Fondas

> Sistema integral para fondas y cocinas económicas: punto de venta táctil, control productivo con recetas y costos teóricos, e inventario en tiempo real con dashboard analítico.

---

## 📋 Características

### 🛒 Módulo POS
- Ventas rápidas con interfaz táctil optimizada (Bootstrap 5)
- Gestión de pedidos abiertos con filtro por categoría
- Impresión de tickets (comanda y cuenta) desde el navegador
- Cierre de caja con reporte de turno (efectivo + tarjeta)
- Historial de ventas con paginación

### 🍳 Control Productivo
- Recetas por platillo con ingredientes y proporciones
- Costo teórico automático calculado desde insumos
- Margen de ganancia por platillo en tiempo real
- Control de inventario: entradas, salidas y mermas
- Alertas de stock bajo y productos próximos a caducar

### 📊 Dashboard Analítico
- KPIs diarios: ventas, alertas y transacciones
- Gráficos interactivos (Chart.js): ventas por día/semana/mes
- Platillos más vendidos (doughnut chart)
- Análisis de rentabilidad: ingresos vs costos
- Exportación de reportes en **PDF** y **Excel**

---

## 🧰 Stack Tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Python 3.11+ · Flask 3 · Blueprints |
| ORM / MySQL | SQLAlchemy 2 · Flask-SQLAlchemy · PyMySQL |
| Logs / Analytics | MongoDB · PyMongo |
| Autenticación | Flask-Login · bcrypt |
| Seguridad | Flask-WTF (CSRF) · Headers de seguridad |
| Frontend | HTML5 · CSS3 · Bootstrap 5 · Chart.js 4 |
| Plantillas | Jinja2 |
| Exportación | reportlab (PDF) · openpyxl (Excel) |
| Contenedores | Docker · Docker Compose |
| Servidor prod. | Gunicorn |

---

## 🚀 Inicio Rápido

### Con Docker Compose (recomendado)

```bash
# 1. Clonar el repositorio
git clone https://github.com/KarlaRL666/FondaControl---Sistema-POS-Control-Productivo-para-Fondas.git
cd FondaControl---Sistema-POS-Control-Productivo-para-Fondas

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# 3. Levantar servicios
docker-compose up -d

# 4. Crear tablas y usuario admin
docker-compose exec web python -c "
from app import create_app; from app.extensions import db
from app.models.user import User
app = create_app()
with app.app_context():
    db.create_all()
    u = User(username='admin', email='admin@fonda.com', role='admin')
    u.set_password('admin123')
    db.session.add(u); db.session.commit()
    print('Admin creado correctamente')
"

# 5. Abrir navegador en http://localhost:5000
```

### Instalación local

```bash
# 1. Crear entorno virtual
python -m venv .venv
source .venv/bin/activate   # Linux / macOS
.venv\Scripts\activate      # Windows

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con datos de MySQL y MongoDB

# 4. Crear base de datos MySQL
mysql -u root -p -e "CREATE DATABASE fondacontrol_db;"
mysql -u root -p -e "CREATE USER 'fondacontrol'@'localhost' IDENTIFIED BY 'tu_password';"
mysql -u root -p -e "GRANT ALL PRIVILEGES ON fondacontrol_db.* TO 'fondacontrol'@'localhost';"

# 5. Migrar base de datos
flask db init
flask db migrate -m "initial"
flask db upgrade

# 6. Crear usuario admin
python -c "
from app import create_app; from app.extensions import db
from app.models.user import User
app = create_app()
with app.app_context():
    u = User(username='admin', email='admin@fonda.com', role='admin')
    u.set_password('admin123'); db.session.add(u); db.session.commit()
    print('Admin creado')
"

# 7. Ejecutar en desarrollo
flask run
```

---

## 🗂️ Estructura del Proyecto

```
fondacontrol/
├── app/
│   ├── __init__.py              # Application factory
│   ├── config.py                # Configuraciones (dev/prod/test)
│   ├── extensions.py            # Extensiones Flask (db, login_manager…)
│   ├── models/
│   │   ├── user.py              # Usuario con bcrypt
│   │   ├── product.py           # Platillo y categoría
│   │   ├── recipe.py            # Receta e ingredientes
│   │   ├── inventory.py         # Insumos y movimientos
│   │   └── sale.py              # Venta, ítem y cierre de caja
│   ├── blueprints/
│   │   ├── auth/                # Login / logout / gestión usuarios
│   │   ├── pos/                 # Punto de venta
│   │   ├── inventory/           # Control productivo
│   │   └── dashboard/           # Analítica y reportes
│   ├── templates/               # Jinja2 (base + por módulo)
│   └── static/                  # CSS, JS, imágenes
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_models.py
│   └── test_pos.py
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── run.py
```

---

## 🔐 Seguridad

- **Contraseñas** hasheadas con **bcrypt** (salt rounds configurables)
- **CSRF** protegido en todos los formularios con Flask-WTF
- **Headers de seguridad** en cada respuesta: `X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`, `Referrer-Policy`, `HSTS` (producción)
- **Variables de entorno** para secretos (nunca en código fuente)
- **SQL Injection** prevenida por SQLAlchemy ORM (parámetros ligados)
- **XSS** mitigado por autoescapado de Jinja2 y Content-Type headers
- Roles de usuario: `admin`, `cajero`, `cocinero`
- Protección de rutas con `@login_required` en todos los blueprints

---

## 🧪 Tests

```bash
# Instalar dependencias de test
pip install pytest pytest-flask

# Ejecutar tests (SQLite en memoria, sin MySQL)
pytest tests/ -v

# Con cobertura
pip install pytest-cov
pytest tests/ --cov=app --cov-report=html
```

---

## 📡 Endpoints API

### POS
| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/pos/` | Terminal POS |
| `POST` | `/pos/ventas` | Crear nueva venta |
| `GET` | `/pos/ventas/<id>` | Detalle de venta (JSON) |
| `POST` | `/pos/ventas/<id>/items` | Agregar ítem |
| `DELETE` | `/pos/ventas/<id>/items/<item_id>` | Eliminar ítem |
| `POST` | `/pos/ventas/<id>/pagar` | Procesar pago |
| `POST` | `/pos/ventas/<id>/cancelar` | Cancelar venta |
| `GET` | `/pos/ventas/<id>/ticket` | Vista de ticket |
| `POST` | `/pos/cierre-caja` | Registrar cierre |
| `GET` | `/pos/historial` | Historial paginado |

### Dashboard (JSON)
| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/dashboard/api/ventas?period=week` | Ventas diarias |
| `GET` | `/dashboard/api/platillos-mas-vendidos` | Top productos |
| `GET` | `/dashboard/api/rentabilidad` | Ingresos vs costos |
| `GET` | `/dashboard/reporte/pdf` | Exportar PDF |
| `GET` | `/dashboard/reporte/excel` | Exportar Excel |

### Inventario
| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/inventario/` | Lista de insumos |
| `GET/POST` | `/inventario/insumos/nuevo` | Crear insumo |
| `GET/POST` | `/inventario/insumos/<id>/editar` | Editar insumo |
| `GET/POST` | `/inventario/movimientos` | Registrar movimiento |
| `GET` | `/inventario/platillos` | Lista de platillos |
| `GET/POST` | `/inventario/recetas/<id>` | Gestionar receta |

---

## 🐳 Variables de Entorno

| Variable | Descripción | Ejemplo |
|---|---|---|
| `SECRET_KEY` | Clave secreta Flask | `una-clave-muy-larga` |
| `MYSQL_HOST` | Host MySQL | `localhost` |
| `MYSQL_PORT` | Puerto MySQL | `3306` |
| `MYSQL_USER` | Usuario MySQL | `fondacontrol` |
| `MYSQL_PASSWORD` | Contraseña MySQL | `mipassword` |
| `MYSQL_DATABASE` | Base de datos | `fondacontrol_db` |
| `MONGO_URI` | URI de MongoDB | `mongodb://localhost:27017/logs` |
| `FLASK_ENV` | Entorno | `development` / `production` |

---

## 📄 Licencia

MIT © 2024 – FondaControl
