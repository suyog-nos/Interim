from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
import re
from forms import RegistrationForm
from config import conn
from werkzeug.security import generate_password_hash, check_password_hash
import os

# Create a Blueprint for all routes
main_bp = Blueprint('main', __name__)


def get_cursor():
    """Helper function to get a new cursor for each request"""
    return conn.cursor()


# ===== Main Pages =====
@main_bp.route('/')
def index():
    role = session.get('role', 'Guest')
    if role == 'Admin':
        return redirect(url_for('main.dashboard'))
    elif role == 'Staff':
        return redirect(url_for('main.pos'))
    elif role == 'Customer':
        return redirect(url_for('products.index'))
    return render_template('index.html')

@main_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            with get_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users 
                    (first_name, last_name, email, phone, password)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        form.first_name.data,
                        form.last_name.data,
                        form.email.data,
                        form.phone.data,
                        form.password.data
                    )
                )
            conn.commit()
            flash(f'Account created for {form.first_name.data}!', 'success')
            return redirect(url_for('login.login'))
        except Exception as e:
            conn.rollback()
            flash(f'Error creating account: {e}', 'danger')
    return render_template('register.html', form=form)

# ===== Dashboard & POS =====
@main_bp.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@main_bp.route('/pos', methods=['GET', 'POST'])
def pos():
    if request.method == 'POST':
        # Handle POS form submission
        try:
            data = request.get_json()
            
            # In a real app, you would save the order to the database here
            print('Order received:', data)
            
            # Example of what you might do with the order data:
            # 1. Create order record
            # 2. Create order items
            # 3. Update inventory
            # 4. Process payment
            
            return {'status': 'success', 'message': 'Order processed successfully'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}, 500
    
    # GET request - show POS interface
    try:
        with get_cursor() as cursor:
            # Get products from database
            cursor.execute("""
                SELECT p.product_id, p.name, p.price, p.stock_quantity, c.name as category 
                FROM products p 
                LEFT JOIN categories c ON p.category_id = c.category_id
                ORDER BY c.name, p.name
            """)
            products = cursor.fetchall()
            
            # Convert to list of dictionaries for JSON serialization with stock info
            products_list = []
            for product in products:
                products_list.append({
                    'id': product[0],
                    'name': product[1],
                    'price': float(product[2]),
                    'stock': product[3],
                    'category': product[4] or 'Uncategorized',
                    'available': product[3] > 0  # Add availability flag
                })
                
        return render_template('POS.html', products=products_list)
        
    except Exception as e:
        print(f'Error loading POS: {str(e)}')
        flash('Error loading POS system', 'danger')
        return render_template('POS.html', products=[])

@main_bp.route('/manage-products')
def manage_products():
    return render_template('manage-products.html')

@main_bp.route('/debug/db')
def debug_db():
    try:
        with get_cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            
            products_info = {}
            table_exists = any('products' in table for table in tables)
            
            if table_exists:
                cursor.execute("DESCRIBE products")
                products_info['structure'] = cursor.fetchall()
                cursor.execute("SELECT * FROM products LIMIT 5")
                products_info['sample_data'] = cursor.fetchall()
            
            return {
                'tables': tables,
                'products': products_info if table_exists else 'No products table found',
                'database': cursor.connection.database
            }
    except Exception as e:
        return {'error': str(e)}

@main_bp.route('/setup/products-table')
def setup_products_table():
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    product_name VARCHAR(100) NOT NULL,
                    quantity INT NOT NULL DEFAULT 0,
                    price DECIMAL(10, 2) NOT NULL,
                    category VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            sample_products = [
                ('Ballpoint Pen', 1, 25.00, 150, 'Generic', 'BALL-001', 'static/images/Pentonic.png'),
                ('Notebook A4', 2, 120.00, 50, 'Generic', 'NOTE-001', 'static/images/notebook.png'),
                ('Stapler', 3, 150.00, 30, 'Generic', 'STAP-001', 'static/images/stapler.png'),
                ('Sticky Notes', 2, 50.00, 200, 'Generic', 'STICK-001', 'static/images/sticky.png'),
                ('Highlighter Set', 1, 180.00, 45, 'Generic', 'HIGH-001', 'static/images/markers.png')
            ]
            
            cursor.executemany(
                """
                INSERT INTO products (name, category_id, price, stock_quantity, brand, sku, image_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    stock_quantity=VALUES(stock_quantity),
                    price=VALUES(price),
                    brand=VALUES(brand)
                """,
                sample_products
            )
            
            conn.commit()
            return "Products table created and sample data added successfully!"
    except Exception as e:
        conn.rollback()
        return f"Error setting up products table: {str(e)}"

