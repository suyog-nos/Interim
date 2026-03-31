from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
import re
from datetime import datetime
from forms import RegistrationForm
from config import conn, check_connection, get_db_connection
from contextlib import contextmanager
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import requests as http_requests

# Khalti configuration
KHALTI_SECRET_KEY = os.environ.get('KHALTI_SECRET_KEY')
KHALTI_BASE_URL = 'https://dev.khalti.com/api/v2'  # Sandbox URL

if not KHALTI_SECRET_KEY:
    print("WARNING: Khalti secret key not found in environment variables. Payment features may not work.")
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import datetime


# Create a Blueprint for all routes
main_bp = Blueprint('main', __name__)


def get_cursor():
    """Helper function to get a new cursor for each request"""
    active_conn = check_connection()
    if active_conn is None:
        return None
    return active_conn.cursor()

@contextmanager
def get_db_context(commit=False):
    """Context manager for database connections"""
    connection = get_db_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        yield cursor
        if commit:
            connection.commit()
    except Exception as e:
        if commit:
            connection.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


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
        
    flash_sale_products = []
    best_seller_products = []
    try:
        with get_db_context() as cursor:
            # Query for flash sale items: active, low stock (1-10)
            cursor.execute("""
                SELECT 
                    p.product_id, 
                    p.name, 
                    p.price, 
                    p.stock_quantity, 
                    p.image_url, 
                    p.brand,
                    c.name AS category_name
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.category_id
                WHERE p.status = 'active'
                  AND p.stock_quantity > 0
                  AND p.stock_quantity <= 10
                ORDER BY p.stock_quantity ASC, p.product_id DESC
                LIMIT 6
            """)
            flash_sale_products = cursor.fetchall()
            
            # Format product data directly using existing rules
            for p in flash_sale_products:
                if 'price' in p and p['price'] is not None:
                    p['price'] = float(p['price'])
                
                # Image handler
                if not p.get('image_url'):
                    p['image_url'] = 'static/images/placeholder-product.png'
                elif not any(p['image_url'].startswith(prefix) for prefix in ['http://', 'https://', '/static/', 'static/']):
                    p['image_url'] = f"static/images/{p['image_url'].lstrip('/')}"
                    
            # Query for best seller items
            cursor.execute("""
                SELECT 
                    p.product_id, 
                    p.name, 
                    p.price, 
                    p.stock_quantity, 
                    p.image_url, 
                    p.brand,
                    c.name AS category_name,
                    SUM(oi.quantity) AS total_sold
                FROM order_items oi
                JOIN orders o ON oi.order_id = o.order_id
                JOIN products p ON oi.product_id = p.product_id
                LEFT JOIN categories c ON p.category_id = c.category_id
                WHERE o.order_status = 'completed'
                  AND o.created_at >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
                  AND p.status = 'active'
                  AND p.stock_quantity > 0
                GROUP BY 
                    p.product_id, p.name, p.price, p.stock_quantity, 
                    p.image_url, p.brand, c.name
                ORDER BY total_sold DESC
                LIMIT 4
            """)
            best_seller_products = cursor.fetchall()
            
            # Format product data directly using existing rules
            for p in best_seller_products:
                if 'price' in p and p['price'] is not None:
                    p['price'] = float(p['price'])
                
                # Image handler
                if not p.get('image_url'):
                    p['image_url'] = 'static/images/placeholder-product.png'
                elif not any(p['image_url'].startswith(prefix) for prefix in ['http://', 'https://', '/static/', 'static/']):
                    p['image_url'] = f"static/images/{p['image_url'].lstrip('/')}"
                    
    except Exception as e:
        print(f"Error fetching products: {e}")
        
    return render_template('index.html', flash_sale_products=flash_sale_products, best_seller_products=best_seller_products)

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
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect(url_for('login.login'))
        
    # Check role based access
    if session.get('role') not in ['Admin', 'Staff']:
        flash('Access denied. Admin or Staff permission required.', 'danger')
        return redirect(url_for('main.index'))

    try:
        with get_db_context() as cursor:
            # 1. Total Sales (Completed orders)
            cursor.execute("SELECT COALESCE(SUM(total_amount), 0) as total_sales FROM orders WHERE order_status = 'completed'")
            total_sales = cursor.fetchone()['total_sales']
            
            # 2. Total Orders
            cursor.execute("SELECT COUNT(*) as total_orders FROM orders")
            total_orders = cursor.fetchone()['total_orders']
            
            # 3. Total Customers
            cursor.execute("SELECT COUNT(*) as total_customers FROM users WHERE role = 'Customer'")
            total_customers = cursor.fetchone()['total_customers']
            
            # 4. Low Stock Products (threshold < 10)
            cursor.execute("SELECT COUNT(*) as low_stock_count FROM products WHERE stock_quantity < 10")
            low_stock_count = cursor.fetchone()['low_stock_count']
            
            # 5. Monthly Sales Data (Last 6 months)
            cursor.execute("""
                SELECT 
                    DATE_FORMAT(created_at, '%Y-%m') as month,
                    SUM(total_amount) as sales
                FROM orders 
                WHERE order_status = 'completed' 
                AND created_at >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
                GROUP BY month
                ORDER BY month ASC
            """)
            monthly_sales_data = cursor.fetchall()
            
            # Format for Chart.js
            months = []
            sales = []
            for entry in monthly_sales_data:
                # Convert '2023-01' to 'Jan 2023'
                date_obj = datetime.strptime(entry['month'], '%Y-%m')
                months.append(date_obj.strftime('%b %Y'))
                sales.append(float(entry['sales']))
                
            # 6. Top Selling Products
            cursor.execute("""
                SELECT 
                    p.name,
                    SUM(oi.quantity) as total_sold
                FROM order_items oi
                JOIN products p ON oi.product_id = p.product_id
                JOIN orders o ON oi.order_id = o.order_id
                WHERE o.order_status = 'completed'
                  AND o.created_at >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
                GROUP BY p.product_id
                ORDER BY total_sold DESC
                LIMIT 5
            """)
            top_products = cursor.fetchall()
            
            product_names = [p['name'] for p in top_products]
            product_sales = [int(p['total_sold']) for p in top_products]
            
            # 7. Recent Orders
            cursor.execute("""
                SELECT 
                    o.order_id,
                    o.order_type,
                    o.transaction_code,
                    CONCAT(u.first_name, ' ', u.last_name) as customer_name,
                    u.phone as customer_phone,
                    o.total_amount,
                    o.order_status,
                    o.created_at
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.user_id
                ORDER BY o.created_at DESC
                LIMIT 5
            """)
            recent_orders = cursor.fetchall()
            
            # Process recent orders to handle walk-in customers
            for order in recent_orders:
                # Check if this is a walk-in customer (POS order with name in transaction_code)
                if (order['order_type'] == 'POS' and order['transaction_code'] and 
                    order['transaction_code'].strip() != ''):
                    order['customer_name'] = order['transaction_code']  # Walk-in customer name
                elif not order['customer_name']:
                    order['customer_name'] = 'Walk-in Customer'
            
            return render_template('dashboard.html', 
                                 total_sales=total_sales,
                                 total_orders=total_orders,
                                 total_customers=total_customers,
                                 low_stock_count=low_stock_count,
                                 months=months,
                                 sales=sales,
                                 product_names=product_names,
                                 product_sales=product_sales,
                                 recent_orders=recent_orders)
                                 
    except Exception as e:
        print(f"Error loading dashboard: {e}")
        # Return empty data structure on error to prevent template crash
        return render_template('dashboard.html', 
                             total_sales=0, total_orders=0, 
                             total_customers=0, low_stock_count=0,
                             months=[], sales=[], 
                             product_names=[], product_sales=[], 
                             recent_orders=[])

