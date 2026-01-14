from flask import Blueprint, render_template, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash
from config import conn
from datetime import datetime
import mysql.connector

# Blueprint for user registration
register_bp = Blueprint('register', __name__)

@register_bp.route('/register', methods=['GET', 'POST'])
def register():
    # Handle user registration
    if request.method == 'POST':
        # Get form data from registration page
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # validation - check all fields are filled
        if not all([first_name, last_name, email, phone, password, confirm_password]):
            flash('All fields are required.', 'error')
            return render_template('register.html')
        
        # Check if passwords match
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')
        
        # email validation
        if '@' not in email or '.' not in email:
            flash('Please enter a valid email address.', 'error')
            return render_template('register.html')
        
        # phone validation - check for exactly 10 digits
        if len(phone) != 10 or not phone.isdigit():
            flash('Please enter a valid 10-digit phone number.', 'error')
            return render_template('register.html')
        
        try:
            # Check if email already exists in database
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
            if cursor.fetchone() is not None:
                flash('Email already registered. Please use a different email.', 'error')
                return render_template('register.html')
            
            # Hash password for security
            hashed_password = generate_password_hash(
                password,
                method='pbkdf2:sha256',
                salt_length=16
            )
            
            # Insert new user into database
            cursor.execute(
                """
                INSERT INTO users 
                (first_name, last_name, email, phone, hashed_password, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    first_name,
                    last_name,
                    email,
                    phone,
                    hashed_password,
                    datetime.utcnow()
                )
            )
            
            # Save changes to database
            conn.commit()
            cursor.close()
            
            # Show success message to user
            flash('Registration successful! You can now login.', 'success')
            return render_template('register.html')
            
        except mysql.connector.Error as err:
            # Handle database errors
            conn.rollback()
            flash(f'Database error: {err.msg}', 'error')
            print(f"Database error: {err}")
            return render_template('register.html')
        finally:
            # Always close cursor
            if 'cursor' in locals():
                cursor.close()
    
    # GET request - show registration form
    return render_template('register.html')
