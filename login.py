from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.security import check_password_hash
from config import conn
import mysql.connector

# Blueprint dedicated to authentication / login
login_bp = Blueprint('login', __name__)

def get_user_by_email(email: str):
    """Fetch a single user record by email."""
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT user_id, first_name, last_name, email, hashed_password
            FROM users
            WHERE email = %s
            """,
            (email,),
        )
        return cursor.fetchone()
    except mysql.connector.Error as err:
        print(f"Database error while fetching user: {err}")
        return None
    finally:
        if cursor:
            cursor.close()

@login_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handle user login - simplified version without session management.
    Validates credentials and shows success message.
    """
    if request.method == 'GET':
        return render_template('login.html')
    
    if request.method == 'POST':
        # Get form data
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        #  validation
        if not email or not password:
            flash('Please enter both email and password.', 'error')
            return render_template('login.html')

        # Look up user by email
        user = get_user_by_email(email)

        if not user or not user.get('hashed_password'):
            flash('Invalid email or password.', 'error')
            return render_template('login.html')

        # Verify hashed password
        if not check_password_hash(user['hashed_password'], password):
            flash('Invalid email or password.', 'error')
            return render_template('login.html')
            
        # Successful authentication - redirect to dashboard
        return redirect(url_for('login.dashboard', logged_in='true', show_success='true'))

@login_bp.route('/dashboard')
def dashboard():
    """
     dashboard page after successful login.
    """
    # Check if user is logged in ( session check)
    if not request.args.get('logged_in'):
        flash('Please login to access dashboard.', 'error')
        return redirect(url_for('login.login'))
    
    # Show login success message if coming from login
    if request.args.get('show_success') == 'true':
        flash('Login successful! You are now logged in.', 'success')
    
    return render_template('dashboard.html')

@login_bp.route('/logout')
def logout():
    """
    Handle user logout
    redirects to index page.
    """
    flash('You have been logged out successfully!', 'success')
    return redirect('/')