from flask import Blueprint, render_template, request, jsonify, json, session, flash, redirect, url_for
from flask_login import login_required, current_user
from config import conn  # Use the existing connection
from werkzeug.utils import secure_filename
import os
import time

def format_product(product):
    """Helper function to format product data"""
    # Handle image URL
    if 'image_url' not in product or not product['image_url']:
        product['image_url'] = 'static/images/placeholder-product.png'
    elif not any(product['image_url'].startswith(prefix) for prefix in ['http://', 'https://', '/static/', 'static/']):
        product['image_url'] = f"static/images/{product['image_url'].lstrip('/')}"
    
    return product

products_bp = Blueprint('products', __name__)

def get_db_connection():
    # Return a new connection using the same parameters as in config.py
    return conn

def get_staff_task_stats(user_id):
    """Get task statistics for a staff member"""
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Get task statistics for the user
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'in-progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
            FROM tasks
            WHERE assigned_to = %s
        """, (user_id,))
        
        stats = cursor.fetchone()
        cursor.close()
        return stats
        
    except Exception as e:
        print(f"Error fetching staff task stats: {e}")
        return {
            'total': 0,
            'pending': 0,
            'in_progress': 0,
            'completed': 0
        }

def get_staff_tasks(user_id):
    """Get all tasks for a staff member"""
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        
        # Get user's tasks
        cursor.execute("""
            SELECT * 
            FROM tasks 
            WHERE assigned_to = %s 
            ORDER BY 
                CASE 
                    WHEN status = 'pending' THEN 1
                    WHEN status = 'in-progress' THEN 2
                    ELSE 3
                END,
                due_date ASC,
                CASE priority
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    ELSE 3
                END
        """, (user_id,))
        
        tasks = cursor.fetchall()
        cursor.close()
        return tasks
        
    except Exception as e:
        print(f"Error fetching staff tasks: {e}")
        return []

@products_bp.route('/')
def index():
    """Render the main products page"""
    return render_products()

@products_bp.route('/products')
def products():
    """Handle both HTML and JSON requests for products"""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return get_products_json()
    return render_products()

def render_products():
    """Render the products page with initial data"""
    try:
        # Get initial products (increased limit)
        products_data = get_products_data(limit=50, include_inactive=False)
        
        # Get categories for filter
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT c.name, COUNT(p.product_id) as product_count 
            FROM categories c
            LEFT JOIN products p ON c.category_id = p.category_id
            GROUP BY c.name 
            ORDER BY c.name
        """)
        categories = [{
            'name': row['name'],
            'count': row['product_count']
        } for row in cursor.fetchall()]
        
        return render_template('products.html', 
                             products=products_data['products'], 
                             categories=categories,
                             total_products=products_data['total'],
                             is_guest=('user_id' not in session))
    except Exception as e:
        print(f"Error in render_products: {str(e)}")
        return render_template('products.html', 
                            products=[], 
                            categories=[],
                            total_products=0,
                            is_guest=True)

def get_products_data(category='', limit=None, offset=0, include_inactive=False):
    """Helper function to get products data with filters"""
    try:
        # Build the base query
        query = """
            SELECT SQL_CALC_FOUND_ROWS 
                   p.*, c.name as category_name 
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.category_id
            WHERE 1=1
        """
        
        params = []
        
        # Add status filter (default to active products only)
        if not include_inactive:
            query += " AND p.status = 'active'"
        
        # Add filters
        if category:
            query += " AND c.name = %s"
            params.append(category)
        
        # Add pagination
        if limit is not None:
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])
        
        # Execute query
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params)
        products = cursor.fetchall()
        
        # Get total count
        cursor.execute("SELECT FOUND_ROWS() as total")
        total = cursor.fetchone()['total']
        
        # Process products
        for product in products:
            format_product(product)
        
        return {
            'products': products,
            'total': total
        }
        
    except Exception as e:
        print(f"Error in get_products_data: {str(e)}")
        return {'products': [], 'total': 0}
    finally:
        if 'cursor' in locals():
            cursor.close()

