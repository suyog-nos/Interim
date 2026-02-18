from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
import re
from forms import RegistrationForm
from config import conn
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
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
                WHERE p.status = 'active'
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

@main_bp.route('/demand-forecasting')
def demand_forecasting():
    return render_template('demand-forecasting.html')

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
                    p.category_id,
                    p.supplier_id,
                    p.brand,
                    p.sku,
                    p.image_url,
                    p.status,
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
                    'category_id': product[4],
                    'supplier_id': product[5],
                    'brand': product[6] or '',
                    'sku': product[7] or '',
                    'image_url': product[8] or '',
                    'status': product[9] or 'active',
                    'category': product[10] or 'Uncategorized',
                    'supplier': product[11] or 'No Supplier'
                })
            
            # Fetch suppliers for the dropdown
            cursor.execute("SELECT supplier_id, name FROM suppliers ORDER BY name")
            suppliers = cursor.fetchall()
            suppliers_list = [{'supplier_id': s[0], 'name': s[1]} for s in suppliers]
            
            # Fetch categories for the dropdown
            cursor.execute("SELECT category_id, name FROM categories ORDER BY name")
            categories = cursor.fetchall()
            categories_list = [{'category_id': c[0], 'name': c[1]} for c in categories]
            
            return render_template('stock.html', products=products_list, suppliers=suppliers_list, categories=categories_list)
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in stock route: {str(e)}\n{error_details}")
        flash(f'Error loading stock: {str(e)}', 'danger')
        return render_template('stock.html', products=[], suppliers=[], categories=[])