@main_bp.route('/pos', methods=['GET'])
def pos():
    # Check access
    if session.get('role') not in ['Admin', 'Staff']:
        flash('Access denied. Staff permission required.', 'danger')
        return redirect(url_for('main.index'))

    try:
        with get_cursor() as cursor:
            # Get products from database
            cursor.execute("""
                SELECT p.product_id, p.name, p.price, p.stock_quantity, p.image_url, c.name as category 
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
                    'id': product[0],  # product_id
                    'name': product[1],
                    'price': float(product[2]) if product[2] else 0.0,
                    'stock': product[3],
                    'image_url': product[4],  # image_url field
                    'category': product[5] or 'Uncategorized',
                    'available': product[3] > 0
                })
                
        return render_template('POS.html', products=products_list)
        
    except Exception as e:
        print(f'Error loading POS: {str(e)}')
        flash('Error loading POS system', 'danger')
        return render_template('POS.html', products=[])

@main_bp.route('/pos/checkout', methods=['POST'])
def pos_checkout():
    if session.get('role') not in ['Admin', 'Staff']:
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 401

    try:
        data = request.get_json()
        items = data.get('items', [])
        total_amount = data.get('total', 0)
        payment_method = data.get('payment_method', 'Cash')
        customer_id = data.get('customer_id')  # Get customer_id from request
        customer_name = data.get('customer_name')  # Get customer_name for walk-in customers
        customer_phone = data.get('customer_phone')  # Get customer_phone for walk-in customers
        
        if not items:
            return jsonify({'success': False, 'message': 'Cart is empty'}), 400

        staff_id = session.get('user_id')  # Staff member processing the sale
        
        with get_db_context(commit=True) as cursor:
            # 1. Create Order
            # payment_status is 'Paid' for POS by default
            # For walk-in customers, store name in transaction_code field and use staff_id as user_id
            transaction_info = customer_name if customer_name and customer_id is None else None
            
            # For walk-in customers, we need a non-null user_id, so use staff_id as fallback
            # The transaction_code will identify it as a walk-in customer
            final_user_id = customer_id if customer_id is not None else staff_id
            
            # Map frontend payment methods to database values
            payment_type_db = 'Pay at Store' if payment_method == 'Cash' else 'Pay Online'
            
            cursor.execute("""
                INSERT INTO orders 
                (user_id, staff_id, order_type, payment_type, payment_status, total_amount, order_status, created_at, transaction_code)
                VALUES (%s, %s, 'POS', %s, 'Paid', %s, 'completed', NOW(), %s)
            """, (final_user_id, staff_id, payment_type_db, total_amount, transaction_info))
            
            order_id = cursor.lastrowid
            
            # 2. Process Items
            for item in items:
                product_id = item.get('id')
                quantity = item.get('quantity')
                price = item.get('price')
                
                # Check stock first
                cursor.execute("SELECT stock_quantity FROM products WHERE product_id = %s", (product_id,))
                result = cursor.fetchone()
                
                if not result:
                    raise Exception(f"Product ID {product_id} not found")
                
                current_stock = result['stock_quantity']
                
                if current_stock < quantity:
                    raise Exception(f"Insufficient stock for product {item.get('name')}")
                
                # Insert Order Item with sold_unit
                cursor.execute("""
                    INSERT INTO order_items (order_id, product_id, quantity, sold_unit, price_at_order)
                    VALUES (%s, %s, %s, 'piece', %s)
                """, (order_id, product_id, quantity, price))
                
                # Update Stock
                cursor.execute("""
                    UPDATE products 
                    SET stock_quantity = stock_quantity - %s 
                    WHERE product_id = %s
                """, (quantity, product_id))
                
            return jsonify({
                'success': True, 
                'sale_id': order_id, 
                'message': 'Sale completed successfully'
            })

    except Exception as e:
        print(f"POS Checkout Error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@main_bp.route('/api/search/customers')
def search_customers():
    """Search customers by name, phone, or email for POS"""
    if session.get('role') not in ['Admin', 'Staff']:
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 401
    
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify([])
    
    try:
        with get_db_context() as cursor:
            cursor.execute("""
                SELECT user_id, first_name, last_name, email, phone
                FROM users 
                WHERE role = 'Customer' 
                AND (first_name LIKE %s OR last_name LIKE %s OR phone LIKE %s OR email LIKE %s)
                ORDER BY first_name, last_name
                LIMIT 10
            """, (f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%'))
            
            customers = cursor.fetchall()
            return jsonify(customers)
            
    except Exception as e:
        print(f"Customer search error: {e}")
        return jsonify([]), 500

@main_bp.route('/demand-forecasting')
def demand_forecasting():
    try:
        connection = check_connection()
        if connection is None:
            flash("Database connection failed", "danger")
            return render_template('demand-forecasting.html', forecast_results=[])

        query = """
            SELECT
                oi.product_id,
                p.name AS product_name,
                DATE_FORMAT(o.created_at, '%Y-%m') AS month,
                SUM(oi.quantity) AS total_quantity
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            JOIN products p ON oi.product_id = p.product_id
            WHERE o.order_status = 'completed'
            GROUP BY oi.product_id, p.name, month
            ORDER BY oi.product_id, month;
        """

        cursor = connection.cursor(dictionary=True)
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return render_template('demand-forecasting.html', forecast_results=[])

        # Convert to DataFrame
        df = pd.DataFrame(rows)
        df["total_quantity"] = pd.to_numeric(df["total_quantity"], errors="coerce").fillna(0)
        
        forecast_results = []
        
        # Process each product
        for (product_id, product_name), group in df.groupby(["product_id", "product_name"]):
            group = group.sort_values("month").reset_index(drop=True)
            
            quantities = group["total_quantity"].values.astype(float)
            n = len(quantities)
            
            # X = Month Index (1, 2, 3...), y = Quantity
            X = np.arange(1, n + 1).reshape(-1, 1)
            y = quantities
            
            # Train Linear Regression
            model = LinearRegression()
            model.fit(X, y)
            
            # Predict next month
            next_month_index = np.array([[n + 1]])
            predicted = model.predict(next_month_index)[0]
            predicted = max(0, round(predicted, 2))  # No negative demand
            
            # Get last 3 months sales
            last_3 = quantities[-3:].tolist() if n >= 3 else quantities.tolist()
            last_3_str = " → ".join([str(int(q)) for q in last_3])
            
            # Determine trend
            if n > 0:
                last_val = quantities[-1]
                diff = predicted - last_val
                if diff > 0.5:
                    trend = "Up" 
                    trend_class = "trend-up"
                    trend_icon = "fa-arrow-up"
                elif diff < -0.5:
                    trend = "Down" 
                    trend_class = "trend-down"
                    trend_icon = "fa-arrow-down"
                else:
                    trend = "Flat"
                    trend_class = "trend-flat"
                    trend_icon = "fa-minus"
            else:
                trend = "New"
                trend_class = "trend-flat"
                trend_icon = "fa-minus"

            # Prepare data for Chart.js
            # 1. Labels: Convert YYYY-MM to "Jan", "Feb", etc.
            try:
                months_list = group["month"].tolist()
                chart_labels = [datetime.strptime(m, '%Y-%m').strftime('%b') for m in months_list]
                
                # Calculate next month label
                if n > 0:
                    last_month_str = months_list[-1]
                    last_month_dt = datetime.strptime(last_month_str, '%Y-%m')
                    if last_month_dt.month == 12:
                        next_month_dt = last_month_dt.replace(year=last_month_dt.year + 1, month=1)
                    else:
                        next_month_dt = last_month_dt.replace(month=last_month_dt.month + 1)
                    next_month_label = next_month_dt.strftime('%b')
                else:
                    next_month_label = "Next"
                
                # Add prediction label
                chart_labels.append(next_month_label)
                
            except Exception as e:
                print(f"Date parsing error: {e}")
                chart_labels = [f"M{i+1}" for i in range(n)] + ["Next"]

            forecast_results.append({
                "product_id": product_id,
                "product_name": product_name,
                "last_3_month_sales": last_3,
                "last_3_str": last_3_str,
                "predicted_next_month": int(round(predicted)),
                "trend": trend,
                "trend_class": trend_class,
                "trend_icon": trend_icon,
                "chart_history": quantities.tolist(),
                "chart_labels": chart_labels
            })
            
        # Calculate summary stats
        total_products = len(forecast_results)
        if total_products > 0:
            predicted_values = [f['predicted_next_month'] for f in forecast_results]
            avg_pred = round(sum(predicted_values) / total_products, 1)
            highest_pred = max(predicted_values)
            lowest_pred = min(predicted_values)
        else:
            avg_pred = 0
            highest_pred = 0
            lowest_pred = 0

        stats = {
            'products': total_products,
            'avg_pred': avg_pred,
            'highest': highest_pred,
            'lowest': lowest_pred
        }
        
        return render_template('demand-forecasting.html', forecast_results=forecast_results, stats=stats)

    except Exception as e:
        print(f"Forecasting Error: {e}")
        flash(f"Error generating predictions: {e}", "danger")
        return render_template('demand-forecasting.html', forecast_results=[], stats=None)

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
        purchase_prices = request.form.getlist('purchase_price[]')

        if not staff_id:
            return jsonify({'success': False, 'message': 'User not logged in'}), 401

        if not product_ids or not quantities:
            return jsonify({'success': False, 'message': 'No products provided'}), 400

        success_count = 0
        with get_cursor() as cursor:
            for index, product_id in enumerate(product_ids):
                quantity = quantities[index] if index < len(quantities) else None
                supplier_id = supplier_ids[index] if index < len(supplier_ids) else ''
                purchase_price = purchase_prices[index] if index < len(purchase_prices) and purchase_prices[index] else 0.0

                if not product_id or not quantity:
                    continue

                try:
                    quantity = int(quantity)
                    purchase_price = float(purchase_price)
                except ValueError:
                    continue

                if quantity <= 0:
                    continue

                # Convert empty string to NULL for supplier_id and validate it's required
                if not supplier_id or supplier_id == '':
                    continue  # Skip rows without supplier (now required)

                cursor.execute(
                    """
                    INSERT INTO new_arrival_alerts 
                    (staff_id, product_id, quantity_received, supplier_id, purchase_price, staff_notes, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'Pending')
                    """,
                    (staff_id, product_id, quantity, supplier_id, purchase_price, '')
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
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        search_query = request.args.get('q', '').strip()
        category_id = request.args.get('category_id', '', type=str)
        offset = (page - 1) * per_page

        with get_cursor() as cursor:
            # First, check if tables exist
            cursor.execute("SHOW TABLES LIKE 'products'")
            if not cursor.fetchone():
                return "Products table does not exist. Please run the setup."
                
            cursor.execute("SHOW TABLES LIKE 'categories'")
            if not cursor.fetchone():
                return "Categories table does not exist. Please run the setup."
            
            # Base query parts
            where_clauses = []
            params = []
            if search_query:
                where_clauses.append("(p.name LIKE %s OR p.sku LIKE %s OR c.name LIKE %s)")
                q_param = f"%{search_query}%"
                params.extend([q_param, q_param, q_param])
            
            if category_id:
                where_clauses.append("p.category_id = %s")
                params.append(category_id)

            where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            # Get total count for pagination with search
            count_query = f"""
                SELECT COUNT(*) 
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.category_id
                {where_clause}
            """
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]
            total_pages = (total_count + per_page - 1) // per_page

            query = f"""
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
                {where_clause}
                ORDER BY c.name, p.name
                LIMIT %s OFFSET %s
            """
            
            query_params = params + [per_page, offset]
            print(f"Executing query with search '{search_query}', page {page}, limit {per_page}")  # Debug log
            cursor.execute(query, query_params)
            products = cursor.fetchall()
            print(f"Found {len(products)} products for current page")  # Debug log
            
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
            
            return render_template('stock.html', 
                                 products=products_list, 
                                 suppliers=suppliers_list, 
                                 categories=categories_list,
                                 page=page,
                                 per_page=per_page,
                                 total_pages=total_pages,
                                 total_count=total_count,
                                 search_query=search_query,
                                 selected_category=category_id)
            
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
                new_product_id = cursor.lastrowid
                
                # If there's initial stock, log it in stock_history so it updates supplier stats
                if stock_quantity > 0:
                    cursor.execute(
                        """
                        INSERT INTO stock_history (product_id, supplier_id, quantity_received, purchase_price)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (new_product_id, supplier_id, stock_quantity, price)  # Using selling price as a default cost
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

@main_bp.route('/api/orders')
def api_orders():
    """API endpoint to get all orders for sales page with pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        search_query = request.args.get('q', '').strip()
        offset = (page - 1) * per_page

        with get_db_context() as cursor:
            # Base query parts for searching
            where_clause = ""
            params = []
            if search_query:
                # Add LEFT JOIN to search by customer name from users table
                where_clause = """
                    LEFT JOIN users u ON o.user_id = u.user_id
                    WHERE o.order_id LIKE %s 
                    OR u.first_name LIKE %s 
                    OR u.last_name LIKE %s
                    OR o.order_id IN (
                        SELECT order_id FROM order_items 
                        WHERE product_name LIKE %s
                    )
                """
                q_param = f"%{search_query}%"
                params = [q_param, q_param, q_param, q_param]

            # Get total count of unique orders with search
            count_query = f"SELECT COUNT(DISTINCT o.order_id) as total FROM orders o {where_clause}"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()['total']
            total_pages = (total_count + per_page - 1) // per_page

            # Get paginated order IDs with search
            query = f"""
                SELECT DISTINCT o.order_id, o.created_at
                FROM orders o 
                {where_clause}
                ORDER BY o.created_at DESC, o.order_id DESC
                LIMIT %s OFFSET %s
            """
            
            query_params = params + [per_page, offset]
            cursor.execute(query, query_params)
            order_ids = [row['order_id'] for row in cursor.fetchall()]

            if not order_ids:
                return jsonify({
                    'success': True, 
                    'orders': [], 
                    'total_pages': total_pages, 
                    'current_page': page,
                    'total_count': total_count
                })

            # Get full details for these specific order IDs
            format_strings = ','.join(['%s'] * len(order_ids))
            cursor.execute(f"""
                SELECT 
                    o.order_id,
                    o.order_status,
                    o.total_amount,
                    o.created_at,
                    o.payment_type,
                    o.payment_status,
                    o.transaction_code,
                    o.order_type,
                    o.user_id,
                    o.staff_id,
                    CONCAT(u.first_name, ' ', u.last_name) as customer_name,
                    u.phone as customer_phone,
                    oi.order_item_id,
                    oi.quantity,
                    oi.price_at_order,
                    p.name as product_name
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.user_id
                LEFT JOIN order_items oi ON o.order_id = oi.order_id
                LEFT JOIN products p ON oi.product_id = p.product_id
                WHERE o.order_id IN ({format_strings})
                ORDER BY o.created_at DESC, o.order_id DESC, oi.order_item_id ASC
            """, tuple(order_ids))
            rows = cursor.fetchall()
            
            # Group orders with their items
            orders_map = {}
            for row in rows:
                order_id = row['order_id']
                if order_id not in orders_map:
                    # For walk-in customers, always show name from transaction_code
                    # Walk-in customers are identified by having a name in transaction_code
                    # and being a POS order (order_type = 'POS')
                    customer_name = row['customer_name']
                    
                    # Check if this is a walk-in customer (POS order with name in transaction_code)
                    if (row['order_type'] == 'POS' and row['transaction_code'] and 
                        row['transaction_code'].strip() != ''):
                        customer_name = row['transaction_code']  # Walk-in customer name
                    
                    orders_map[order_id] = {
                        'order_id': order_id,
                        'customer_name': customer_name or 'Walk-in Customer',
                        'customer_phone': row['customer_phone'],
                        'order_status': row['order_status'],
                        'total_amount': float(row['total_amount'] or 0),
                        'created_at': row['created_at'].isoformat() if row['created_at'] else '',
                        'payment_type': row['payment_type'],
                        'payment_status': row['payment_status'],
                        'transaction_code': row['transaction_code'],
                        'order_type': row['order_type'],
                        'items': []
                    }
                
                # Add items if they exist
                if row['order_item_id']:
                    orders_map[order_id]['items'].append({
                        'product_name': row['product_name'] or 'Product',
                        'quantity': row['quantity'] or 0,
                        'price_at_order': float(row['price_at_order'] or 0)
                    })
            
            # Re-sort because orders_map doesn't preserve SQL order perfectly if IDs are non-sequential
            # although in this case they should be fine. But let's be safe.
            orders = [orders_map[oid] for oid in order_ids if oid in orders_map]
            
            return jsonify({
                'success': True, 
                'orders': orders,
                'total_pages': total_pages,
                'current_page': page,
                'total_count': total_count
            })
        
    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'success': False, 'message': 'Failed to load orders'}), 500
        
    except Exception as e:
        print(f"Error fetching orders: {e}")
        return jsonify({'success': False, 'message': 'Failed to load orders'}), 500

@main_bp.route('/api/orders/stats')
def api_orders_stats():
    """API endpoint to get order statistics"""
    try:
        with get_db_context() as cursor:
            # Get total sales
            cursor.execute("SELECT COALESCE(SUM(total_amount), 0) as total_sales FROM orders WHERE order_status != 'cancelled'")
            total_sales = cursor.fetchone()['total_sales']
            
            # Get today's sales
            cursor.execute("""
                SELECT COALESCE(SUM(total_amount), 0) as today_sales 
                FROM orders 
                WHERE DATE(created_at) = CURDATE() AND order_status != 'cancelled'
            """)
            today_sales = cursor.fetchone()['today_sales']
            
            # Get total orders
            cursor.execute("SELECT COUNT(*) as total_orders FROM orders WHERE order_status != 'cancelled'")
            total_orders = cursor.fetchone()['total_orders']
            
            # Get average order value
            cursor.execute("SELECT COALESCE(AVG(total_amount), 0) as avg_order_value FROM orders WHERE order_status != 'cancelled'")
            avg_order_value = cursor.fetchone()['avg_order_value']
            
            return jsonify({
                'success': True,
                'total_sales': float(total_sales),
                'today_sales': float(today_sales),
                'total_orders': total_orders,
                'avg_order_value': float(avg_order_value)
            })
        
    except Exception as e:
        print(f"Error fetching order stats: {e}")
        return jsonify({'success': False, 'message': 'Failed to load statistics'}), 500

@main_bp.route('/api/products')
def api_products():
    """API endpoint to get all products for sales page dropdown"""
    try:
        with get_db_context() as cursor:
            cursor.execute("SELECT product_id, name as product_name, price as selling_price, stock_quantity FROM products WHERE status = 'active' OR status IS NULL ORDER BY name")
            products = cursor.fetchall()
            
            # Convert decimals to float for JSON serialization if needed
            for p in products:
                if 'selling_price' in p and p['selling_price']:
                    p['selling_price'] = float(p['selling_price'])
                
            return jsonify({'success': True, 'products': products})
    except Exception as e:
        print(f"Error fetching products API: {e}")
        return jsonify({'success': False, 'message': 'Failed to load products'}), 500

@main_bp.route('/api/orders/<int:order_id>')
def api_order_details(order_id):
    """API endpoint to get details of a specific order"""
    try:
        with get_db_context() as cursor:
            # Get order details
            cursor.execute("""
                SELECT 
                    o.order_id,
                    o.order_status,
                    o.total_amount,
                    o.created_at,
                    o.payment_type,
                    o.payment_status,
                    o.transaction_code,
                    o.order_type,
                    CONCAT(u.first_name, ' ', u.last_name) as customer_name,
                    u.phone as customer_phone,
                    u.email as customer_email
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.user_id
                WHERE o.order_id = %s
            """, (order_id,))
            order = cursor.fetchone()
            
            if not order:
                return jsonify({'success': False, 'message': 'Order not found'}), 404
                
            # Get order items
            cursor.execute("""
                SELECT 
                    oi.order_item_id,
                    oi.quantity,
                    oi.price_at_order,
                    p.name as product_name,
                    p.sku
                FROM order_items oi
                LEFT JOIN products p ON oi.product_id = p.product_id
                WHERE oi.order_id = %s
            """, (order_id,))
            items = cursor.fetchall()
            
            # Format data
            if order['created_at']:
                order['created_at'] = order['created_at'].isoformat()
            
            # Convert decimals
            if order['total_amount']:
                order['total_amount'] = float(order['total_amount'])
                
            for item in items:
                if item['price_at_order']:
                    item['price_at_order'] = float(item['price_at_order'])
            
            order['items'] = items
            
            return jsonify({'success': True, 'order': order})
        
    except Exception as e:
        print(f"Error fetching order details: {e}")
        return jsonify({'success': False, 'message': 'Failed to load order details'}), 500

@main_bp.route('/orders/add', methods=['POST'])
def add_order():
    """API endpoint to add a new order from sales page"""
    try:
        # Get form data
        customer_name = request.form.get('customer_name')
        customer_email = request.form.get('customer_email')
        customer_phone = request.form.get('customer_phone')
        sale_date = request.form.get('sale_date')
        total_amount = request.form.get('total_amount')
        payment_method = request.form.get('payment_method')
        notes = request.form.get('notes')
        
        # Get product data
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        prices = request.form.getlist('price[]')
        
        # Validate required fields
        if not all([customer_name, customer_phone, sale_date, total_amount, payment_method]):
            return jsonify({'success': False, 'message': 'Missing required fields'})
        
        if not product_ids or not quantities or not prices:
            return jsonify({'success': False, 'message': 'No products added'})
        
        # Use context manager for automatic commit/rollback and connection closing
        with get_db_context(commit=True) as cursor:
            # Create or find customer user
            cursor.execute("""
                SELECT user_id FROM users 
                WHERE phone = %s OR (email = %s AND email IS NOT NULL AND email != '')
                LIMIT 1
            """, (customer_phone, customer_email))
            existing_user = cursor.fetchone()
            
            if existing_user:
                user_id = existing_user['user_id']
            else:
                # Create new user as customer - Handle splitting name into first/last
                full_name = customer_name.strip()
                name_parts = full_name.split(None, 1)
                first = name_parts[0]
                last = name_parts[1] if len(name_parts) > 1 else ''
                
                cursor.execute("""
                    INSERT INTO users (first_name, last_name, phone, email, role, hashed_password)
                    VALUES (%s, %s, %s, %s, 'Customer', 'temp_password')
                """, (first, last, customer_phone, customer_email))
                user_id = cursor.lastrowid
            
            # Create order
            cursor.execute("""
                INSERT INTO orders (user_id, order_type, payment_type, total_amount, order_status)
                VALUES (%s, 'POS', %s, %s, 'completed')
            """, (user_id, payment_method, total_amount))
            order_id = cursor.lastrowid
            
            # Add order items
            for i in range(len(product_ids)):
                if product_ids[i] and quantities[i] and prices[i]:
                    cursor.execute("""
                        INSERT INTO order_items (order_id, product_id, quantity, price_at_order)
                        VALUES (%s, %s, %s, %s)
                    """, (order_id, product_ids[i], quantities[i], prices[i]))
                    
                    # Update product stock
                    cursor.execute("""
                        UPDATE products 
                        SET stock_quantity = stock_quantity - %s
                        WHERE product_id = %s AND stock_quantity >= %s
                    """, (quantities[i], product_ids[i], quantities[i]))
                    
                    if cursor.rowcount == 0:
                        raise Exception(f"Insufficient stock for product ID {product_ids[i]}")
            
            return jsonify({'success': True, 'message': 'Order added successfully'})
            
    except Exception as e:
        print(f"Error processing order: {e}")
        return jsonify({'success': False, 'message': f'Failed to process order: {str(e)}'}), 500

@main_bp.route('/orders')
def orders():
    # Check if user is logged in and has proper permissions
    if 'user_id' not in session or session.get('role') not in ['Admin', 'Staff']:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    # Dual-pagination parameter extraction
    active_page = request.args.get('active_page', 1, type=int)
    history_page = request.args.get('history_page', 1, type=int)
    per_page = 10
    
    active_offset = (active_page - 1) * per_page
    history_offset = (history_page - 1) * per_page
    
    # Optional tab memory flag
    active_tab = request.args.get('tab', 'active')
    
    try:
        with get_db_context() as cursor:
            # --- 1. Fetch Active Orders (Paginated) ---
            cursor.execute("""
                SELECT COUNT(*) as count FROM orders 
                WHERE order_status IN ('processing', 'ready_for_pickup', 'pending')
            """)
            total_active = cursor.fetchone()['count']
            total_active_pages = (total_active + per_page - 1) // per_page if total_active > 0 else 1
            
            cursor.execute("""
                SELECT o.order_id, 
                       TRIM(CONCAT(IFNULL(u.first_name, ''), ' ', IFNULL(u.last_name, ''))) as customer_name,
                       o.created_at, o.order_status, 
                       o.payment_type, o.payment_status, o.total_amount,
                       o.transaction_code, o.order_type
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.user_id
                WHERE o.order_status IN ('processing', 'ready_for_pickup', 'pending')
                ORDER BY o.created_at DESC
                LIMIT %s OFFSET %s
            """, (per_page, active_offset))
            active_data = cursor.fetchall()
            
            # --- 2. Fetch History Orders (Paginated) ---
            cursor.execute("""
                SELECT COUNT(*) as count FROM orders 
                WHERE order_status IN ('completed', 'cancelled')
            """)
            total_history = cursor.fetchone()['count']
            total_history_pages = (total_history + per_page - 1) // per_page if total_history > 0 else 1
            
            cursor.execute("""
                SELECT o.order_id, 
                       TRIM(CONCAT(IFNULL(u.first_name, ''), ' ', IFNULL(u.last_name, ''))) as customer_name,
                       o.created_at, o.order_status, 
                       o.payment_type, o.payment_status, o.total_amount,
                       o.transaction_code, o.order_type
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.user_id
                WHERE o.order_status IN ('completed', 'cancelled')
                ORDER BY o.created_at DESC
                LIMIT %s OFFSET %s
            """, (per_page, history_offset))
            history_data = cursor.fetchall()
            
            def group_orders(data_rows):
                o_dict = {}
                for row in data_rows:
                    order_id = row['order_id']
                    display_name = row['customer_name']
                    if not display_name or display_name.strip() == '':
                        display_name = 'Walk-in Customer'
                    o_dict[order_id] = {
                        'order_id': order_id,
                        'customer_name': display_name,
                        'created_at': row['created_at'],
                        'order_status': row['order_status'],
                        'payment_type': row['payment_type'],
                        'payment_status': row['payment_status'],
                        'total_amount': row['total_amount'],
                        'transaction_code': row['transaction_code'],
                        'order_type': row['order_type'],
                        'line_items': []
                    }
                return o_dict
                
            active_orders_dict = group_orders(active_data)
            history_orders_dict = group_orders(history_data)
            
            all_target_ids = list(active_orders_dict.keys()) + list(history_orders_dict.keys())
            
            # --- 3. Attach Items ---
            if all_target_ids:
                format_strings = ','.join(['%s'] * len(all_target_ids))
                cursor.execute(f"""
                    SELECT oi.order_id, oi.quantity, oi.price_at_order as price_per_item, p.name as product_name
                    FROM order_items oi
                    LEFT JOIN products p ON oi.product_id = p.product_id
                    WHERE oi.order_id IN ({format_strings})
                """, tuple(all_target_ids))
                
                items_data = cursor.fetchall()
                for item in items_data:
                    oid = item['order_id']
                    if item['product_name']:
                        formatted_item = {
                            'product_name': item['product_name'],
                            'quantity': item['quantity'],
                            'unit': 'pcs',
                            'price': item['price_per_item']
                        }
                        if oid in active_orders_dict:
                            active_orders_dict[oid]['line_items'].append(formatted_item)
                        elif oid in history_orders_dict:
                            history_orders_dict[oid]['line_items'].append(formatted_item)
            
            return render_template('orders.html', 
                                   active_orders=list(active_orders_dict.values()), 
                                   history_orders=list(history_orders_dict.values()),
                                   active_page=active_page, 
                                   history_page=history_page,
                                   total_active_pages=total_active_pages, 
                                   total_history_pages=total_history_pages, 
                                   total_active=total_active,
                                   total_history=total_history,
                                   per_page=per_page,
                                   active_tab=active_tab)
    except Exception as e:
        print(f"Error fetching orders: {e}")
        import traceback
        print(traceback.format_exc())
        return render_template('orders.html', active_orders=[], history_orders=[], active_page=1, history_page=1, total_active_pages=1, total_history_pages=1, total_active=0, total_history=0, per_page=10, active_tab='active')

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
        
        with get_db_context(commit=True) as cursor:
            # Get current order info before updating
            cursor.execute("""
                SELECT order_status, order_type, payment_status FROM orders WHERE order_id = %s
            """, (order_id,))
            order_data = cursor.fetchone()
            
            if not order_data:
                return redirect('/orders')
            
            current_status = order_data['order_status']
            order_type = order_data['order_type']
            payment_status = order_data['payment_status']
            
            # Simplified Stock Logic: 
            # Subtraction is now mainly handled at order creation (processing stage).
            # This function primarily handles restoration on cancellation and re-deduction if uncancelled.
            
            was_cancelled = current_status == 'cancelled'
            is_cancelled = new_status == 'cancelled'
            
            # A. Transition TO Cancelled: Restore Stock
            if is_cancelled and not was_cancelled:
                cursor.execute("SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
                items = cursor.fetchall()
                for item in items:
                    cursor.execute("UPDATE products SET stock_quantity = stock_quantity + %s WHERE product_id = %s", 
                                 (item['quantity'], item['product_id']))
                flash('Order cancelled and stock restored.', 'info')
            
            # B. Transition FROM Cancelled to Active: Deduct Stock again
            elif was_cancelled and new_status in ['processing', 'ready_for_pickup', 'completed']:
                cursor.execute("SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
                items = cursor.fetchall()
                for item in items:
                    cursor.execute("UPDATE products SET stock_quantity = stock_quantity - %s WHERE product_id = %s", 
                                 (item['quantity'], item['product_id']))
                flash('Order restored and stock deducted.', 'info')
            
            # Update order status
            if new_status == 'completed':
                cursor.execute("""
                    UPDATE orders 
                    SET order_status = %s, payment_status = 'Paid'
                    WHERE order_id = %s
                """, (new_status, order_id))
            else:
                cursor.execute("""
                    UPDATE orders 
                    SET order_status = %s
                    WHERE order_id = %s
                """, (new_status, order_id))
            
            flash(f'Order status updated to {new_status.replace("_", " ").capitalize()}', 'success')
            
        return redirect('/orders')
    except Exception as e:
        print(f"Error updating order status: {e}")
        flash(f'Error updating order: {str(e)}', 'danger')
        return redirect('/orders')

@main_bp.route('/orders/update-payment-status', methods=['POST'])
def update_payment_status():
    try:
        order_id = request.form.get('order_id')
        payment_type = request.form.get('payment_type')
        payment_status = request.form.get('payment_status')
        
        if not order_id or not payment_status:
            return redirect('/orders')
        
        with get_db_context(commit=True) as cursor:
            # Check current status
            cursor.execute("SELECT order_status, order_type, payment_status FROM orders WHERE order_id = %s", (order_id,))
            order = cursor.fetchone()
            
            if order and payment_status == 'Paid' and order['payment_status'] != 'Paid':
                flash('Payment status updated to Paid.', 'success')
            
            cursor.execute("""
                UPDATE orders 
                SET payment_status = %s, payment_type = %s
                WHERE order_id = %s
            """, (payment_status, payment_type, order_id))
        
        return redirect('/orders')
    except Exception as e:
        print(f"Error updating payment status: {e}")
        flash('Error updating payment info', 'danger')
        return redirect('/orders')

@main_bp.route('/cart')
def cart():
    if session.get('role') != 'Customer':
        flash('Please log in as a customer to view your cart', 'warning')
        return redirect(url_for('login.login'))
    return render_template('cart.html')

@main_bp.route('/checkout')
def checkout():
    # Role check
    user_id = session.get('user_id')
    role = session.get('role')
    
    if not user_id:
        flash('Please log in to checkout', 'warning')
        return redirect(url_for('login.login'))
        
    if role != 'Customer':
        flash('Only customers can access the checkout page', 'info')
        # If they are Admin/Staff, maybe they just want to see the page?
        # But user said ONLY customer. So we redirect to their respective home.
        if role == 'Admin': return redirect(url_for('main.dashboard'))
        if role == 'Staff': return redirect(url_for('main.pos'))
        return redirect(url_for('products.index'))
        
    try:
        # Get selected items from query param
        selected_ids_str = request.args.get('items', '')
        selected_ids = [int(id) for id in selected_ids_str.split(',') if id.strip().isdigit()]
        
        with get_db_context() as cursor:
            # Fetch cart items with product details
            query = """
                SELECT ci.cart_item_id, ci.quantity, p.product_id, p.name, p.price, p.image_url 
                FROM cart_items ci
                JOIN products p ON ci.product_id = p.product_id
                WHERE ci.user_id = %s
            """
            params = [user_id]
            
            if selected_ids:
                placeholders = ','.join(['%s'] * len(selected_ids))
                query += f" AND ci.cart_item_id IN ({placeholders})"
                params.extend(selected_ids)
                
            cursor.execute(query, params)
            cart_items = cursor.fetchall()
            
            if not cart_items:
                flash('Your cart is empty', 'info')
                return redirect(url_for('main.cart'))
            
            # Process items for template
            processed_items = []
            total = 0
            for item in cart_items:
                price = float(item['price']) if item['price'] is not None else 0.0
                quantity = int(item['quantity'])
                item['price'] = price
                processed_items.append(item)
                total += price * quantity
            
            return render_template('checkout.html', 
                                 cart_items=processed_items, 
                                 total=total)

    except Exception as e:
        import traceback
        print(f"Checkout load error: {e}")
        flash('Error loading checkout page', 'danger')
        return redirect(url_for('main.cart'))

@main_bp.route('/initiate-khalti-payment', methods=['POST'])
def initiate_khalti_payment():
    if session.get('role') != 'Customer':
        return jsonify({'error': 'Only customers can make payments'}), 403
    
    try:
        if 'user_id' not in session:
            return jsonify({'error': 'User not logged in'}), 401
            
        user_id = session['user_id']
        data = request.get_json() or {}
        selected_ids_str = data.get('items', '')
        
        # Robust parsing of items
        selected_ids = []
        if selected_ids_str and isinstance(selected_ids_str, str):
            selected_ids = [int(id) for id in selected_ids_str.split(',') if id and id.strip().isdigit()]
        
        with get_db_context() as cursor:
            # Recalculate total on server
            query = """
                SELECT ci.quantity, p.price 
                FROM cart_items ci
                JOIN products p ON ci.product_id = p.product_id
                WHERE ci.user_id = %s
            """
            params = [user_id]
            
            if selected_ids:
                placeholders = ','.join(['%s'] * len(selected_ids))
                query += f" AND ci.cart_item_id IN ({placeholders})"
                params.extend(selected_ids)
                
            cursor.execute(query, params)
            items = cursor.fetchall()
            
            if not items:
                print(f"DEBUG: No items found in cart for user {user_id} with cart_item_ids {selected_ids}")
                return jsonify({'error': 'No items found in cart to pay for. Your cart may have been cleared or items were moved.'}), 400
                
            amount = sum(float(item['price'] or 0) * item['quantity'] for item in items)
        
        if amount <= 0:
            print(f"DEBUG: Calculated amount is zero for user {user_id}")
            return jsonify({'error': 'Calculated total amount is zero. Cannot process payment.', 'calculated_amount': amount}), 400

        if not KHALTI_SECRET_KEY:
            print("ERROR: Khalti secret key is not configured!")
            return jsonify({'error': 'Khalti payment system is not configured on server.'}), 500

        # Amount in paisa (1 NPR = 100 paisa)
        amount_in_paisa = int(amount * 100)
        
        # Build return URL with items param
        return_url = request.host_url.rstrip('/') + url_for('main.khalti_callback')
        if selected_ids_str:
            return_url += f'?items={selected_ids_str}'
        
        purchase_order_id = f"order_{user_id}_{int(datetime.now().timestamp())}"
        
        payload = {
            'return_url': return_url,
            'website_url': request.host_url.rstrip('/'),
            'amount': amount_in_paisa,
            'purchase_order_id': purchase_order_id,
            'purchase_order_name': 'Yogimar Store Purchase',
            'customer_info': {
                'name': session.get('first_name', '') + ' ' + session.get('last_name', ''),
                'email': session.get('email', ''),
                'phone': session.get('phone', ''),
            }
        }
        
        headers = {
            'Authorization': f'Key {KHALTI_SECRET_KEY}',
            'Content-Type': 'application/json',
        }
        
        print(f"DEBUG: Initiating Khalti payment for user {user_id}, amount: {amount_in_paisa} paisa")
        
        response = http_requests.post(
            f'{KHALTI_BASE_URL}/epayment/initiate/',
            json=payload,
            headers=headers
        )
        
        if response.status_code == 200:
            resp_data = response.json()
            return jsonify({
                'payment_url': resp_data.get('payment_url'),
                'pidx': resp_data.get('pidx')
            })
        else:
            print(f"Khalti initiate error: {response.status_code} - {response.text}")
            return jsonify({'error': f'Khalti payment initiation failed: {response.text}'}), 400
            
    except Exception as e:
        import traceback
        print(f"KHALTI ERROR: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': f"Payment setup failed: {str(e)}"}), 400

@main_bp.route('/khalti/callback')
def khalti_callback():
    """Handle Khalti callback: Verify payment, create order, move items, clear cart"""
    if session.get('role') != 'Customer':
        flash('Access denied', 'danger')
        return redirect(url_for('login.login'))
    
    pidx = request.args.get('pidx')
    status = request.args.get('status')  # Khalti sends status in callback
    
    if not pidx:
        flash('Invalid payment verification', 'danger')
        return redirect(url_for('main.index'))
    
    # If Khalti reports non-completed status in the URL
    if status and status.lower() != 'completed':
        flash(f'Payment was not completed. Status: {status}', 'warning')
        return redirect(url_for('main.cart'))
        
    user_id = session['user_id']
    
    try:
        # Verify payment with Khalti Lookup API
        try:
            headers = {
                'Authorization': f'Key {KHALTI_SECRET_KEY}',
                'Content-Type': 'application/json',
            }
            lookup_response = http_requests.post(
                f'{KHALTI_BASE_URL}/epayment/lookup/',
                json={'pidx': pidx},
                headers=headers
            )
            
            if lookup_response.status_code == 200:
                lookup_data = lookup_response.json()
                payment_status = lookup_data.get('status', '')
                
                if payment_status.lower() != 'completed':
                    flash(f'Payment verification failed. Status: {payment_status}', 'warning')
                    return redirect(url_for('main.cart'))
                    
                print(f"Khalti payment verified: pidx={pidx}, status={payment_status}")
            else:
                print(f"Khalti lookup error: {lookup_response.status_code} - {lookup_response.text}")
                flash('Could not verify payment status with Khalti.', 'danger')
                return redirect(url_for('main.cart'))
                
        except Exception as ve:
            print(f"Khalti Verification Error: {ve}")
            flash('Could not verify payment status with Khalti.', 'danger')
            return redirect(url_for('main.cart'))

        # Get selected items from query param
        selected_ids_str = request.args.get('items', '')
        selected_ids = [int(id) for id in selected_ids_str.split(',') if id.strip().isdigit()]
        
        with get_db_context(commit=True) as cursor:
            # Idempotency Check using pidx as transaction_code
            cursor.execute("SELECT order_id FROM orders WHERE transaction_code = %s", (pidx,))
            existing = cursor.fetchone()
            if existing:
                return render_template('payment-success.html', order_id=existing['order_id'])

            # 1. Get cart items from DB
            query = """
                SELECT ci.product_id, ci.quantity, p.price, ci.cart_item_id
                FROM cart_items ci
                JOIN products p ON ci.product_id = p.product_id
                WHERE ci.user_id = %s
            """
            params = [user_id]
            
            if selected_ids:
                placeholders = ','.join(['%s'] * len(selected_ids))
                query += f" AND ci.cart_item_id IN ({placeholders})"
                params.extend(selected_ids)
                
            cursor.execute(query, params)
            cart_items = cursor.fetchall()
            
            if not cart_items:
                # Already processed or empty
                return render_template('payment-success.html')
                
            total_amount = sum((item['price'] or 0) * item['quantity'] for item in cart_items)
            
            # 2. Create Order (transaction_code stores Khalti pidx)
            cursor.execute("""
                INSERT INTO orders 
                (user_id, order_type, payment_type, payment_status, total_amount, transaction_code, order_status, created_at)
                VALUES (%s, 'Online', 'Pay Online', 'Paid', %s, %s, 'processing', NOW())
            """, (user_id, total_amount, pidx))
            
            order_id = cursor.lastrowid
            
            # 3. Create Order Items and Deduct Stock
            for item in cart_items:
                product_id = item['product_id']
                qty = item['quantity']
                
                # Check stock availability again before final deduction
                cursor.execute("SELECT name, stock_quantity FROM products WHERE product_id = %s FOR UPDATE", (product_id,))
                product = cursor.fetchone()
                
                if not product or product['stock_quantity'] < qty:
                    raise Exception(f"Insufficient stock for {product['name'] if product else 'Product ID ' + str(product_id)}")

                # Subtract Stock immediately on purchase/processing 
                cursor.execute("""
                    UPDATE products 
                    SET stock_quantity = stock_quantity - %s 
                    WHERE product_id = %s
                """, (qty, product_id))
                
                # Insert order item
                cursor.execute("""
                    INSERT INTO order_items (order_id, product_id, quantity, price_at_order)
                    VALUES (%s, %s, %s, %s)
                """, (order_id, product_id, qty, item['price']))
                
            # 4. Clear Cart (only selected items)
            if selected_ids:
                placeholders = ','.join(['%s'] * len(selected_ids))
                cursor.execute(f"DELETE FROM cart_items WHERE user_id = %s AND cart_item_id IN ({placeholders})", [user_id] + selected_ids)
            else:
                cursor.execute("DELETE FROM cart_items WHERE user_id = %s", (user_id,))
            
            print(f"SUCCESS: Order {order_id} created successfully for user {user_id} via Khalti (pidx: {pidx})")
            
        return render_template('payment-success.html', order_id=order_id)
        
    except Exception as e:
        print(f"Order creation error: {e}")
        flash('Payment successful but error creating order. Please contact support.', 'warning')
        return redirect(url_for('main.index'))

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
            SELECT 
                user_id,
                first_name,
                last_name,
                email,
                phone,
                role,
                province,
                district,
                address
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
        province = request.form.get('province', '').strip()
        district = request.form.get('district', '').strip()
        address = request.form.get('address', '').strip()
        
        # Check if this is an AJAX request
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        # Basic validation
        if not all([first_name, last_name, email, phone]):
            error_msg = 'All required fields must be filled out.'
            if is_ajax:
                return jsonify({'status': 'error', 'message': error_msg}), 400
            flash(error_msg, 'error')
            return redirect(url_for('main.customer_profile', edit='true'))
            
        # Name validation - no numbers allowed
        if any(char.isdigit() for char in first_name) or any(char.isdigit() for char in last_name):
            error_msg = 'Name fields cannot contain numbers.'
            if is_ajax:
                return jsonify({'status': 'error', 'message': error_msg}), 400
            flash(error_msg, 'error')
            return redirect(url_for('main.customer_profile', edit='true'))
            
        # Name length validation
        if len(first_name) < 2 or len(last_name) < 2:
            error_msg = 'Name fields must be at least 2 characters long.'
            if is_ajax:
                return jsonify({'status': 'error', 'message': error_msg}), 400
            flash(error_msg, 'error')
            return redirect(url_for('main.customer_profile', edit='true'))
        
        # Enhanced email validation with strict domain checking
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(\.[a-zA-Z]{2,})?$'
        if not re.match(email_pattern, email):
            error_msg = 'Please enter a valid email address (e.g., example@gmail.com).'
            if is_ajax:
                return jsonify({'status': 'error', 'message': error_msg}), 400
            flash(error_msg, 'error')
            return redirect(url_for('main.customer_profile', edit='true'))
        
        # Get domain part for additional validation
        domain = email.split('@')[-1].lower()
        
        # Special handling for Gmail addresses
        if 'gmail' in domain:
            if not domain == 'gmail.com':
                error_msg = 'Gmail addresses must use @gmail.com domain.'
                if is_ajax:
                    return jsonify({'status': 'error', 'message': error_msg}), 400
                flash(error_msg, 'error')
                return redirect(url_for('main.customer_profile', edit='true'))
        # General domain validation for other email providers
        elif '.' not in domain or len(domain.split('.')[-1]) < 2:
            error_msg = 'Please enter a valid email domain (e.g., example.com).'
            if is_ajax:
                return jsonify({'status': 'error', 'message': error_msg}), 400
            flash(error_msg, 'error')
            return redirect(url_for('main.customer_profile', edit='true'))
        
        # Phone number validation
        if not re.match(r'^\d{10}$', phone):
            error_msg = 'Please enter a valid 10-digit phone number (digits only).'
            if is_ajax:
                return jsonify({'status': 'error', 'message': error_msg}), 400
            flash(error_msg, 'error')
            return redirect(url_for('main.customer_profile', edit='true'))

        # Province/District length validation
        for field_value, field_name in [(province, 'Province'), (district, 'District')]:
            if field_value and len(field_value) > 50:
                error_msg = f'{field_name} must be 50 characters or fewer.'
                if is_ajax:
                    return jsonify({'status': 'error', 'message': error_msg}), 400
                flash(error_msg, 'error')
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
                    phone = %s,
                    province = %s,
                    district = %s,
                    address = %s
                WHERE user_id = %s
                """,
                (first_name, last_name, email, phone, province or None, district or None, address or None, user_id)
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
            error_msg = f'Database error: {str(e)}'
            if is_ajax:
                return jsonify({'status': 'error', 'message': error_msg}), 500
            flash(error_msg, 'error')
            return redirect(url_for('main.customer_profile', edit='true'))
            
        finally:
            if cursor:
                cursor.close()
        
        return redirect(url_for('main.customer_profile'))
        
    except Exception as e:
        print(f"Unexpected error in update_profile: {str(e)}")
        error_msg = 'An unexpected error occurred. Please try again later.'
        if request.is_json or (request.headers.get('X-Requested-With') == 'XMLHttpRequest'):
            return jsonify({'status': 'error', 'message': error_msg}), 500
        flash(error_msg, 'error')
        return redirect(url_for('main.customer_profile', edit='true'))

@main_bp.route('/customer-history')
def customer_history():
    return render_template('customer-history.html')

# ===== Supplier Management =====
@main_bp.route('/suppliers')
def suppliers():
    # Check if user is logged in and has proper permissions
    if 'user_id' not in session or session.get('role') not in ['Admin', 'Staff']:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('main.index'))
    
    # Ensure database connection is available
    active_conn = check_connection()
    if active_conn is None:
        flash('Database connection error. Please try again.', 'danger')
        return redirect(url_for('main.index'))
    
    cursor = active_conn.cursor(dictionary=True)
    try:
        # Get supplier statistics
        cursor.execute("SELECT COUNT(*) as total FROM suppliers")
        stats = cursor.fetchone()
        
        # Get all suppliers with purchase history
        cursor.execute("""
            SELECT 
                s.supplier_id,
                s.name as supplier_name,
                s.contact_person,
                s.email as contact_email,
                s.phone as contact_phone,
                s.address,
                s.pan_number,
                s.vat_number,
                COUNT(p.product_id) as product_count,
                (SELECT COUNT(*) FROM stock_history sh WHERE sh.supplier_id = s.supplier_id) as total_orders,
                (SELECT SUM(sh.quantity_received * sh.purchase_price) FROM stock_history sh WHERE sh.supplier_id = s.supplier_id) as total_value,
                (SELECT COUNT(DISTINCT sh.product_id) FROM stock_history sh WHERE sh.supplier_id = s.supplier_id AND sh.received_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)) as active_orders
            FROM suppliers s
            LEFT JOIN products p ON s.supplier_id = p.supplier_id
            GROUP BY s.supplier_id
            ORDER BY total_orders DESC, total_value DESC, s.name ASC
        """)
        suppliers_list = cursor.fetchall()
        
        # Get purchase history for each supplier
        for supplier in suppliers_list:
            cursor.execute("""
                SELECT 
                    p.name as product_name,
                    sh.quantity_received,
                    sh.purchase_price,
                    sh.received_at
                FROM stock_history sh
                JOIN products p ON sh.product_id = p.product_id
                WHERE sh.supplier_id = %s
                ORDER BY sh.received_at DESC
                LIMIT 5
            """, (supplier['supplier_id'],))
            supplier['purchase_history'] = cursor.fetchall()
        
        return render_template('suppliers.html', 
                             suppliers=suppliers_list,
                             total_orders=sum(s['total_orders'] or 0 for s in suppliers_list),
                             total_value=sum(s['total_value'] or 0 for s in suppliers_list),
                             active_suppliers=len([s for s in suppliers_list if s['active_orders'] > 0]))
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in suppliers route: {str(e)}\n{error_details}")
        flash(f'Error loading suppliers: {str(e)}', 'danger')
        return render_template('suppliers.html', suppliers=[], total_orders=0, total_value=0, active_suppliers=0)
    finally:
        cursor.close()