def get_products_json():
    """Handle AJAX requests for products with filters"""
    try:
        # Get filter parameters
        category = request.args.get('category', '')
        limit = request.args.get('limit', 12, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Get filtered products
        data = get_products_data(category, limit, offset, include_inactive=False)
        
        # Return JSON response
        return jsonify({
            'success': True,
            'products': data['products'],
            'total': data['total']
        })
    except Exception as e:
        print(f"Error in get_products_json: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error loading products'
        }), 500

@products_bp.route('/api/products/<int:product_id>')
def get_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = """
        SELECT p.*, c.name as category_name 
        FROM products p
        JOIN categories c ON p.category_id = c.category_id
        WHERE p.product_id = %s
    """
    
    cursor.execute(query, (product_id,))
    product = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if product:
        return jsonify(product)
    return jsonify({"error": "Product not found"}), 404


@products_bp.route('/edit', methods=['POST'])
def update_product():
    """Handle product updates from the edit modal."""
    role = session.get('role')
    if role not in ('Admin', 'Staff'):
        flash('You are not authorized to edit products.', 'danger')
        return redirect(url_for('main.stock'))

    product_id = request.form.get('product_id')
    if not product_id:
        flash('Product ID is required.', 'danger')
        return redirect(url_for('main.stock'))

    name = request.form.get('name', '').strip()
    category_id = request.form.get('category_id')
    supplier_id = request.form.get('supplier_id', '').strip()
    price = request.form.get('price', 0)
    stock_quantity = request.form.get('stock_quantity', 0)
    unit_type = request.form.get('unit_type', 'piece')
    units_per_pack = request.form.get('units_per_pack') or 1
    status = request.form.get('status', 'active')
    brand = request.form.get('brand', '').strip()
    sku = request.form.get('sku', '').strip()

    if not name or not category_id or not supplier_id:
        flash('Name, category, and supplier are required.', 'danger')
        return redirect(url_for('main.stock'))

    try:
        price = float(price)
        stock_quantity = int(stock_quantity)
        units_per_pack = int(units_per_pack)
    except (TypeError, ValueError):
        flash('Invalid numeric values provided.', 'danger')
        return redirect(url_for('main.stock'))

    # Ensure piece products always use 1 unit per pack
    if unit_type == 'piece':
        units_per_pack = 1

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT image_url FROM products WHERE product_id = %s",
            (product_id,)
        )
        product = cursor.fetchone()
        if not product:
            flash('Product not found.', 'danger')
            return redirect(url_for('main.stock'))

        image_url = product.get('image_url')
        if 'product_image' in request.files:
            file = request.files['product_image']
            if file and file.filename:
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                filename = file.filename.lower()
                if '.' in filename and filename.rsplit('.', 1)[1] in allowed_extensions:
                    secure_name = secure_filename(file.filename)
                    timestamp = str(int(time.time()))
                    name_part, ext_part = secure_name.rsplit('.', 1)
                    final_filename = f"{name_part}_{timestamp}.{ext_part}"
                    upload_path = os.path.join('static', 'images', final_filename)
                    os.makedirs(os.path.dirname(upload_path), exist_ok=True)
                    file.save(upload_path)
                    image_url = f"static/images/{final_filename}"
                else:
                    flash('Invalid image type. Please upload PNG, JPG, JPEG, GIF, or WebP.', 'danger')
                    return redirect(url_for('main.stock'))

        cursor.execute(
            """
            UPDATE products
            SET name = %s,
                category_id = %s,
                supplier_id = %s,
                price = %s,
                stock_quantity = %s,
                unit_type = %s,
                units_per_pack = %s,
                status = %s,
                brand = %s,
                sku = %s,
                image_url = %s
            WHERE product_id = %s
            """,
            (
                name,
                category_id,
                supplier_id,
                price,
                stock_quantity,
                unit_type,
                units_per_pack,
                status,
                brand,
                sku,
                image_url,
                product_id
            )
        )
        conn.commit()
        flash('Product updated successfully!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Failed to update product: {str(e)}', 'danger')
    finally:
        cursor.close()

    return redirect(url_for('main.stock'))