@main_bp.route('/stock/request', methods=['POST'])
def stock_request():
    if session.get('role') != 'Staff':
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
    
    try:
        staff_id = session.get('user_id')
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        supplier_ids = request.form.getlist('supplier_id[]')

        if not staff_id:
            return jsonify({'success': False, 'message': 'User not logged in'}), 401

        if not product_ids or not quantities:
            return jsonify({'success': False, 'message': 'No products provided'}), 400

        success_count = 0
        with get_cursor() as cursor:
            for index, product_id in enumerate(product_ids):
                quantity = quantities[index] if index < len(quantities) else None
                supplier_id = supplier_ids[index] if index < len(supplier_ids) else ''

                if not product_id or not quantity:
                    continue

                try:
                    quantity = int(quantity)
                except ValueError:
                    continue

                if quantity <= 0:
                    continue

                # Convert empty string to NULL for supplier_id
                if not supplier_id or supplier_id == '':
                    supplier_id = None  # Always set to NULL when blank

                cursor.execute(
                    """
                    INSERT INTO new_arrival_alerts 
                    (staff_id, product_id, quantity_received, supplier_id, staff_notes, status)
                    VALUES (%s, %s, %s, %s, %s, 'Pending')
                    """,
                    (staff_id, product_id, quantity, supplier_id, '')
                )
                success_count += 1

        if success_count == 0:
            return jsonify({'success': False, 'message': 'No valid products to process'}), 400

        conn.commit()
        return jsonify({'success': True, 'message': f'{success_count} stock arrival(s) submitted successfully'})

    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid quantity value'}), 400
    except Exception as e:
        conn.rollback()
        print(f"Error submitting stock request: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to submit request'}), 500

@main_bp.route('/stock')
def stock():
    print("Stock route accessed")  # Debug log
    try:
        with get_cursor() as cursor:
            # First, check if tables exist
            cursor.execute("SHOW TABLES LIKE 'products'")
            if not cursor.fetchone():
                return "Products table does not exist. Please run the setup."
                
            cursor.execute("SHOW TABLES LIKE 'categories'")
            if not cursor.fetchone():
                return "Categories table does not exist. Please run the setup."
            
            query = """
                SELECT 
                    p.product_id,
                    p.name,
                    p.stock_quantity,
                    p.price,
                    c.name as category_name,
                    s.name as supplier_name
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.category_id
                LEFT JOIN suppliers s ON p.supplier_id = s.supplier_id
                ORDER BY c.name, p.name
            """
            
            print("Executing query:", query)  # Debug log
            cursor.execute(query)
            products = cursor.fetchall()
            print(f"Found {len(products)} products")  # Debug log
            
            products_list = []
            for product in products:
                products_list.append({
                    'product_id': product[0],
                    'name': product[1],
                    'quantity': product[2],
                    'price': float(product[3]) if product[3] else 0.0,
                    'category': product[4] or 'Uncategorized',
                    'supplier': product[5] or 'No Supplier'
                })
            
            # Fetch suppliers for the dropdown
            cursor.execute("SELECT supplier_id, name FROM suppliers ORDER BY name")
            suppliers = cursor.fetchall()
            suppliers_list = [{'supplier_id': s[0], 'name': s[1]} for s in suppliers]
            
            return render_template('stock.html', products=products_list, suppliers=suppliers_list)
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in stock route: {str(e)}\n{error_details}")
        flash(f'Error loading stock: {str(e)}', 'danger')
        return render_template('stock.html', products=[], suppliers=[])

@main_bp.route('/products/add', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            category_id = request.form.get('category_id')
            price = float(request.form.get('price', 0))
            stock_quantity = int(request.form.get('quantity', 0))
            brand = request.form.get('brand', '')
            sku = request.form.get('sku', '')
            image_url = request.form.get('image_url', '')
            
            with get_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO products (name, category_id, price, stock_quantity, brand, sku, image_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (name, category_id, price, stock_quantity, brand, sku, image_url)
                )
                conn.commit()
                flash('Product added successfully!', 'success')
                return redirect(url_for('main.manage_products'))
        except Exception as e:
            conn.rollback()
            flash(f'Error adding product: {str(e)}', 'danger')
    
    # For GET request or if there was an error
    with get_cursor() as cursor:
        cursor.execute("SELECT id, name FROM categories ORDER BY name")
        categories = cursor.fetchall()
    
    return render_template('add_product.html', categories=categories)

# ===== Sales & Orders =====
@main_bp.route('/sales')
def sales():
    return render_template('sales.html')

@main_bp.route('/orders')
def orders():
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT o.order_id, 
                   CONCAT(u.first_name, ' ', u.last_name) as customer_name,
                   o.created_at, o.order_status, 
                   o.payment_type, o.payment_status, o.total_amount,
                   o.transaction_code, o.order_type,
                   oi.product_name, oi.quantity, oi.price_per_item
            FROM orders o
            LEFT JOIN users u ON o.user_id = u.user_id
            LEFT JOIN (
                SELECT oi.order_id, p.name as product_name, oi.quantity, oi.price_at_order as price_per_item
                FROM order_items oi
                LEFT JOIN products p ON oi.product_id = p.product_id
            ) oi ON o.order_id = oi.order_id
            ORDER BY o.created_at DESC
        """)
        orders_data = cursor.fetchall()
        cursor.close()
        
        # Group order items by order_id
        orders = {}
        for row in orders_data:
            order_id = row['order_id']
            if order_id not in orders:
                orders[order_id] = {
                    'order_id': row['order_id'],
                    'customer_name': row['customer_name'] or 'Walk-in Customer',
                    'created_at': row['created_at'],
                    'order_status': row['order_status'],
                    'payment_type': row['payment_type'],
                    'payment_status': row['payment_status'],
                    'total_amount': row['total_amount'],
                    'transaction_code': row['transaction_code'],
                    'order_type': row['order_type'],
                    'line_items': []
                }
            if row['product_name']:
                orders[order_id]['line_items'].append({
                    'product_name': row['product_name'],
                    'quantity': row['quantity'],
                    'unit': 'pcs',
                    'price': row['price_per_item']
                })
        
        return render_template('orders.html', orders=list(orders.values()))
    except Exception as e:
        print(f"Error fetching orders: {e}")
        return render_template('orders.html', orders=[])

@main_bp.route('/orders/update-status', methods=['POST'])
def update_order_status():
    try:
        order_id = request.form.get('order_id')
        new_status = request.form.get('new_status')
        
        if not order_id or not new_status:
            return redirect('/orders')
        
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders 
            SET order_status = %s 
            WHERE order_id = %s
        """, (new_status, order_id))
        conn.commit()
        cursor.close()
        
        return redirect('/orders')
    except Exception as e:
        print(f"Error updating order status: {e}")
        return redirect('/orders')

@main_bp.route('/orders/update-payment-status', methods=['POST'])
def update_payment_status():
    try:
        order_id = request.form.get('order_id')
        payment_type = request.form.get('payment_type')
        payment_status = request.form.get('payment_status')
        
        if not order_id or not payment_status:
            return redirect('/orders')
        
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders 
            SET payment_status = %s, payment_type = %s
            WHERE order_id = %s
        """, (payment_status, payment_type, order_id))
        conn.commit()
        cursor.close()
        
        return redirect('/orders')
    except Exception as e:
        print(f"Error updating payment status: {e}")
        return redirect('/orders')

@main_bp.route('/cart')
def cart():
    return render_template('cart.html')

@main_bp.route('/checkout')
def checkout():
    return render_template('checkout.html')

# ===== Customer Management =====
@main_bp.route('/customer-profile')
def customer_profile():
    user_id = session.get('user_id')
    if not user_id:
        flash('Please log in to view your profile.', 'error')
        return redirect(url_for('login.login'))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT user_id, first_name, last_name, email, phone, role
            FROM users
            WHERE user_id = %s
            """,
            (user_id,),
        )
        user = cursor.fetchone()
        cursor.close()
    except Exception as e:
        print(f"Error fetching user: {e}")
        flash('Error loading profile information.', 'error')
        return render_template('customer-profile.html', user=None, edit_mode=False)

    if not user:
        flash('User account not found.', 'error')
        return redirect(url_for('login.login'))

    # Check if we're in edit mode
    edit_mode = request.args.get('edit', '').lower() == 'true'
    return render_template('customer-profile.html', user=user, edit_mode=edit_mode)


