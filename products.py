from flask import Blueprint, render_template, request, jsonify, json, session, flash
from flask_login import login_required, current_user
from config import conn  # Use the existing connection

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
        # Get initial products (limited for initial load)
        products_data = get_products_data(limit=12)
        
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

def get_products_data(category='', limit=None, offset=0):
    """Helper function to get products data with filters"""
    try:
        # Build the base query
        query = """
            SELECT SQL_CALC_FOUND_ROWS 
                   p.*, c.name as category_name 
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.category_id
        """
        
        params = []
        
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
        data = get_products_data(category, limit, offset)
        
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
                SELECT product_id, name, price
                FROM products
                WHERE product_id = %s
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
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Get current cart items
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
                    'message': 'Your cart is empty'
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
            
            # Create order items
            for item in cart_items:
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
            
            # Clear the cart
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