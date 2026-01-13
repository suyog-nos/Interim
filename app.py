from flask import Flask, render_template
from config import conn
from register import register_bp
from login import login_bp

# Initialize Flask application
app = Flask(__name__)
# Secret key for session management and flash messages
app.secret_key = 'dev-secret-key'

# Home page route
@app.route('/')
def index():
    return render_template('index.html')

# Register authentication blueprints
app.register_blueprint(register_bp, url_prefix='/auth')
app.register_blueprint(login_bp)

# Run the application
if __name__ == '__main__':
    app.run(debug=True, port=5000)