@products_bp.route('/api/customer/orders')
def get_customer_orders():
    """Return the current customer's orders with their line items."""
    user_id = session.get('user_id')
    role = session.get('role')

    if not user_id:
        return jsonify({'success': False, 'message': 'Please log in to view your orders.'}), 401

    if role != 'Customer':
        return jsonify({'success': False, 'message': 'Only customers can view order history.'}), 403

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT 
                o.order_id,
                o.order_status,
                o.total_amount,
                o.created_at,
                o.payment_type,
                o.payment_status,
                o.transaction_code,
                oi.order_item_id,
                oi.quantity,
                oi.price_at_order,
                p.name AS product_name,
                p.image_url
            FROM orders o
            LEFT JOIN order_items oi ON o.order_id = oi.order_id
            LEFT JOIN products p ON oi.product_id = p.product_id
            WHERE o.user_id = %s
            ORDER BY o.created_at DESC, o.order_id DESC, oi.order_item_id ASC
            """,
            (user_id,),
        )

        rows = cursor.fetchall()
    except Exception as e:
        import traceback

        print(f"Error loading orders for user {user_id}: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': 'Failed to load orders.'}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()

    orders_map = {}
    order_counter = 1  # Start with order number 1
    
    for row in rows:
        order_id = row['order_id']
        if order_id not in orders_map:
            created_at = row.get('created_at')
            if hasattr(created_at, 'strftime'):
                created_str = created_at.isoformat()
            else:
                created_str = str(created_at) if created_at is not None else ''

            total_amount = float(row.get('total_amount') or 0)

            orders_map[order_id] = {
                'order_id': order_id,
                'order_number': order_counter,  # Add sequential order number
                'order_status': (row.get('order_status') or '').lower(),
                'total_amount': f"{total_amount:.2f}",
                'created_at': created_str,
                'payment_type': row.get('payment_type'),
                'payment_status': row.get('payment_status'),
                'transaction_code': row.get('transaction_code'),
                'items': [],
                'subtotal': 0.0,
            }
            order_counter += 1  # Increment for next order

        # Attach order items if they exist
        if row.get('order_item_id') is not None:
            price = float(row.get('price_at_order') or 0)
            quantity = row.get('quantity') or 0
            subtotal = price * quantity

            image_url = row.get('image_url') or 'static/images/placeholder-product.png'
            if not any(image_url.startswith(prefix) for prefix in ['http://', 'https://', '/static/', 'static/']):
                image_url = f"static/images/{image_url.lstrip('/') }"

            orders_map[order_id]['items'].append(
                {
                    'order_item_id': row['order_item_id'],
                    'name': row.get('product_name') or 'Product',
                    'quantity': quantity,
                    'price': f"{price:.2f}",
                    'image': image_url,
                    'subtotal': f"{subtotal:.2f}",
                }
            )

            orders_map[order_id]['subtotal'] += subtotal

    orders = []
    for order in orders_map.values():
        if order['subtotal'] == 0 and order['items']:
            order['subtotal'] = sum(float(item['subtotal']) for item in order['items'])
        order['subtotal'] = f"{order['subtotal']:.2f}"
        orders.append(order)

    return jsonify({'success': True, 'orders': orders})

@products_bp.route('/api/products/<int:product_id>/alert', methods=['POST'])
@login_required
def send_product_alert(product_id):
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        quantity = data.get('quantity', 1)
        
        # Validate inputs
        if not message:
            return jsonify({'success': False, 'error': 'Message is required'}), 400
            
        try:
            quantity = int(quantity)
            if quantity < 1:
                return jsonify({'success': False, 'error': 'Quantity must be at least 1'}), 400
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid quantity'}), 400
            
        # Get product details for the alert
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Get product details
            cursor.execute("""
                SELECT p.*, c.name as category_name 
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.category_id
                WHERE p.product_id = %s
            """, (product_id,))
            product = cursor.fetchone()
            
            if not product:
                return jsonify({'success': False, 'error': 'Product not found'}), 404
            
            # Here you can implement the actual alert logic, for example:
            # 1. Save to database
            cursor.execute("""
                INSERT INTO product_alerts 
                (product_id, requested_quantity, message, created_by, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (product_id, quantity, message, current_user.id))
            
            # Commit the transaction
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': 'Alert created successfully',
                'alert': {
                    'product_id': product_id,
                    'requested_quantity': quantity,
                    'message': message
                }
            })
            
        finally:
            cursor.close()
            
    except Exception as e:
        print(f"Error sending alert: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to send alert',
            'details': str(e)
        }), 500

