from flask import Blueprint, render_template, request, redirect, url_for, flash, session, url_for
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
            SELECT user_id, first_name, last_name, email, hashed_password, role
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
    Handle user login.

    Requirements implemented:
    - Validate email/username and password presence
    - Verify hashed password from DB
    - Store user_id, role, and name in the session
    - Redirect after login based on role:
        * Customer -> products page
        * Staff    -> POS page
        * Admin    -> dashboard
    - On failure, redirect with error message to prevent form resubmission
    """
    if request.method == 'GET':
        # Clear any existing error messages on fresh page load
        if 'login_email' in session or 'error' in request.args:
            email = session.get('login_email', '')
            return render_template('login.html', email=email)
        return render_template('login.html')
    if request.method == 'POST':
        # Accept either `email` or `username` from the form (UI currently uses `username`)
        raw_identifier = (
            request.form.get('email')
            or request.form.get('username')
            or ''
        ).strip().lower()
        password = request.form.get('password', '')

        # Store the email in session for repopulating the form
        session['login_email'] = raw_identifier if raw_identifier else ''
        
        # Basic validation
        if not raw_identifier or not password:
            flash('Please enter both email and password.', 'error')
            return redirect(url_for('login.login', error='credentials_required'))

        # Look up user by email
        user = get_user_by_email(raw_identifier)

        if not user or not user.get('hashed_password'):
            flash('Invalid email or password.', 'error')
            return redirect(url_for('login.login', error='invalid_credentials'))

        # Verify hashed password
        if not check_password_hash(user['hashed_password'], password):
            flash('Invalid email or password.', 'error')
            return redirect(url_for('login.login', error='invalid_credentials'))
            
        # Clear the stored email on successful login
        if 'login_email' in session:
            session.pop('login_email')

        # Successful authentication – set up session
        full_name = f"{user.get('first_name', '').strip()} {user.get('last_name', '').strip()}".strip()
        session['user_id'] = user['user_id']
        session['role'] = user.get('role') or 'Customer'
        session['name'] = full_name or user['email']
        session['show_welcome'] = True

        role = session['role']

        # Role-based redirect
        if role == 'Admin':
            return redirect(url_for('main.dashboard'))
        elif role == 'Staff':
            return redirect(url_for('main.pos'))
        else:
            # Default / Customer -> products page
            return redirect(url_for('products.index'))

    # GET: render login page
    return render_template('login.html')


@login_bp.route('/logout')
def logout():
    """
    Handle user logout.
    Clears the session and redirects to the login page.
    """
    # Clear all session data
    session.clear()
    # Flash a logout message
    flash('You have been successfully logged out.', 'success')
    # Redirect to login page
    return redirect(url_for('login.login'))