@main_bp.route('/update-profile', methods=['POST'])
def update_profile():
    try:
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'status': 'error', 'message': 'Please log in to update your profile.'}), 401
            flash('Please log in to update your profile.', 'error')
            return redirect(url_for('login.login'))

        user_id = session['user_id']
        
        # Get form data
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        
        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Basic validation
        if not all([first_name, last_name, email, phone]):
            flash('All fields are required.', 'error')
            return redirect(url_for('main.customer_profile', edit='true'))
            
        # Name validation - no numbers allowed
        if any(char.isdigit() for char in first_name) or any(char.isdigit() for char in last_name):
            flash('Name fields cannot contain numbers.', 'error')
            return redirect(url_for('main.customer_profile', edit='true'))
            
        # Name length validation
        if len(first_name) < 2 or len(last_name) < 2:
            flash('Name fields must be at least 2 characters long.', 'error')
            return redirect(url_for('main.customer_profile', edit='true'))
        
        # Enhanced email validation with strict domain checking
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(\.[a-zA-Z]{2,})?$'
        if not re.match(email_pattern, email):
            flash('Please enter a valid email address (e.g., example@gmail.com).', 'error')
            return redirect(url_for('main.customer_profile', edit='true'))
        
        # Get domain part for additional validation
        domain = email.split('@')[-1].lower()
        
        # Special handling for Gmail addresses
        if 'gmail' in domain:
            if not domain == 'gmail.com':
                flash('Gmail addresses must use @gmail.com domain.', 'error')
                return redirect(url_for('main.customer_profile', edit='true'))
        # General domain validation for other email providers
        elif '.' not in domain or len(domain.split('.')[-1]) < 2:
            flash('Please enter a valid email domain (e.g., example.com).', 'error')
            return redirect(url_for('main.customer_profile', edit='true'))
        
        # Phone number validation
        if not re.match(r'^\d{10}$', phone):
            flash('Please enter a valid 10-digit phone number (digits only).', 'error')
            return redirect(url_for('main.customer_profile', edit='true'))
        
        cursor = None
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Check if email already exists for another user
            cursor.execute(
                """
                SELECT user_id, first_name, last_name FROM users 
                WHERE email = %s AND user_id != %s
                """,
                (email, user_id)
            )
            existing_user = cursor.fetchone()
            if existing_user:
                error_msg = 'The email you entered is already in use. Please try a different email.'
                if is_ajax:
                    return jsonify({
                        'status': 'error',
                        'message': error_msg,
                        'existing_user': f"{existing_user['first_name']} {existing_user['last_name']}"
                    }), 400
                flash(error_msg, 'error')
                return redirect(url_for('main.customer_profile', edit='true'))
            
            # Update user data
            cursor.execute(
                """
                UPDATE users 
                SET first_name = %s, 
                    last_name = %s, 
                    email = %s, 
                    phone = %s
                WHERE user_id = %s
                """,
                (first_name, last_name, email, phone, user_id)
            )
            
            if cursor.rowcount == 0:
                flash('No changes were made or user not found.', 'info')
            else:
                # Update session data
                session['name'] = f"{first_name} {last_name}"
                success_msg = 'Profile updated successfully!'
                if is_ajax:
                    return jsonify({'status': 'success', 'message': success_msg})
                flash(success_msg, 'success')
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            print(f"Database error: {str(e)}")
            flash(f'Database error: {str(e)}', 'error')
            return redirect(url_for('main.customer_profile', edit='true'))
            
        finally:
            if cursor:
                cursor.close()
        
        return redirect(url_for('main.customer_profile'))
        
    except Exception as e:
        print(f"Unexpected error in update_profile: {str(e)}")
        flash('An unexpected error occurred. Please try again later.', 'error')
        return redirect(url_for('main.customer_profile', edit='true'))

