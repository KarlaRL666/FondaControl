from flask import Blueprint

clientes = Blueprint('clientes', __name__)

from . import routes