# ===== CART FUNCTIONALITY =====

@products_bp.route('/api/cart/test')
def test_cart_db():
    """Test database connection and cart_items table"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Test cart_items table structure
        cursor.execute("DESCRIBE cart_items")
        table_structure = cursor.fetchall()
        
        # Test if we can select from cart_items
        cursor.execute("SELECT COUNT(*) as count FROM cart_items")
        cart_count = cursor.fetchone()
        
        cursor.close()
        
        return jsonify({
            'success': True,
            'table_structure': table_structure,
            'cart_items_count': cart_count['count']
        })
        
    except Exception as e:
        print(f"Database test error: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@products_bp.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    """Add a product to the cart"""
    try:
        print(f"Cart add request received: {request.json}")  # Debug log
        
        # Check if user is logged in
        if 'user_id' not in session:
            print("User not logged in")  # Debug log
            return jsonify({
                'success': False,
                'message': 'Please log in to add items to cart'
            }), 401
        
        data = request.get_json()
        print(f"Request data: {data}")  # Debug log
        
        product_id = data.get('product_id')
        quantity = data.get('quantity', 1)
        
        print(f"Product ID: {product_id}, Quantity: {quantity}")  # Debug log
        
        if not product_id:
            return jsonify({
                'success': False,
                'message': 'Product ID is required'
            }), 400
        
        try:
            quantity = int(quantity)
            if quantity < 1:
                return jsonify({
                    'success': False,
                    'message': 'Quantity must be at least 1'
                }), 400
        except (ValueError, TypeError) as e:
            print(f"Quantity conversion error: {e}")  # Debug log
            return jsonify({
                'success': False,
                'message': 'Invalid quantity'
            }), 400
        
        user_id = session['user_id']
        print(f"User ID: {user_id}")  # Debug log
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Check if product exists
            cursor.execute("""
            SELECT product_id, name, price, stock_quantity
            FROM products
            WHERE product_id = %s AND status = 'active'
        """, (product_id,))
            product = cursor.fetchone()
            
            print(f"Product found: {product}")  # Debug log
            
            if not product:
                return jsonify({
                    'success': False,
                    'message': 'Product not found'
                }), 404
            
            # Check if item already exists in cart
            cursor.execute("""
                SELECT cart_item_id, quantity
                FROM cart_items
                WHERE user_id = %s AND product_id = %s
            """, (user_id, product_id))
            existing_item = cursor.fetchone()
            
            print(f"Existing cart item: {existing_item}")  # Debug log
            
            if existing_item:
                # Update existing cart item
                new_quantity = existing_item['quantity'] + quantity
                
                cursor.execute("""
                    UPDATE cart_items
                    SET quantity = %s
                    WHERE cart_item_id = %s
                """, (new_quantity, existing_item['cart_item_id']))
                print("Updated existing cart item")  # Debug log
            else:
                # Add new cart item
                cursor.execute("""
                    INSERT INTO cart_items (user_id, product_id, quantity)
                    VALUES (%s, %s, %s)
                """, (user_id, product_id, quantity))
                print("Added new cart item")  # Debug log
            
            conn.commit()
            print("Database commit successful")  # Debug log
            
            cart_count = get_cart_count(user_id)
            print(f"Cart count: {cart_count}")  # Debug log
            
            return jsonify({
                'success': True,
                'message': f'{product["name"]} added to cart',
                'cart_count': cart_count
            })
            
        finally:
            cursor.close()
            
    except Exception as e:
        print(f"Error adding to cart: {str(e)}")  # Debug log
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")  # Debug log
        return jsonify({
            'success': False,
            'message': f'Failed to add item to cart: {str(e)}'
        }), 500

@products_bp.route('/api/cart/update', methods=['POST'])
def update_cart_item():
    """Update cart item quantity"""
    try:
        if 'user_id' not in session:
            return jsonify({
                'success': False,
                'message': 'Please log in to update cart'
            }), 401
        
        data = request.get_json()
        cart_item_id = data.get('cart_item_id')
        quantity = data.get('quantity')
        
        if not cart_item_id or not quantity:
            return jsonify({
                'success': False,
                'message': 'Cart item ID and quantity are required'
            }), 400
        
        try:
            quantity = int(quantity)
            if quantity < 1 or quantity > 999:
                return jsonify({
                    'success': False,
                    'message': 'Quantity must be between 1 and 999'
                }), 400
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'message': 'Invalid quantity'
            }), 400
        
        user_id = session['user_id']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Check if cart item exists and belongs to user
            cursor.execute("""
                SELECT cart_item_id, user_id
                FROM cart_items
                WHERE cart_item_id = %s AND user_id = %s
            """, (cart_item_id, user_id))
            cart_item = cursor.fetchone()
            
            if not cart_item:
                return jsonify({
                    'success': False,
                    'message': 'Cart item not found'
                }), 404
            
            # Update quantity
            cursor.execute("""
                UPDATE cart_items
                SET quantity = %s
                WHERE cart_item_id = %s AND user_id = %s
            """, (quantity, cart_item_id, user_id))
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': 'Cart updated successfully',
                'cart_count': get_cart_count(user_id)
            })
            
        finally:
            cursor.close()
            
    except Exception as e:
        print(f"Error updating cart: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': f'Failed to update cart: {str(e)}'
        }), 500

@products_bp.route('/api/cart/pay-store', methods=['POST'])
def create_store_order():
    """Create an order for 'Pay at Store' payment type"""
    try:
        if 'user_id' not in session:
            return jsonify({
                'success': False,
                'message': 'Please log in to complete your order'
            }), 401
        
        user_id = session['user_id']
        data = request.get_json() or {}
        selected_items = data.get('selected_items', [])
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Build query to get cart items
            if selected_items:
                # Get only selected items
                placeholders = ','.join(['%s'] * len(selected_items))
                cursor.execute(f"""
                    SELECT ci.product_id, ci.quantity, p.name, p.price
                    FROM cart_items ci
                    JOIN products p ON ci.product_id = p.product_id
                    WHERE ci.user_id = %s AND ci.cart_item_id IN ({placeholders})
                """, [user_id] + selected_items)
            else:
                # Get all cart items (backward compatibility)
                cursor.execute("""
                    SELECT ci.product_id, ci.quantity, p.name, p.price
                    FROM cart_items ci
                    JOIN products p ON ci.product_id = p.product_id
                    WHERE ci.user_id = %s
                """, (user_id,))
            
            cart_items = cursor.fetchall()
            
            if not cart_items:
                return jsonify({
                    'success': False,
                    'message': 'No items selected for order'
                }), 400
            
            # Calculate total amount
            total_amount = sum(item['price'] * item['quantity'] for item in cart_items)
            
            # Generate unique transaction code
            import random
            import string
            transaction_code = 'STORE-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            
            # Create the order
            cursor.execute("""
                INSERT INTO orders (
                    user_id, 
                    staff_id, 
                    payment_type, 
                    payment_status, 
                    order_status, 
                    total_amount, 
                    transaction_code
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                None,  # No staff_id for online orders
                'Pay at Store',
                'Unpaid',
                'pending',
                total_amount,
                transaction_code
            ))
            
            order_id = cursor.lastrowid
            
            # Create order items and deduct stock
            stock_update_failed = False
            for item in cart_items:
                # Check if sufficient stock is available
                cursor.execute("""
                    SELECT stock_quantity FROM products 
                    WHERE product_id = %s FOR UPDATE
                """, (item['product_id'],))
                product_stock = cursor.fetchone()
                
                if not product_stock or product_stock['stock_quantity'] < item['quantity']:
                    stock_update_failed = True
                    break
                
                # Deduct stock
                cursor.execute("""
                    UPDATE products 
                    SET stock_quantity = stock_quantity - %s 
                    WHERE product_id = %s
                """, (item['quantity'], item['product_id']))
                
                # Create order item
                cursor.execute("""
                    INSERT INTO order_items (
                        order_id, 
                        product_id, 
                        quantity, 
                        price_at_order
                    ) VALUES (%s, %s, %s, %s)
                """, (
                    order_id,
                    item['product_id'],
                    item['quantity'],
                    item['price']
                ))
            
            if stock_update_failed:
                # Rollback the entire transaction if stock update failed
                conn.rollback()
                return jsonify({
                    'success': False,
                    'message': 'Insufficient stock for one or more items. Please refresh your cart and try again.'
                }), 400
            
            # Remove only the ordered items from cart
            if selected_items:
                placeholders = ','.join(['%s'] * len(selected_items))
                cursor.execute(f"""
                    DELETE FROM cart_items 
                    WHERE user_id = %s AND cart_item_id IN ({placeholders})
                """, [user_id] + selected_items)
            else:
                # Clear entire cart (backward compatibility)
                cursor.execute("""
                    DELETE FROM cart_items 
                    WHERE user_id = %s
                """, (user_id,))
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': 'Order created successfully! Please visit our store to complete payment.',
                'order_id': order_id,
                'transaction_code': transaction_code,
                'total_amount': total_amount
            })
            
        finally:
            cursor.close()
            
    except Exception as e:
        print(f"Error creating store order: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': f'Failed to create order: {str(e)}'
        }), 500