@main_bp.route('/suppliers/add', methods=['POST'])
def add_supplier():
    # Check if user is logged in and has proper permissions
    if 'user_id' not in session or session.get('role') not in ['Admin', 'Staff']:
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    try:
        data = request.get_json() if request.is_json else request.form
        
        # Validate required fields
        if not data.get('supplier_name'):
            return jsonify({'success': False, 'message': 'Supplier name is required'})
        
        cursor = conn.cursor()
        
        # Check if supplier already exists
        cursor.execute("SELECT supplier_id FROM suppliers WHERE name = %s", (data['supplier_name'],))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': 'Supplier with this name already exists'})
        
        # Insert new supplier
        cursor.execute("""
            INSERT INTO suppliers (name, contact_person, email, phone, address)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            data['supplier_name'],
            data.get('contact_person', ''),
            data.get('contact_email', ''),
            data.get('contact_phone', ''),
            data.get('address', '')
        ))
        
        conn.commit()
        cursor.close()
        
        return jsonify({'success': True, 'message': 'Supplier added successfully'})
        
    except Exception as e:
        if 'cursor' in locals():
            cursor.close()
        import traceback
        error_details = traceback.format_exc()
        print(f"Error adding supplier: {str(e)}\n{error_details}")
        return jsonify({'success': False, 'message': f'Error adding supplier: {str(e)}'})

@main_bp.route('/suppliers/<int:supplier_id>/delete', methods=['POST'])
def delete_supplier(supplier_id):
    # Check if user is logged in and has proper permissions
    if 'user_id' not in session or session.get('role') not in ['Admin', 'Staff']:
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Check if supplier exists
        cursor.execute("SELECT name FROM suppliers WHERE supplier_id = %s", (supplier_id,))
        supplier = cursor.fetchone()
        if not supplier:
            return jsonify({'success': False, 'message': 'Supplier not found'})
        
        # Check for linked products
        cursor.execute("SELECT COUNT(*) as product_count FROM products WHERE supplier_id = %s", (supplier_id,))
        product_check = cursor.fetchone()
        
        if product_check['product_count'] > 0:
            # Get product names for error message
            cursor.execute("SELECT name FROM products WHERE supplier_id = %s LIMIT 5", (supplier_id,))
            products = cursor.fetchall()
            product_names = [p['name'] for p in products]
            
            return jsonify({
                'success': False, 
                'message': f'Cannot delete supplier. {product_check["product_count"]} products are linked to this supplier.',
                'products': product_names,
                'has_products': True
            })
        
        # Delete the supplier
        cursor.execute("DELETE FROM suppliers WHERE supplier_id = %s", (supplier_id,))
        conn.commit()
        cursor.close()
        
        return jsonify({'success': True, 'message': f'Supplier "{supplier["name"]}" deleted successfully'})
        
    except Exception as e:
        if 'cursor' in locals():
            cursor.close()
        import traceback
        error_details = traceback.format_exc()
        print(f"Error deleting supplier: {str(e)}\n{error_details}")
        return jsonify({'success': False, 'message': f'Error deleting supplier: {str(e)}'})

@main_bp.route('/suppliers/data')
def get_suppliers_data():
    # Check if user is logged in and has proper permissions
    if 'user_id' not in session or session.get('role') not in ['Admin', 'Staff']:
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Get all suppliers with statistics
        cursor.execute("""
            SELECT 
                s.supplier_id,
                s.name as supplier_name,
                s.contact_person,
                s.email as contact_email,
                s.phone as contact_phone,
                s.address,
                s.pan_number,
                s.vat_number,
                COUNT(p.product_id) as product_count,
                (SELECT COUNT(*) FROM stock_history sh WHERE sh.supplier_id = s.supplier_id) as total_orders,
                (SELECT SUM(sh.quantity_received * sh.purchase_price) FROM stock_history sh WHERE sh.supplier_id = s.supplier_id) as total_value,
                (SELECT COUNT(DISTINCT sh.product_id) FROM stock_history sh WHERE sh.supplier_id = s.supplier_id AND sh.received_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)) as active_orders
            FROM suppliers s
            LEFT JOIN products p ON s.supplier_id = p.supplier_id
            GROUP BY s.supplier_id
            ORDER BY s.name
        """)
        suppliers_list = cursor.fetchall()
        
        # Get purchase history for each supplier
        for supplier in suppliers_list:
            cursor.execute("""
                SELECT 
                    p.name as product_name,
                    sh.quantity_received,
                    sh.purchase_price,
                    sh.received_at
                FROM stock_history sh
                JOIN products p ON sh.product_id = p.product_id
                WHERE sh.supplier_id = %s
                ORDER BY sh.received_at DESC
                LIMIT 5
            """, (supplier['supplier_id'],))
            supplier['purchase_history'] = cursor.fetchall()
        
        cursor.close()
        
        return jsonify({'success': True, 'suppliers': suppliers_list})
        
    except Exception as e:
        if 'cursor' in locals():
            cursor.close()
        import traceback
        error_details = traceback.format_exc()
        print(f"Error fetching suppliers data: {str(e)}\n{error_details}")
        return jsonify({'success': False, 'message': f'Error fetching suppliers: {str(e)}'})

@main_bp.route('/api/supplier/<int:supplier_id>/history')
def get_supplier_history(supplier_id):
    # Check if user is logged in and has proper permissions
    if session.get('role') not in ['Admin', 'Staff']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        with get_db_context() as cursor:
            # Enhanced query with more details
            query = """
                SELECT 
                    sh.history_id,
                    sh.received_at, 
                    p.name as product_name,
                    p.sku,
                    c.name as category_name,
                    sh.quantity_received, 
                    sh.purchase_price,
                    (sh.quantity_received * sh.purchase_price) as total_investment,
                    p.unit_type
                FROM stock_history sh
                JOIN products p ON sh.product_id = p.product_id
                JOIN categories c ON p.category_id = c.category_id
                WHERE sh.supplier_id = %s
                ORDER BY sh.received_at DESC
            """
            cursor.execute(query, (supplier_id,))
            history = cursor.fetchall()

            # Calculate summary statistics
            total_spent = sum(item['total_investment'] for item in history)
            total_orders = len(history)
            unique_products = len(set(item['product_name'] for item in history))

        return jsonify({
            'success': True,
            'history': history,
            'summary': {
                'total_spent': float(total_spent),
                'total_orders': total_orders,
                'unique_products': unique_products
            }
        })
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error fetching supplier history: {str(e)}\n{error_details}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ===== Supplier Export API =====
@main_bp.route('/api/export/suppliers', methods=['POST'])
def export_suppliers_report():
    # Check if user is logged in and has proper permissions
    if 'user_id' not in session or session.get('role') not in ['Admin', 'Staff']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        # Parse request data
        data = request.get_json()
        scope = data.get('scope', 'all')
        date_range = data.get('date_range', '30days')
        detail_level = data.get('detail_level', 'summary')
        supplier_id = data.get('supplier_id')

        with get_db_context() as cursor:
            # Calculate date filter
            date_filter = ""
            if date_range == '7days':
                date_filter = "AND sh.received_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
            elif date_range == '30days':
                date_filter = "AND sh.received_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)"
            elif date_range == '90days':
                date_filter = "AND sh.received_at >= DATE_SUB(NOW(), INTERVAL 90 DAY)"
            # 'all' means no date filter

            # Build WHERE clause
            where_clause = "WHERE 1=1"
            if scope == 'specific' and supplier_id:
                where_clause += f" AND s.supplier_id = {supplier_id}"
            
            where_clause += " " + date_filter

            # Query based on summary mode only
            # Summary mode - aggregate data per supplier
            query = f"""
                SELECT 
                    s.supplier_id,
                    s.name as supplier_name,
                    s.contact_person,
                    COUNT(DISTINCT sh.history_id) as total_records,
                    COALESCE(SUM(sh.quantity_received), 0) as total_quantity,
                    COALESCE(SUM(sh.quantity_received * sh.purchase_price), 0) as total_investment,
                    COUNT(DISTINCT sh.product_id) as unique_products,
                    MAX(sh.received_at) as last_supply_date
                FROM suppliers s
                LEFT JOIN stock_history sh ON s.supplier_id = sh.supplier_id
                {where_clause}
                GROUP BY s.supplier_id, s.name, s.contact_person
                ORDER BY s.name
            """

            cursor.execute(query)
            results = cursor.fetchall()

            # Calculate summary statistics
            summary = {
                'total_suppliers': len(set(r['supplier_id'] for r in results)) if results else 0,
                'total_records': len(results),
                'total_quantity': sum(r.get('total_quantity', 0) if 'total_quantity' in r else r.get('quantity_received', 0) for r in results),
                'total_investment': sum(r.get('total_investment', 0) if 'total_investment' in r else r.get('total_cost', 0) for r in results)
            }

            # Prepare response
            response_data = {
                'success': True,
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'filters': {
                    'scope': scope,
                    'date_range': date_range,
                    'detail_level': detail_level,
                    'supplier_id': supplier_id
                },
                'summary': summary,
                'rows': results
            }

            return jsonify(response_data)

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error generating supplier report: {str(e)}\n{error_details}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
    # Check if user is logged in
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    user_role = session.get('role')
    user_id = session.get('user_id')
    
    if not user_id or user_role not in ['Admin', 'Staff']:
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
        
        # For Admin, validate all fields. For Staff, we only care about status.
        if user_role != 'Staff':
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
            
        try:
            task_id_int = int(task_id)
        except (TypeError, ValueError):
            return respond_error('Invalid task ID')
        
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
            
            # Staff Permission Logic
            if user_role == 'Staff':
                if current_assigned_to != user_id:
                    if is_ajax:
                        return jsonify({'success': False, 'message': 'You can only update tasks assigned to you'}), 403
                    flash('You can only update tasks assigned to you', 'danger')
                    return redirect(url_for('main.task'))

                # Force other fields to remain unchanged from DB
                title = current_title
                description = current_description
                category = current_category
                priority = current_priority
                parsed_date = current_due_date
                assigned_to_id = current_assigned_to
                
                # Update due_date string for comparison
                due_date = current_due_date.strftime('%Y-%m-%d') if current_due_date else None
                assigned_to = str(assigned_to_id)
            else:
                # Admin logic
                try:
                    assigned_to_id = int(assigned_to)
                except (TypeError, ValueError):
                    return respond_error('Invalid staff selection')
                
                from datetime import datetime
                try:
                    parsed_date = datetime.strptime(due_date, '%Y-%m-%d').date()
                except ValueError:
                    return respond_error('Invalid due date format')

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
                SELECT sr.request_id, sr.product_id, p.name, sr.status, sr.requested_quantity, sr.supplier_id, p.price
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
                
            if new_status == 'Approved':
                product_id = stock_request[1]
                qty = stock_request[4]
                supplier_id = stock_request[5]
                price = stock_request[6]
                
                # Update product stock
                cursor.execute("""
                    UPDATE products 
                    SET stock_quantity = stock_quantity + %s
                    WHERE product_id = %s
                """, (qty, product_id))
                
                # Add to stock history if supplier is known
                if supplier_id:
                    cursor.execute("""
                        INSERT INTO stock_history (product_id, supplier_id, quantity_received, purchase_price)
                        VALUES (%s, %s, %s, %s)
                    """, (product_id, supplier_id, qty, price))
            
            # Commit the transaction
            conn.commit()
            
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
            
            # Update the status and handle stock updates if approving
            if new_status == 'Approved':
                # Set purchase_price to 0.00 for admin to update later
                cursor.execute("""
                    UPDATE new_arrival_alerts 
                    SET status = %s, purchase_price = COALESCE(purchase_price, 0.00)
                    WHERE arrival_id = %s
                """, (new_status, arrival_id))
                
                # Get arrival details for stock update
                cursor.execute("""
                    SELECT product_id, supplier_id, quantity_received, purchase_price 
                    FROM new_arrival_alerts 
                    WHERE arrival_id = %s
                """, (arrival_id,))
                arrival_details = cursor.fetchone()
                
                if arrival_details:
                    product_id, supplier_id, quantity_received, purchase_price = arrival_details
                    
                    # Update product stock
                    cursor.execute("""
                        UPDATE products 
                        SET stock_quantity = stock_quantity + %s
                        WHERE product_id = %s
                    """, (quantity_received, product_id))
                    
                    # Add to stock history
                    cursor.execute("""
                        INSERT INTO stock_history (product_id, supplier_id, quantity_received, purchase_price)
                        VALUES (%s, %s, %s, %s)
                    """, (product_id, supplier_id, quantity_received, purchase_price))
            else:
                # Just update status for rejected
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
            
            # Commit all database changes (status, stock, and history)
            conn.commit()
            
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

# ===== Export API Routes =====

@main_bp.route('/api/export/users')
def export_users():
    """Export users data filtered by role type"""
    if 'user_id' not in session or session.get('role') != 'Admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    report_type = request.args.get('type', 'all')  # 'customer', 'staff', 'all'
    
    try:
        with get_db_context() as cursor:
            if report_type == 'customer':
                role_filter = "WHERE u.role = 'Customer'"
            elif report_type == 'staff':
                role_filter = "WHERE u.role = 'Staff'"
            else:
                role_filter = "WHERE u.role IN ('Customer', 'Staff')"
            
            cursor.execute(f"""
                SELECT 
                    u.user_id,
                    u.first_name,
                    u.last_name,
                    u.email,
                    u.phone,
                    u.role,
                    u.province,
                    u.district,
                    u.created_at,
                    COUNT(DISTINCT CASE WHEN u.role = 'Customer' THEN o.order_id END) as total_orders,
                    COALESCE(SUM(CASE WHEN u.role = 'Customer' THEN o.total_amount END), 0) as total_spent,
                    COUNT(DISTINCT CASE WHEN u.role = 'Staff' AND o.order_status = 'completed' THEN o.order_id END) as orders_sold,
                    MAX(CASE WHEN u.role = 'Customer' THEN o.created_at END) as last_order_date
                FROM users u
                LEFT JOIN orders o ON u.user_id = o.user_id
                {role_filter}
                GROUP BY u.user_id
                ORDER BY 
                    CASE 
                        WHEN u.role = 'Staff' THEN 1
                        WHEN u.role = 'Customer' THEN 2
                    END,
                    CASE 
                        WHEN u.role = 'Staff' THEN COUNT(DISTINCT CASE WHEN u.role = 'Staff' AND o.order_status = 'completed' THEN o.order_id END)
                        WHEN u.role = 'Customer' THEN COUNT(DISTINCT CASE WHEN u.role = 'Customer' THEN o.order_id END)
                        ELSE 0
                    END DESC,
                    CASE 
                        WHEN u.role = 'Customer' THEN MAX(CASE WHEN u.role = 'Customer' THEN o.created_at END)
                        ELSE NULL
                    END DESC,
                    u.first_name
            """)
            users_data = cursor.fetchall()
            
            # Summary stats
            cursor.execute(f"""
                SELECT role, COUNT(*) as count
                FROM users u
                {role_filter}
                GROUP BY role
            """)
            role_counts = cursor.fetchall()
            
            return jsonify({
                'success': True,
                'report_type': report_type,
                'users': users_data,
                'summary': role_counts,
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
    except Exception as e:
        print(f"Export users error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@main_bp.route('/api/export/stock')
def export_stock():
    """Export stock/inventory data"""
    if 'user_id' not in session or session.get('role') not in ['Admin', 'Staff']:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    stock_filter = request.args.get('filter', 'all')  # 'all', 'low', 'out', 'category'
    category_id = request.args.get('category_id', '')
    
    try:
        with get_db_context() as cursor:
            where_clauses = []
            params = []
            
            if stock_filter == 'low':
                where_clauses.append("p.stock_quantity > 0 AND p.stock_quantity <= 10")
            elif stock_filter == 'out':
                where_clauses.append("p.stock_quantity = 0")
            elif stock_filter == 'in_stock':
                where_clauses.append("p.stock_quantity > 10")
            
            if category_id:
                where_clauses.append("p.category_id = %s")
                params.append(category_id)
            
            where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            
            cursor.execute(f"""
                SELECT 
                    p.product_id,
                    p.name,
                    p.sku,
                    p.brand,
                    p.price,
                    p.stock_quantity,
                    p.status,
                    c.name as category_name,
                    s.name as supplier_name,
                    CASE 
                        WHEN p.stock_quantity = 0 THEN 'Out of Stock'
                        WHEN p.stock_quantity <= 10 THEN 'Low Stock'
                        ELSE 'In Stock'
                    END as stock_status
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.category_id
                LEFT JOIN suppliers s ON p.supplier_id = s.supplier_id
                {where_clause}
                ORDER BY p.stock_quantity DESC
            """, params)
            products = cursor.fetchall()
            
            # Summary
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_products,
                    SUM(CASE WHEN stock_quantity = 0 THEN 1 ELSE 0 END) as out_of_stock,
                    SUM(CASE WHEN stock_quantity > 0 AND stock_quantity <= 10 THEN 1 ELSE 0 END) as low_stock,
                    SUM(CASE WHEN stock_quantity > 10 THEN 1 ELSE 0 END) as in_stock,
                    COALESCE(SUM(stock_quantity * price), 0) as total_value
                FROM products
            """)
            summary = cursor.fetchone()
            
            return jsonify({
                'success': True,
                'filter': stock_filter,
                'products': products,
                'summary': summary,
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
    except Exception as e:
        print(f"Export stock error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@main_bp.route('/api/export/sales')
def export_sales():
    """Export sales data"""
    if 'user_id' not in session or session.get('role') not in ['Admin', 'Staff']:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    period = request.args.get('period', 'month')  # 'week', 'month', 'year', 'all'
    
    try:
        with get_db_context() as cursor:
            if period == 'week':
                date_filter = "AND o.created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
            elif period == 'month':
                date_filter = "AND o.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)"
            elif period == '3month':
                date_filter = "AND o.created_at >= DATE_SUB(NOW(), INTERVAL 90 DAY)"
            elif period == 'year':
                date_filter = "AND o.created_at >= DATE_SUB(NOW(), INTERVAL 1 YEAR)"
            else:
                date_filter = ""
            
            cursor.execute(f"""
                SELECT 
                    o.order_id,
                    CONCAT(u.first_name, ' ', u.last_name) as customer_name,
                    o.order_type,
                    o.payment_type,
                    o.total_amount,
                    o.order_status,
                    o.payment_status,
                    o.created_at
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.user_id
                WHERE o.order_status IN ('completed', 'Completed')
                {date_filter}
                ORDER BY o.created_at DESC
                LIMIT 500
            """)
            sales = cursor.fetchall()
            
            cursor.execute(f"""
                SELECT 
                    COUNT(*) as total_orders,
                    COALESCE(SUM(total_amount), 0) as total_revenue,
                    COALESCE(AVG(total_amount), 0) as avg_order_value
                FROM orders
                WHERE order_status IN ('completed', 'Completed')
                {date_filter}
            """)
            summary = cursor.fetchone()
            
            return jsonify({
                'success': True,
                'period': period,
                'sales': sales,
                'summary': summary,
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
    except Exception as e:
        print(f"Export sales error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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

# Duplicate route removed to fix startup error
# @main_bp.route('/pos/checkout', methods=['POST'])
def pos_checkout_legacy_unused():
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

# ===== User Management Routes =====
@main_bp.route('/users/get/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """Get user data including address"""
    # Check if user is logged in and is an admin
    if 'user_id' not in session or session.get('role') != 'Admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    try:
        # Use dictionary cursor for proper JSON serialization
        with check_connection().cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT user_id, first_name, last_name, email, phone, citizen_id, province, district, address, role
                FROM users WHERE user_id = %s
            """, (user_id,))
            user = cursor.fetchone()
            
            if not user:
                return jsonify({'success': False, 'error': 'User not found'}), 404
            
            return jsonify({'success': True, 'user': user})
            
    except Exception as e:
        print(f"Error fetching user data: {e}")
        return jsonify({'success': False, 'error': 'An error occurred while fetching user data'}), 500

@main_bp.route('/users/update', methods=['POST'])
def update_user():
    """Update user information"""
    # Check if user is logged in and is an admin
    if 'user_id' not in session or session.get('role') != 'Admin':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    try:
        # Get form data
        user_id = request.form.get('user_id')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        role = request.form.get('role')
        phone = request.form.get('phone')
        citizen_id = request.form.get('citizen_id')
        province = request.form.get('province')
        district = request.form.get('district')
        address = request.form.get('address')
        
        # Validate input
        if not all([user_id, first_name, last_name, email, role]):
            return jsonify({'success': False, 'error': 'All required fields are required'}), 400
        
        # Check if user exists
        with get_cursor() as cursor:
            cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
            if not cursor.fetchone():
                return jsonify({'success': False, 'error': 'User not found'}), 404
            
            # Check for duplicate email (excluding current user)
            cursor.execute("SELECT user_id FROM users WHERE email = %s AND user_id != %s", (email, user_id))
            if cursor.fetchone():
                return jsonify({'success': False, 'error': 'Email already exists'}), 400
            
            # Update user including address fields and citizen_id
            cursor.execute("""
                UPDATE users 
                SET first_name = %s, last_name = %s, email = %s, role = %s, phone = %s, citizen_id = %s,
                    province = %s, district = %s, address = %s
                WHERE user_id = %s
            """, (first_name, last_name, email, role, phone, citizen_id, province, district, address, user_id))
            
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'error': 'Failed to update user'}), 500
            
            conn.commit()
            
        return jsonify({
            'success': True, 
            'message': f'User {first_name} {last_name} updated successfully!'
        })
        
    except Exception as e:
        print(f"Error updating user: {e}")
        return jsonify({'success': False, 'error': 'An error occurred while updating user'}), 500

@main_bp.app_errorhandler(404)
def page_not_found(e):
    return render_template('base.html', error_message='Page not found'), 404
