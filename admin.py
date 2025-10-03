from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from db import get_connection

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Rotta per area admin
@admin_bp.route("/")
def home_admin():
    return render_template("home_admin.html")

@admin_bp.route("/admin_aste")
def admin_aste():
    return render_template("admin_aste.html")