@main_bp.route('/products/add', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            category_id = request.form.get('category_id')
            supplier_id = request.form.get('supplier_id') or 1
            price = float(request.form.get('price', 0))
            stock_quantity = int(request.form.get('stock_quantity', 0))
            unit_type = request.form.get('unit_type', 'piece')
            brand = request.form.get('brand', '')
            sku = request.form.get('sku', '')
            
            # Handle file upload
            image_url = ''
            if 'product_image' in request.files:
                file = request.files['product_image']
                if file and file.filename != '':
                    # Check if the file is an allowed image type
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    filename = file.filename.lower()
                    if '.' in filename and filename.rsplit('.', 1)[1] in allowed_extensions:
                        # Create secure filename
                        secure_name = secure_filename(file.filename)
                        
                        # Add timestamp to avoid filename conflicts
                        import time
                        timestamp = str(int(time.time()))
                        name_part, ext_part = secure_name.rsplit('.', 1)
                        final_filename = f"{name_part}_{timestamp}.{ext_part}"
                        
                        # Save the file
                        upload_path = os.path.join('static', 'images', final_filename)
                        os.makedirs(os.path.dirname(upload_path), exist_ok=True)
                        file.save(upload_path)
                        
                        # Store the relative path in the database
                        image_url = f"static/images/{final_filename}"
                    else:
                        flash('Invalid file type. Please upload an image file (PNG, JPG, JPEG, GIF, or WebP).', 'danger')
                        return redirect(request.referrer or url_for('main.stock'))
            
            with get_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO products (name, category_id, supplier_id, price, stock_quantity, unit_type, units_per_pack, brand, sku, image_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (name, category_id, supplier_id, price, stock_quantity, unit_type, 1, brand, sku, image_url)
                )
                conn.commit()
                flash('Product added successfully!', 'success')
                return redirect(url_for('main.stock'))
        except Exception as e:
            conn.rollback()
            flash(f'Error adding product: {str(e)}', 'danger')
            return redirect(request.referrer or url_for('main.stock'))
    
    # For GET request or if there was an error
    with get_cursor() as cursor:
        cursor.execute("SELECT category_id, name FROM categories ORDER BY name")
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
        user_role = session.get('role')
        
        if not order_id or not new_status:
            return redirect('/orders')
        
        # Check role permissions for status updates
        if user_role == 'Staff':
            # Staff can only update to processing and ready_for_pickup
            if new_status not in ['processing', 'ready_for_pickup']:
                return redirect('/orders')
        elif user_role != 'Admin':
            # Only Admin and Staff can update order status
            return redirect('/orders')
        
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Get current order status and items before updating
            cursor.execute("""
                SELECT order_status FROM orders WHERE order_id = %s
            """, (order_id,))
            current_order = cursor.fetchone()
            
            if not current_order:
                return redirect('/orders')
            
            current_status = current_order['order_status']
            
            # If cancelling the order, restore stock
            if new_status == 'cancelled' and current_status != 'cancelled':
                # Get order items to restore stock
                cursor.execute("""
                    SELECT oi.product_id, oi.quantity 
                    FROM order_items oi 
                    WHERE oi.order_id = %s
                """, (order_id,))
                order_items = cursor.fetchall()
                
                # Restore stock quantities
                for item in order_items:
                    cursor.execute("""
                        UPDATE products 
                        SET stock_quantity = stock_quantity + %s 
                        WHERE product_id = %s
                    """, (item['quantity'], item['product_id']))
            
            # Update order status
            cursor.execute("""
                UPDATE orders 
                SET order_status = %s
                WHERE order_id = %s
            """, (new_status, order_id))
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            print(f"Error updating order status: {e}")
        finally:
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
@main_bp.route('/tasks')
def task():
    # Check if user is logged in and is an admin
    if 'user_id' not in session or session.get('role') != 'Admin':
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    cursor = conn.cursor(dictionary=True)
    try:
        # Get task statistics for the dashboard
        cursor.execute("""
            SELECT 
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'in-progress' THEN 1 ELSE 0 END) AS in_progress,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed
            FROM tasks
        """)
        stats = cursor.fetchone() or {}
        
        # Get all tasks with assignee details
        cursor.execute("""
            SELECT 
                t.task_id,
                t.title,
                t.description,
                t.due_date,
                t.priority,
                t.status,
                t.category,
                t.created_at,
                CONCAT(u.first_name, ' ', u.last_name) AS assigned_to_name
            FROM tasks t
            JOIN users u ON t.assigned_to = u.user_id
            ORDER BY 
                FIELD(t.status, 'pending', 'in-progress', 'completed'),
                t.due_date ASC,
                FIELD(t.priority, 'high', 'medium', 'low')
        """)
        tasks = cursor.fetchall()
        
        # Fetch stock alerts raised by staff (stock_requests acts as alerts)
        # Fetch new arrival alerts submitted by staff
        cursor.execute("""
            SELECT 
                naa.arrival_id,
                naa.product_id,
                p.name AS product_name,
                p.stock_status AS alert_type,
                p.stock_quantity,
                naa.quantity_received,
                naa.staff_notes,
                naa.status,
                naa.created_at,
                CONCAT(u.first_name, ' ', u.last_name) AS staff_name,
                COALESCE(s.name, 'Unknown Supplier') AS supplier_name,
                CASE 
                    WHEN p.stock_quantity <= 0 THEN 'high'
                    WHEN p.stock_quantity <= 5 THEN 'high'
                    WHEN p.stock_quantity <= 15 THEN 'medium'
                    ELSE 'low'
                END AS priority_label
            FROM new_arrival_alerts naa
            JOIN products p ON naa.product_id = p.product_id
            JOIN users u ON naa.staff_id = u.user_id
            LEFT JOIN suppliers s ON naa.supplier_id = s.supplier_id
            ORDER BY naa.created_at DESC
            LIMIT 30
        """)
        arrival_alerts = cursor.fetchall()
        
        # Fetch stock alerts raised by staff
        cursor.execute("""
            SELECT 
                sr.request_id,
                sr.product_id,
                p.name AS product_name,
                p.stock_status AS alert_type,
                p.stock_quantity,
                sr.requested_quantity,
                sr.reason,
                sr.status,
                sr.created_at,
                CONCAT(u.first_name, ' ', u.last_name) AS staff_name,
                CASE 
                    WHEN p.stock_quantity <= 0 THEN 'high'
                    WHEN p.stock_quantity <= 5 THEN 'high'
                    WHEN p.stock_quantity <= 15 THEN 'medium'
                    ELSE 'low'
                END AS priority_label
            FROM stock_requests sr
            JOIN products p ON sr.product_id = p.product_id
            JOIN users u ON sr.staff_id = u.user_id
            ORDER BY sr.created_at DESC
            LIMIT 30
        """)
        stock_alerts = cursor.fetchall()
        
        # Fetch staff members for task assignment dropdown
        cursor.execute("""
            SELECT 
                user_id,
                CONCAT(first_name, ' ', last_name) AS full_name,
                email
            FROM users 
            WHERE role = 'Staff' 
            ORDER BY first_name, last_name
        """)
        staff_members = cursor.fetchall()
        
        combined_alerts = (arrival_alerts or []) + (stock_alerts or [])
        alert_count = len(combined_alerts)
        pending_alerts = sum(1 for alert in combined_alerts if str(alert.get('status', '')).lower() == 'pending')
        
        return render_template(
            'task.html',
            stats=stats,
            tasks=tasks,
            arrival_alerts=arrival_alerts,
            stock_alerts=stock_alerts,
            staff_members=staff_members,
            alert_count=alert_count,
            pending_alerts=pending_alerts,
            current_page='tasks'
        )
    except Exception as e:
        print(f"Error fetching task data: {str(e)}")
        flash('Error loading task management page', 'danger')
        return redirect(url_for('main.dashboard'))
    finally:
        cursor.close()

@main_bp.route('/mytasks')
def mytask():
    # Check if user is logged in
    if 'user_id' not in session:
        flash('Please login to view your tasks', 'warning')
        return redirect(url_for('main.login'))
    
    user_id = session['user_id']
    
    try:
        # Import the functions from products.py
        from products import get_staff_tasks, get_staff_task_stats
        
        # Get user's tasks and stats using the new functions
        tasks = get_staff_tasks(user_id)
        stats = get_staff_task_stats(user_id)
        
        return render_template(
            'mytask.html',
            tasks=tasks,
            stats=stats,
            current_page='mytasks'
        )
        
    except Exception as e:
        print(f"Error fetching user tasks: {str(e)}")
        flash('Error loading your tasks', 'danger')
        return redirect(url_for('main.dashboard'))

@main_bp.route('/tasks/update', methods=['POST'])
def update_task():
    # Check if user is logged in and is an admin
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if 'user_id' not in session or session.get('role') != 'Admin':
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        flash('You do not have permission to update tasks', 'danger')
        return redirect(url_for('main.task'))
    
    try:
        # Get form data
        task_id = request.form.get('task_id')
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', 'General').strip() or 'General'
        priority = (request.form.get('priority') or 'medium').lower()
        status = (request.form.get('status') or 'pending').lower()
        due_date = request.form.get('due_date')
        assigned_to = request.form.get('assigned_to')
        
        # Validation
        def respond_error(message, status_code=400):
            if is_ajax:
                return jsonify({'success': False, 'message': message}), status_code
            flash(message, 'danger')
            return redirect(url_for('main.task'))
        
        if not task_id:
            return respond_error('Task ID is required')
        
        if not title:
            return respond_error('Task title is required')
        
        if not due_date:
            return respond_error('Due date is required')
        
        if not assigned_to:
            return respond_error('Task assignment is required')
        
        # Validate priority
        if priority not in ['low', 'medium', 'high']:
            priority = 'medium'
        
        # Validate status
        if status not in ['pending', 'in-progress', 'completed']:
            status = 'pending'
        
        # Validate date
        from datetime import datetime
        try:
            parsed_date = datetime.strptime(due_date, '%Y-%m-%d').date()
        except ValueError:
            return respond_error('Invalid due date format')
        
        try:
            task_id_int = int(task_id)
            assigned_to_id = int(assigned_to)
        except (TypeError, ValueError):
            return respond_error('Invalid task ID or staff selection')
        
        # Update task in database
        with get_cursor() as cursor:
            # First check if task exists and get current values
            cursor.execute(
                """
                SELECT title, description, category, priority, status, due_date, assigned_to
                FROM tasks 
                WHERE task_id = %s
                """,
                (task_id_int,)
            )
            
            current_task = cursor.fetchone()
            if not current_task:
                return respond_error('Task not found')
            
            # Check if values are actually different
            current_title, current_description, current_category, current_priority, current_status, current_due_date, current_assigned_to = current_task
            
            # Convert current_due_date to string for comparison
            if current_due_date:
                current_due_date_str = current_due_date.strftime('%Y-%m-%d')
            else:
                current_due_date_str = None
            
            # If no actual changes, return success but don't update
            if (current_title == title and 
                current_description == description and 
                current_category == category and 
                current_priority == priority and 
                current_status == status and 
                current_due_date_str == due_date and 
                str(current_assigned_to) == assigned_to):
                
                # Return success with message that no changes were needed
                if is_ajax:
                    return jsonify({
                        'success': True, 
                        'message': 'No changes made',
                        'task': None
                    })
                flash('No changes made', 'info')
                return redirect(url_for('main.task'))
            
            # Perform the actual update
            cursor.execute(
                """
                UPDATE tasks 
                SET title = %s, description = %s, category = %s, priority = %s, 
                    status = %s, due_date = %s, assigned_to = %s
                WHERE task_id = %s
                """,
                (title, description, category, priority, status, parsed_date, assigned_to_id, task_id_int)
            )
            
            if cursor.rowcount == 0:
                return respond_error('Failed to update task - please try again')
            
            # Get assignee name for response
            cursor.execute(
                """
                SELECT CONCAT(first_name, ' ', last_name) 
                FROM users 
                WHERE user_id = %s
                """,
                (assigned_to_id,)
            )
            assigned_to_name = cursor.fetchone()
            assigned_to_name = assigned_to_name[0] if assigned_to_name and assigned_to_name[0] else 'Unassigned'
            
            conn.commit()
            
            success_msg = f'Task "{title}" updated successfully'
            if is_ajax:
                return jsonify({
                    'success': True, 
                    'message': success_msg,
                    'task': {
                        'task_id': task_id_int,
                        'title': title,
                        'description': description,
                        'category': category,
                        'priority': priority,
                        'status': status,
                        'due_date': parsed_date.isoformat(),
                        'assigned_to_name': assigned_to_name
                    }
                })
            flash(success_msg, 'success')
            return redirect(url_for('main.task'))
            
    except ValueError as e:
        error_msg = f'Invalid data: {str(e)}'
        if is_ajax:
            return jsonify({'success': False, 'message': error_msg}), 400
        flash(error_msg, 'danger')
        return redirect(url_for('main.task'))
        
    except Exception as e:
        conn.rollback()
        error_msg = f'Error updating task: {str(e)}'
        print(f"Error in update_task: {str(e)}")
        if is_ajax:
            return jsonify({'success': False, 'message': error_msg}), 500
        flash(error_msg, 'danger')
        return redirect(url_for('main.task'))

@main_bp.route('/tasks/updates', methods=['GET'])
def get_task_updates():
    """Check for task updates - used for auto-refresh"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401
    
    try:
        cursor = get_cursor()
        
        # Get current task count for the user
        if session.get('role') == 'Admin':
            cursor.execute("SELECT COUNT(*) FROM tasks")
        else:
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE assigned_to = %s", 
                          (session['user_id'],))
        
        task_count = cursor.fetchone()[0]
        cursor.close()
        
        return jsonify({
            'success': True,
            'task_count': task_count
        })
        
    except Exception as e:
        print(f"Error checking task updates: {e}")
        return jsonify({'success': False, 'message': 'Error checking updates'}), 500


@main_bp.route('/tasks/delete/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    """Delete a task"""
    # Check if user is logged in and is an admin
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if 'user_id' not in session or session.get('role') != 'Admin':
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        flash('You do not have permission to delete tasks', 'danger')
        return redirect(url_for('main.task'))
    
    try:
        with get_cursor() as cursor:
            # Check if task exists
            cursor.execute("SELECT title FROM tasks WHERE task_id = %s", (task_id,))
            task = cursor.fetchone()
            
            if not task:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Task not found'}), 404
                flash('Task not found', 'danger')
                return redirect(url_for('main.task'))
            
            # Delete the task
            cursor.execute("DELETE FROM tasks WHERE task_id = %s", (task_id,))
            
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': f'Task "{task[0]}" deleted successfully'
                })
            
            flash(f'Task "{task[0]}" deleted successfully', 'success')
            return redirect(url_for('main.task'))
            
    except Exception as e:
        conn.rollback()
        error_msg = f'Error deleting task: {str(e)}'
        print(f"Error in delete_task: {str(e)}")
        if is_ajax:
            return jsonify({'success': False, 'message': error_msg}), 500
        flash(error_msg, 'danger')
        return redirect(url_for('main.task'))


@main_bp.route('/stock-requests/<int:request_id>/status', methods=['POST'])
def update_stock_request_status(request_id):
    """Update stock request status (Approve/Reject)"""
    # Check if user is logged in and is an admin
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if 'user_id' not in session or session.get('role') != 'Admin':
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        flash('You do not have permission to update stock requests', 'danger')
        return redirect(url_for('main.task'))
    
    try:
        # Get JSON data
        if not request.is_json:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Invalid request format'}), 400
            flash('Invalid request format', 'danger')
            return redirect(url_for('main.task'))
        
        data = request.get_json()
        new_status = data.get('status')
        
        # Validate status
        if new_status not in ['Approved', 'Rejected']:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Invalid status'}), 400
            flash('Invalid status', 'danger')
            return redirect(url_for('main.task'))
        
        with get_cursor() as cursor:
            # Check if stock request exists and get product name
            cursor.execute("""
                SELECT sr.request_id, sr.product_id, p.name, sr.status
                FROM stock_requests sr
                JOIN products p ON sr.product_id = p.product_id
                WHERE sr.request_id = %s
            """, (request_id,))
            
            stock_request = cursor.fetchone()
            if not stock_request:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Stock request not found'}), 404
                flash('Stock request not found', 'danger')
                return redirect(url_for('main.task'))
            
            # Check if already processed
            if stock_request[3] != 'Pending':
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Stock request already processed'}), 400
                flash('Stock request already processed', 'warning')
                return redirect(url_for('main.task'))
            
            # Update the status
            cursor.execute("""
                UPDATE stock_requests 
                SET status = %s
                WHERE request_id = %s
            """, (new_status, request_id))
            
            if cursor.rowcount == 0:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Failed to update stock request'}), 500
                flash('Failed to update stock request', 'danger')
                return redirect(url_for('main.task'))
            
            product_name = stock_request[2]
            
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': f'Stock request for "{product_name}" {new_status.lower()} successfully'
                })
            
            flash(f'Stock request for "{product_name}" {new_status.lower()} successfully', 'success')
            return redirect(url_for('main.task'))
            
    except Exception as e:
        error_msg = f'Error updating stock request: {str(e)}'
        print(f"Error in update_stock_request_status: {str(e)}")
        if is_ajax:
            return jsonify({'success': False, 'message': error_msg}), 500
        flash(error_msg, 'danger')
        return redirect(url_for('main.task'))


@main_bp.route('/arrivals/<int:arrival_id>/status', methods=['POST'])
def update_arrival_status(arrival_id):
    """Update arrival status (Approve/Reject)"""
    # Check if user is logged in and is an admin
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if 'user_id' not in session or session.get('role') != 'Admin':
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        flash('You do not have permission to update arrivals', 'danger')
        return redirect(url_for('main.task'))
    
    try:
        # Get JSON data
        if not request.is_json:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Invalid request format'}), 400
            flash('Invalid request format', 'danger')
            return redirect(url_for('main.task'))
        
        data = request.get_json()
        new_status = data.get('status')
        
        # Validate status
        if new_status not in ['Approved', 'Rejected']:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Invalid status'}), 400
            flash('Invalid status', 'danger')
            return redirect(url_for('main.task'))
        
        with get_cursor() as cursor:
            # Check if arrival exists and get product name
            cursor.execute("""
                SELECT naa.arrival_id, naa.product_id, p.name, naa.status
                FROM new_arrival_alerts naa
                JOIN products p ON naa.product_id = p.product_id
                WHERE naa.arrival_id = %s
            """, (arrival_id,))
            
            arrival = cursor.fetchone()
            if not arrival:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Arrival not found'}), 404
                flash('Arrival not found', 'danger')
                return redirect(url_for('main.task'))
            
            # Check if already processed
            if arrival[3] != 'Pending':
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Arrival already processed'}), 400
                flash('Arrival already processed', 'warning')
                return redirect(url_for('main.task'))
            
            # Update the status
            cursor.execute("""
                UPDATE new_arrival_alerts 
                SET status = %s
                WHERE arrival_id = %s
            """, (new_status, arrival_id))
            
            if cursor.rowcount == 0:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Failed to update arrival'}), 500
                flash('Failed to update arrival', 'danger')
                return redirect(url_for('main.task'))
            
            product_name = arrival[2]
            
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': f'Arrival for "{product_name}" {new_status.lower()} successfully'
                })
            
            flash(f'Arrival for "{product_name}" {new_status.lower()} successfully', 'success')
            return redirect(url_for('main.task'))
            
    except Exception as e:
        error_msg = f'Error updating arrival: {str(e)}'
        print(f"Error in update_arrival_status: {str(e)}")
        if is_ajax:
            return jsonify({'success': False, 'message': error_msg}), 500
        flash(error_msg, 'danger')
        return redirect(url_for('main.task'))


@main_bp.route('/arrivals/<int:arrival_id>/delete', methods=['POST'])
def delete_arrival(arrival_id):
    """Delete arrival alert"""
    # Check if user is logged in and is an admin
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if 'user_id' not in session or session.get('role') != 'Admin':
        if is_ajax:
            return jsonify({'success': False, 'message': 'Permission denied'}), 403
        flash('You do not have permission to delete arrivals', 'danger')
        return redirect(url_for('main.task'))
    
    try:
        with get_cursor() as cursor:
            # Check if arrival exists and get product name
            cursor.execute("""
                SELECT arrival_id, product_id, status
                FROM new_arrival_alerts 
                WHERE arrival_id = %s
            """, (arrival_id,))
            
            arrival = cursor.fetchone()
            if not arrival:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Arrival not found'}), 404
                flash('Arrival not found', 'danger')
                return redirect(url_for('main.task'))
            
            # Delete the arrival
            cursor.execute("""
                DELETE FROM new_arrival_alerts 
                WHERE arrival_id = %s
            """, (arrival_id,))
            
            if cursor.rowcount == 0:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Failed to delete arrival'}), 500
                flash('Failed to delete arrival', 'danger')
                return redirect(url_for('main.task'))
            
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': 'Arrival alert deleted successfully'
                })
            
            flash('Arrival alert deleted successfully', 'success')
            return redirect(url_for('main.task'))
            
    except Exception as e:
        error_msg = f'Error deleting arrival: {str(e)}'
        print(f"Error in delete_arrival: {str(e)}")
        if is_ajax:
            return jsonify({'success': False, 'message': error_msg}), 500
        flash(error_msg, 'danger')
        return redirect(url_for('main.task'))


@main_bp.route('/stock-requests/<int:request_id>/delete', methods=['POST'])
def delete_stock_request(request_id):
    """Delete stock request alert"""
    # Check if user is logged in and is an admin
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if 'user_id' not in session or session.get('role') != 'Admin':
        if is_ajax:
            return jsonify({'success': False, 'message': 'Permission denied'}), 403
        flash('You do not have permission to delete stock requests', 'danger')
        return redirect(url_for('main.task'))
    
    try:
        with get_cursor() as cursor:
            # Check if stock request exists and get product name
            cursor.execute("""
                SELECT request_id, product_id, status
                FROM stock_requests 
                WHERE request_id = %s
            """, (request_id,))
            
            stock_request = cursor.fetchone()
            if not stock_request:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Stock request not found'}), 404
                flash('Stock request not found', 'danger')
                return redirect(url_for('main.task'))
            
            # Delete the stock request
            cursor.execute("""
                DELETE FROM stock_requests 
                WHERE request_id = %s
            """, (request_id,))
            
            if cursor.rowcount == 0:
                if is_ajax:
                    return jsonify({'success': False, 'message': 'Failed to delete stock request'}), 500
                flash('Failed to delete stock request', 'danger')
                return redirect(url_for('main.task'))
            
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': 'Stock request deleted successfully'
                })
            
            flash('Stock request deleted successfully', 'success')
            return redirect(url_for('main.task'))
            
    except Exception as e:
        error_msg = f'Error deleting stock request: {str(e)}'
        print(f"Error in delete_stock_request: {str(e)}")
        if is_ajax:
            return jsonify({'success': False, 'message': error_msg}), 500
        flash(error_msg, 'danger')
        return redirect(url_for('main.task'))


@main_bp.route('/tasks/add', methods=['POST'])
def add_task():
    # Check if user is logged in and is an admin
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if 'user_id' not in session or session.get('role') != 'Admin':
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        flash('You do not have permission to add tasks', 'danger')
        return redirect(url_for('main.index'))
    
    try:
        # Get form data
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', 'General').strip() or 'General'
        priority = (request.form.get('priority') or 'medium').lower()
        due_date = request.form.get('due_date')
        assigned_to = request.form.get('assigned_to')
        
        # Validation
        def respond_error(message, status_code=400):
            if is_ajax:
                return jsonify({'success': False, 'message': message}), status_code
            flash(message, 'danger')
            return redirect(url_for('main.task'))
        
        if not title:
            return respond_error('Task title is required')
        
        if not due_date:
            return respond_error('Due date is required')
        
        if not assigned_to:
            return respond_error('Task assignment is required')
        
        # Validate priority
        if priority not in ['low', 'medium', 'high']:
            priority = 'medium'
        
        # Validate date
        from datetime import datetime
        try:
            parsed_date = datetime.strptime(due_date, '%Y-%m-%d').date()
        except ValueError:
            return respond_error('Invalid due date format')
        
        try:
            assigned_to_id = int(assigned_to)
        except (TypeError, ValueError):
            return respond_error('Invalid staff selection')
        
        # Insert task into database
        with get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tasks (title, description, category, priority, due_date, assigned_to, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                """,
                (title, description, category, priority, parsed_date, assigned_to_id)
            )
            
            task_id = cursor.lastrowid
            
            cursor.execute(
                """
                SELECT CONCAT(first_name, ' ', last_name) 
                FROM users 
                WHERE user_id = %s
                """,
                (assigned_to_id,)
            )
            assigned_to_name = cursor.fetchone()
            assigned_to_name = assigned_to_name[0] if assigned_to_name and assigned_to_name[0] else 'Unassigned'
            
            conn.commit()
            
            success_msg = f'Task "{title}" created successfully and assigned to staff member'
            if is_ajax:
                return jsonify({
                    'success': True, 
                    'message': success_msg,
                    'task': {
                        'task_id': task_id,
                        'title': title,
                        'description': description,
                        'category': category,
                        'priority': priority,
                        'status': 'pending',
                        'due_date': parsed_date.isoformat(),
                        'assigned_to_name': assigned_to_name
                    }
                })
            flash(success_msg, 'success')
            return redirect(url_for('main.task'))
            
    except ValueError as e:
        error_msg = f'Invalid data: {str(e)}'
        if is_ajax:
            return jsonify({'success': False, 'message': error_msg}), 400
        flash(error_msg, 'danger')
        return redirect(url_for('main.task'))
        
    except Exception as e:
        conn.rollback()
        error_msg = f'Error creating task: {str(e)}'
        print(f"Error in add_task: {str(e)}")
        if is_ajax:
            return jsonify({'success': False, 'message': error_msg}), 500
        flash(error_msg, 'danger')
        return redirect(url_for('main.task'))

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