@products_bp.route('/api/cart')
def get_cart():
    """Get cart items for the current user"""
    try:
        if 'user_id' not in session:
            return jsonify({
                'success': False,
                'message': 'Please log in to view cart'
            }), 401
        
        user_id = session['user_id']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute("""
                SELECT 
                    ci.cart_item_id,
                    ci.quantity,
                    p.product_id,
                    p.name,
                    p.price,
                    p.image_url,
                    p.stock_quantity,
                    p.status,
                    c.name as category_name
                FROM cart_items ci
                JOIN products p ON ci.product_id = p.product_id
                LEFT JOIN categories c ON p.category_id = c.category_id
                WHERE ci.user_id = %s
                ORDER BY ci.cart_item_id DESC
            """, (user_id,))
            
            cart_items = cursor.fetchall()
            
            # Calculate totals
            total_amount = 0
            total_items = 0
            
            for item in cart_items:
                # Format image URL
                if not item['image_url']:
                    item['image_url'] = 'static/images/placeholder-product.png'
                elif not any(item['image_url'].startswith(prefix) for prefix in ['http://', 'https://', '/static/', 'static/']):
                    item['image_url'] = f"static/images/{item['image_url'].lstrip('/')}"
                
                item['subtotal'] = float(item['price']) * item['quantity']
                total_amount += item['subtotal']
                total_items += item['quantity']
            
            return jsonify({
                'success': True,
                'cart_items': cart_items,
                'total_amount': round(total_amount, 2),
                'total_items': total_items,
                'cart_count': len(cart_items)
            })
            
        finally:
            cursor.close()
            
    except Exception as e:
        print(f"Error getting cart: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to load cart'
        }), 500