@main_bp.route('/customer-history')
def customer_history():
    return render_template('customer-history.html')

# ===== Supplier Management =====
@main_bp.route('/suppliers')
def suppliers():
    return render_template('suppliers.html')


# ===== Task Management =====
@main_bp.route('/task')
def task():
    return render_template('task.html')

@main_bp.route('/mytask')
def mytask():
    return render_template('mytask.html')

# ===== System & Admin =====
@main_bp.route('/users')
def users():
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT 
                    user_id as id,
                    first_name, 
                    last_name, 
                    email,
                    role,
                    CASE 
                        WHEN role != 'Customer' THEN 'Active'  
                        ELSE 'Active'  
                    END as status
                FROM users
                WHERE role != 'Admin'
                ORDER BY user_id ASC
            """)
            users = cursor.fetchall()
            # Convert to list of dictionaries for easier template handling
            users_list = [dict(zip([column[0] for column in cursor.description], row)) for row in users]
            return render_template('users.html', users=users_list)
    except Exception as e:
        flash(f'Error fetching users: {str(e)}', 'error')
        return render_template('users.html', users=[])

@main_bp.route('/users')
def reports():
    return render_template('users.html')

@main_bp.route('/notifications')
def notifications():
    return render_template('notifications.html')
    
@main_bp.route('/register')
def redirect_register():
    return redirect('/auth/register')

@main_bp.route('/maintenance')
def maintenance():
    return render_template('maintenance.html')

# ===== Payment & Status =====
@main_bp.route('/payment/success')
def payment_success():
    return render_template('payment-success.html')  # Changed from payment_success.html to payment-success.html

@main_bp.route('/pos/checkout', methods=['POST'])
def pos_checkout():
    if session.get('role') != 'Staff':
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
    
    try:
        data = request.get_json()
        order_items = data.get('items', [])
        total_amount = data.get('total', 0)
        payment_method = data.get('payment_method', 'Cash')
        
        if not order_items:
            return jsonify({'success': False, 'message': 'No items in order'}), 400
        
        staff_id = session.get('user_id')
        
        with get_cursor() as cursor:
            # Create sales record
            cursor.execute(
                """
                INSERT INTO sales (staff_id, total_amount, payment_method, status, created_at)
                VALUES (%s, %s, %s, 'Completed', NOW())
                """,
                (staff_id, total_amount, payment_method)
            )
            sale_id = cursor.lastrowid
            
            # Create sale items (no stock validation or deduction)
            for item in order_items:
                product_id = item['id']
                quantity = item['quantity']
                price = item['price']
                
                # Add sale item
                cursor.execute(
                    """
                    INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, subtotal)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (sale_id, product_id, quantity, price, price * quantity)
                )
            
            conn.commit()
            
        return jsonify({
            'success': True, 
            'message': 'Sale completed successfully',
            'sale_id': sale_id
        })
        
    except Exception as e:
        conn.rollback()
        print(f"Error processing checkout: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to process sale'}), 500

@main_bp.route('/api/products/<int:product_id>/alert', methods=['POST'])
def send_product_alert(product_id):
    if session.get('role') != 'Staff':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        quantity = data.get('quantity', 0)
        
        if not message:
            return jsonify({'success': False, 'error': 'Message is required'})
        
        if quantity < 1:
            return jsonify({'success': False, 'error': 'Quantity must be at least 1'})
        
        staff_id = session.get('user_id')
        
        with get_cursor() as cursor:
            # Verify product exists
            cursor.execute("SELECT name FROM products WHERE product_id = %s", (product_id,))
            product = cursor.fetchone()
            
            if not product:
                return jsonify({'success': False, 'error': 'Product not found'})
            
            # Insert alert into database using stock_requests table
            cursor.execute(
                """
                INSERT INTO stock_requests (staff_id, product_id, supplier_id, requested_quantity, reason, status)
                VALUES (%s, %s, NULL, %s, %s, 'Pending')
                """,
                (staff_id, product_id, quantity, message)
            )
            
            conn.commit()
            
        return jsonify({
            'success': True, 
            'message': f'Alert sent for {product[0]} - {quantity} units requested'
        })
        
    except Exception as e:
        conn.rollback()
        print(f"Error sending alert: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to send alert'}), 500

@main_bp.route('/payment/failed')
def payment_failed():
    return render_template('payment-failed.html')  # Changed from payment_failed.html to payment-failed.html

@main_bp.route('/admin/reset-password', methods=['POST'])
def admin_reset_password():
    try:
        # Check if user is logged in and is admin
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Please log in to continue'}), 401
        
        # Get form data from admin password reset modal
        user_id = request.form.get('user_id', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_new_password = request.form.get('confirm_new_password', '').strip()
        
        # Validation
        if not all([user_id, new_password, confirm_new_password]):
            return jsonify({'success': False, 'error': 'All fields are required'}), 400
        
        # Password requirements validation (same as register.py)
        def validate_password_strength(password):
            if len(password) < 8:
                return False, "Password must be at least 8 characters long"
            if not re.search(r'[a-z]', password):
                return False, "Password must contain at least one lowercase letter"
            if not re.search(r'[A-Z]', password):
                return False, "Password must contain at least one uppercase letter"
            if not re.search(r'[0-9]', password):
                return False, "Password must contain at least one number"
            if not re.search(r'[^A-Za-z0-9]', password):
                return False, "Password must contain at least one special character"
            return True, "Password meets all requirements"
        
        is_valid, error_message = validate_password_strength(new_password)
        if not is_valid:
            return jsonify({'success': False, 'error': error_message}), 400
        
        if new_password != confirm_new_password:
            return jsonify({'success': False, 'error': 'New passwords do not match'}), 400
        
        # Hash the new password before saving (same method as registration)
        hashed_new_password = generate_password_hash(
            new_password,
            method='pbkdf2:sha256',
            salt_length=16
        )
        
        # Update hashed_password field
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET hashed_password = %s WHERE user_id = %s", (hashed_new_password, user_id))
        conn.commit()
        cursor.close()
        
        return jsonify({'success': True, 'message': 'Password reset successfully!'})
        
    except Exception as e:
        print(f"Error in admin password reset: {e}")
        return jsonify({'success': False, 'error': 'Password reset failed. Please try again.'}), 500

@main_bp.route('/change-password', methods=['POST'])
def change_password():
    try:
        if 'user_id' not in session:
            flash('Please log in to change your password.', 'error')
            return redirect(url_for('login.login'))

        user_id = session['user_id']
        
        # Get form data
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        # Validation
        if not all([current_password, new_password, confirm_password]):
            flash('All password fields are required.', 'error')
            return redirect(url_for('main.customer_profile'))
        
        # Password requirements validation
        def validate_password_strength(password):
            if len(password) < 8:
                return False, "Password must be at least 8 characters long"
            if not re.search(r'[a-z]', password):
                return False, "Password must contain at least one lowercase letter"
            if not re.search(r'[A-Z]', password):
                return False, "Password must contain at least one uppercase letter"
            if not re.search(r'[0-9]', password):
                return False, "Password must contain at least one number"
            if not re.search(r'[^A-Za-z0-9]', password):
                return False, "Password must contain at least one special character"
            return True, "Password meets all requirements"
        
        is_valid, error_message = validate_password_strength(new_password)
        if not is_valid:
            flash(error_message, 'error')
            return redirect(url_for('main.customer_profile'))
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return redirect(url_for('main.customer_profile'))
        
        # Get current user data to verify current password
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT hashed_password FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        
        if not user:
            flash('User account not found.', 'error')
            return redirect(url_for('main.customer_profile'))
        
        # Verify current password using same method as login
        if not check_password_hash(user['hashed_password'], current_password):
            flash('Please check your current password and try again', 'error')
            return redirect(url_for('main.customer_profile'))
        
        # Hash the new password before saving (same method as registration)
        hashed_new_password = generate_password_hash(
            new_password,
            method='pbkdf2:sha256',
            salt_length=16
        )
        
        # Update hashed_password field (same field as login uses)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET hashed_password = %s WHERE user_id = %s", (hashed_new_password, user_id))
        conn.commit()
        cursor.close()
        
        flash('Password changed successfully!', 'success')
        return redirect(url_for('main.customer_profile'))
        
    except Exception as e:
        print(f"Error changing password: {e}")
        # Don't show generic error - let the specific validation errors handle the feedback
        return redirect(url_for('main.customer_profile'))

# ===== Error Handlers =====
@main_bp.app_errorhandler(404)
def page_not_found(e):
    return render_template('base.html', error_message='Page not found'), 404