@main_bp.route('/users/delete/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete a user"""
    # Check if user is logged in and is an admin
    if 'user_id' not in session or session.get('role') != 'Admin':
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
    
    try:
        with get_cursor() as cursor:
            # Check if user exists and prevent self-deletion
            cursor.execute("SELECT user_id, role FROM users WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()
            
            if not user:
                return jsonify({'success': False, 'message': 'User not found'}), 404
            
            # Prevent deleting the currently logged-in admin
            if user_id == session['user_id']:
                return jsonify({'success': False, 'message': 'Cannot delete your own account'}), 400
            
            # Delete the user
            cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Failed to delete user'}), 500
            
            return jsonify({'success': True, 'message': 'User deleted successfully'})
            
    except Exception as e:
        error_msg = str(e)
        print(f"Error in delete_user: {error_msg}")
        
        # Handle specific foreign key constraint errors
        if "Cannot delete or update a parent row" in error_msg and "foreign key constraint" in error_msg:
            if "cart_items" in error_msg:
                user_message = "Cannot delete user. They still have items in their cart."
            elif "orders" in error_msg:
                user_message = "Cannot delete user. They have existing orders."
            elif "stock_requests" in error_msg:
                user_message = "Cannot delete user. They have pending stock requests."
            elif "new_arrival_alerts" in error_msg:
                user_message = "Cannot delete user. They have pending arrival alerts."
            else:
                user_message = "Cannot delete user. They have associated records that must be removed first."
        else:
            user_message = "An error occurred while deleting the user."
            
        return jsonify({'success': False, 'message': user_message}), 500

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

# ===== Category Management =====
@main_bp.route('/add_category', methods=['POST'])
def add_category():
    """Add a new category with case-insensitive duplicate validation"""
    if session.get('role') != 'Admin':
        flash('Only administrators can add categories.', 'error')
        return redirect(url_for('main.stock'))
    
    try:
        category_name = request.form.get('name', '').strip()
        category_description = request.form.get('description', '').strip()
        
        # Validate input
        if not category_name:
            flash('Category name is required.', 'error')
            return redirect(url_for('main.stock'))
        
        # Check for case-insensitive duplicate
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT name FROM categories WHERE LOWER(name) = LOWER(%s)", (category_name,))
        existing_category = cursor.fetchone()
        cursor.close()
        
        if existing_category:
            flash(f'Category "{category_name}" already exists.', 'error')
            return redirect(url_for('main.stock'))
        
        # Insert new category
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO categories (name, description) VALUES (%s, %s)",
            (category_name, category_description if category_description else None)
        )
        conn.commit()
        cursor.close()
        
        flash(f'Category "{category_name}" added successfully!', 'success')
        return redirect(url_for('main.stock'))
        
    except Exception as e:
        print(f"Error adding category: {e}")
        flash('An error occurred while adding the category. Please try again.', 'error')
        return redirect(url_for('main.stock'))

# ===== Error Handlers =====
@main_bp.app_errorhandler(404)
def page_not_found(e):
    return render_template('base.html', error_message='Page not found'), 404
