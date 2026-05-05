"""POS blueprint."""
from flask import Blueprint

pos_bp = Blueprint("pos", __name__, template_folder="../../templates/pos")

from . import routes  # noqa: F401, E402
