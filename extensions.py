from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_pymongo import PyMongo
from pymongo import MongoClient
db = SQLAlchemy()
migrate = Migrate()
mongo = None

def init_extensions(app):
    global mongo
    
    db.init_app(app)
    migrate.init_app(app, db)
    
    try:
        mongo_client = MongoClient(app.config['MONGO_URI'])
        mongo = mongo_client.get_database("fondaGourmet")  # base de datos MongoDB
        mongo_client.servwer_info()  # Verificar conexión
        print("Conexión a MongoDB establecida correctamente.")
    except Exception as e:
        print(f"Error al conectar con MongoDB: {e}")
        app.mongo = None
        mongo = None