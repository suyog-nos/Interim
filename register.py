from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from werkzeug.security import generate_password_hash
from forms import RegistrationForm
from config import conn
from datetime import datetime
import mysql.connector

register_bp = Blueprint('register', __name__)

@register_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    
    if form.validate_on_submit():
        try:
            # Get a new cursor for this operation
            cursor = conn.cursor(dictionary=True)
            
            try:
                # Check if email already exists
                cursor.execute("SELECT user_id FROM users WHERE email = %s", (form.email.data,))
                if cursor.fetchone() is not None:
                    flash('Email already registered. Please use a different email.', 'error')
                    return render_template('register.html', form=form)
                
                # Hash the password
                hashed_password = generate_password_hash(
                    form.password.data,
                    method='pbkdf2:sha256',
                    salt_length=16
                )
                
                # Insert new user
                cursor.execute(
                    """
                    INSERT INTO users 
                    (first_name, last_name, email, phone, hashed_password, role, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        form.first_name.data.strip(),
                        form.last_name.data.strip(),
                        form.email.data.lower().strip(),
                        form.phone.data.strip(),
                        hashed_password,
                        'Customer',  # Default role
                        datetime.utcnow()
                    )
                )
                
                conn.commit()
                cursor.close()
                
                # Show success message and redirect to login
                flash('Registration successful! Please log in to continue.', 'success')
                return redirect(url_for('login.login'))
                
            except mysql.connector.Error as err:
                conn.rollback()
                flash(f'Database error: {err.msg}', 'error')
                print(f"Database error: {err}")
                return render_template('register.html', form=form)
            finally:
                if cursor:
                    cursor.close()
            
        except Exception as e:
            conn.rollback()
            flash('An error occurred during registration. Please try again.', 'error')
            print(f"Registration error: {str(e)}")
    
    # If form not submitted or validation fails
    if request.method == 'POST':
        # Add form validation errors to flash messages
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", 'error')
    
    return render_template('register.html', form=form)


# ===== Staff Creation (Users Management) START =====
@register_bp.route('/create-staff', methods=['POST'])
def create_staff():
    try:
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '')

        # Basic validation
        if not all([first_name, last_name, phone, email, password]):
            return jsonify({
                'success': False,
                'error': 'All fields are required to add a staff member.'
            }), 400

        cursor = conn.cursor(dictionary=True)

        try:
            # Check if email already exists
            cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
            if cursor.fetchone() is not None:
                return jsonify({
                    'success': False,
                    'error': 'Email already registered. Please use a different email.'
                }), 400

            # Hash the password
            hashed_password = generate_password_hash(
                password,
                method='pbkdf2:sha256',
                salt_length=16
            )

            # Insert new staff user
            cursor.execute(
                """
                INSERT INTO users 
                (first_name, last_name, email, phone, hashed_password, role, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    first_name,
                    last_name,
                    email,
                    phone,
                    hashed_password,
                    'Staff',
                    datetime.utcnow()
                )
            )

            conn.commit()
            return jsonify({
                'success': True,
                'message': 'Staff member added successfully.'
            })

        except mysql.connector.Error as err:
            conn.rollback()
            print(f"Staff creation database error: {err}")
            return jsonify({
                'success': False,
                'error': f'Database error while creating staff: {err.msg}'
            }), 500
            
        finally:
            if cursor:
                cursor.close()

    except Exception as e:
        conn.rollback()
        print(f"Staff creation error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An unexpected error occurred while adding staff. Please try again.'
        }), 500

# ===== Staff Creation (Users Management) END =====