@products_bp.route('/api/cart/remove', methods=['POST'])
def remove_from_cart():
    """Remove an item from cart"""
    try:
        if 'user_id' not in session:
            return jsonify({
                'success': False,
                'message': 'Please log in to update cart'
            }), 401
        
        data = request.get_json()
        cart_item_id = data.get('cart_item_id')
        
        if not cart_item_id:
            return jsonify({
                'success': False,
                'message': 'Cart item ID is required'
            }), 400
        
        user_id = session['user_id']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Delete cart item
            cursor.execute("""
                DELETE FROM cart_items
                WHERE cart_item_id = %s AND user_id = %s
            """, (cart_item_id, user_id))
            
            if cursor.rowcount == 0:
                return jsonify({
                    'success': False,
                    'message': 'Cart item not found'
                }), 404
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': 'Item removed from cart',
                'cart_count': get_cart_count(user_id)
            })
            
        finally:
            cursor.close()
            
    except Exception as e:
        print(f"Error removing from cart: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to remove item from cart'
        }), 500

@products_bp.route('/api/orders/cancel', methods=['POST'])
def cancel_order():
    """Cancel an order and restore stock quantities (Admin only)"""
    try:
        role = session.get('role')
        if role not in ('Admin', 'Staff'):
            return jsonify({
                'success': False,
                'message': 'Only administrators can cancel orders'
            }), 403
        
        data = request.get_json()
        order_id = data.get('order_id')
        cancel_reason = data.get('reason', 'Cancelled by administrator')
        
        if not order_id:
            return jsonify({
                'success': False,
                'message': 'Order ID is required'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Get order details and items
            cursor.execute("""
                SELECT o.order_id, o.order_status, oi.order_item_id, 
                       oi.product_id, oi.quantity
                FROM orders o
                JOIN order_items oi ON o.order_id = oi.order_id
                WHERE o.order_id = %s
                FOR UPDATE
            """, (order_id,))
            
            order_items = cursor.fetchall()
            
            if not order_items:
                return jsonify({
                    'success': False,
                    'message': 'Order not found'
                }), 404
            
            # Check if order can be cancelled
            current_status = order_items[0]['order_status']
            if current_status in ('completed', 'cancelled'):
                return jsonify({
                    'success': False,
                    'message': f'Cannot cancel order in "{current_status}" status'
                }), 400
            
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
                SET order_status = 'cancelled',
                    updated_at = NOW()
                WHERE order_id = %s
            """, (order_id,))
            
            # Log the cancellation (optional - if you have an order_history table)
            # cursor.execute("""
            #     INSERT INTO order_history (order_id, status, reason, created_by, created_at)
            #     VALUES (%s, %s, %s, %s, NOW())
            # """, (order_id, 'cancelled', cancel_reason, session.get('user_id')))
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': 'Order cancelled successfully and stock quantities restored',
                'order_id': order_id,
                'items_restored': len(order_items)
            })
            
        finally:
            cursor.close()
            
    except Exception as e:
        print(f"Error cancelling order: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': f'Failed to cancel order: {str(e)}'
        }), 500

def get_cart_count(user_id):
    """Helper function to get cart item count for a user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM cart_items
            WHERE user_id = %s
        """, (user_id,))
        
        result = cursor.fetchone()
        cursor.close()
        
        return result[0] if result else 0
        
    except Exception as e:
        print(f"Error getting cart count: {str(e)}")
        return 0

@products_bp.route('/api/products/<int:product_id>/status', methods=['POST'])
def update_product_status(product_id):
    """Update product status (for admin use)"""
    role = session.get('role')
    if role not in ('Admin', 'Staff'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        new_status = data.get('status')
        
        if new_status not in ['active', 'hidden']:
            return jsonify({'success': False, 'message': 'Invalid status'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            UPDATE products 
            SET status = %s 
            WHERE product_id = %s
        """, (new_status, product_id))
        
        conn.commit()
        cursor.close()
        
        return jsonify({
            'success': True, 
            'message': f'Product status updated to {new_status}'
        })
        
    except Exception as e:
        print(f"Error updating product status: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to update status'}), 500