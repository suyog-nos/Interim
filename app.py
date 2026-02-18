from flask import Flask, session, request
from config import conn
from products import products_bp
from routes import main_bp
from register import register_bp
from login import login_bp
import os
from access_control import redirect_by_role, is_authorized

app = Flask(__name__)
app.secret_key = '8c145cee1bbf8b085673ad53959a750e65d6d54e1159cf05fe619a8899fcab58'  # Secure secret key


@app.before_request
def enforce_role_access():
    endpoint = request.endpoint
    if endpoint == 'static':
        return
    role = session.get('role', 'Guest')
    if not endpoint or not is_authorized(endpoint, role):
        return redirect_by_role()


@app.context_processor
def inject_welcome_popup():
    show_welcome = session.pop('show_welcome', False)
    name = session.get('name', '')
    return {
        'welcome_name': name,
        'show_welcome': show_welcome
    }

# Register blueprints
app.register_blueprint(main_bp)
app.register_blueprint(products_bp, url_prefix='/products')
app.register_blueprint(register_bp, url_prefix='/auth')
app.register_blueprint(login_bp)  # Handles /login


if __name__ == '__main__':
    app.run(debug=True, port=5000)

# Force update
