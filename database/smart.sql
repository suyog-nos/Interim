-- ========================
-- SMART STATIONERY MANAGEMENT SYSTEM
-- ========================

-- ========================
-- 1. DATABASE SETUP
-- ========================
CREATE DATABASE IF NOT EXISTS smart_stationery;
USE smart_stationery;

-- ========================
-- 2. CORE TABLES
-- ========================

-- USERS TABLE
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(15),
    citizen_id VARCHAR(20) UNIQUE,
    province VARCHAR(50),
    district VARCHAR(50),
    address TEXT,
    hashed_password VARCHAR(255) NOT NULL,
    role ENUM('Customer','Staff','Admin') NOT NULL DEFAULT 'Customer',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_email (email),
    INDEX idx_role (role),
    INDEX idx_name (first_name, last_name)
);

-- CATEGORIES TABLE
CREATE TABLE categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    
    INDEX idx_name (name)
);

-- SUPPLIERS TABLE
CREATE TABLE suppliers (
    supplier_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    contact_person VARCHAR(100),
    email VARCHAR(100),
    phone VARCHAR(15),
    address TEXT,
    pan_number VARCHAR(20),
    vat_number VARCHAR(20),
    
    INDEX idx_name (name)
);

-- ========================
-- 3. INITIAL REFERENCE DATA
-- ========================

-- Default system users
INSERT INTO users (first_name, last_name, email, hashed_password, role) VALUES 
('Yogi', 'Admin', 'admin@gmail.com', 'pbkdf2:sha256:1000000$URzxNiwiJCuhH2j8$d893d71ac9c69b5b49bc61a24d294abda0798ce0c55610723988f39758b4cb6d', 'Admin'),
('Yogi', 'Staff', 'staff@gmail.com', 'pbkdf2:sha256:1000000$URzxNiwiJCuhH2j8$d893d71ac9c69b5b49bc61a24d294abda0798ce0c55610723988f39758b4cb6d', 'Staff'),
('Yogi', 'Customer', 'customer@gmail.com', 'pbkdf2:sha256:1000000$URzxNiwiJCuhH2j8$d893d71ac9c69b5b49bc61a24d294abda0798ce0c55610723988f39758b4cb6d', 'Customer'),

-- Additional staff users
('Raj', 'Kumar', 'staff1@gmail.com', 'pbkdf2:sha256:1000000$URzxNiwiJCuhH2j8$d893d71ac9c69b5b49bc61a24d294abda0798ce0c55610723988f39758b4cb6d', 'Staff'),
('Priya', 'Sharma', 'staff2@gmail.com', 'pbkdf2:sha256:1000000$URzxNiwiJCuhH2j8$d893d71ac9c69b5b49bc61a24d294abda0798ce0c55610723988f39758b4cb6d', 'Staff'),
('Amit', 'Singh', 'staff3@gmail.com', 'pbkdf2:sha256:1000000$URzxNiwiJCuhH2j8$d893d71ac9c69b5b49bc61a24d294abda0798ce0c55610723988f39758b4cb6d', 'Staff'),
('Sneha', 'Verma', 'staff4@gmail.com', 'pbkdf2:sha256:1000000$URzxNiwiJCuhH2j8$d893d71ac9c69b5b49bc61a24d294abda0798ce0c55610723988f39758b4cb6d', 'Staff'),
('Vikram', 'Patel', 'staff5@gmail.com', 'pbkdf2:sha256:1000000$URzxNiwiJCuhH2j8$d893d71ac9c69b5b49bc61a24d294abda0798ce0c55610723988f39758b4cb6d', 'Staff'),

-- Additional customer users
('John', 'Doe', 'customer1@gmail.com', 'pbkdf2:sha256:1000000$URzxNiwiJCuhH2j8$d893d71ac9c69b5b49bc61a24d294abda0798ce0c55610723988f39758b4cb6d', 'Customer'),
('Jane', 'Smith', 'customer2@gmail.com', 'pbkdf2:sha256:1000000$URzxNiwiJCuhH2j8$d893d71ac9c69b5b49bc61a24d294abda0798ce0c55610723988f39758b4cb6d', 'Customer'),
('Mike', 'Johnson', 'customer3@gmail.com', 'pbkdf2:sha256:1000000$URzxNiwiJCuhH2j8$d893d71ac9c69b5b49bc61a24d294abda0798ce0c55610723988f39758b4cb6d', 'Customer'),
('Sarah', 'Williams', 'customer4@gmail.com', 'pbkdf2:sha256:1000000$URzxNiwiJCuhH2j8$d893d71ac9c69b5b49bc61a24d294abda0798ce0c55610723988f39758b4cb6d', 'Customer'),
('David', 'Brown', 'customer5@gmail.com', 'pbkdf2:sha256:1000000$URzxNiwiJCuhH2j8$d893d71ac9c69b5b49bc61a24d294abda0798ce0c55610723988f39758b4cb6d', 'Customer');

-- Product categories
INSERT INTO categories (name, description) VALUES 
('Ball Pens', 'Various types of ball point pens'),
('Gel Pens', 'Smooth writing gel ink pens'),
('Fountain Pens', 'Classic fountain pens with nibs'),
('Markers', 'Permanent, temporary and specialty markers'),
('Highlighters', 'Highlighting markers and packs'),
('Pencils', 'Color pencils, wooden pencils, sketch pencils'),
('Copies & Registers', 'Notebooks, registers and writing books'),
('Office Supplies', 'Staplers, files, clips and office essentials'),
('Sports Equipment', 'Sports balls, rackets and equipment'),
('Paper Products', 'Photocopy paper and specialty paper'),
('Gift Wrap', 'Wrapping paper and ribbons'),
('Adhesives', 'Glue, tape and adhesive products'),
('Cutting Tools', 'Scissors and cutting instruments');

-- Suppliers with PAN/VAT
INSERT INTO suppliers (name, contact_person, email, phone, pan_number, vat_number) VALUES 
('Pentonic Suppliers', 'Raj Sharma', 'pentonic@supplier.com', '9876543210', 'ABCDE1234F', 'VAT123456789'),
('DOMS Corporation', 'Priya Patel', 'doms@supplier.com', '9876543211', 'BCDEF2345G', 'VAT234567890'),
('Natraj Suppliers', 'Amit Kumar', 'natraj@supplier.com', '9876543212', 'CDEFG3456H', 'VAT345678901'),
('Mayur Stationery', 'Sneha Verma', 'mayur@supplier.com', '9876543213', 'DEFGH4567I', 'VAT456789012'),
('General Sports Co.', 'Vikram Singh', 'sports@supplier.com', '9876543214', 'EFGHI5678J', 'VAT567890123'),
('Office Pro Suppliers', 'Anita Desai', 'office@supplier.com', '9876543215', 'FGHIJ6789K', 'VAT678901234');

-- ========================
-- 4. PRODUCTS & INVENTORY
-- ========================
-- PRODUCTS TABLE
CREATE TABLE products (
    product_id INT AUTO_INCREMENT PRIMARY KEY,

    -- Basic product info
    name VARCHAR(255) NOT NULL,            
    category_id INT NOT NULL,
    supplier_id INT NOT NULL,
    brand VARCHAR(100) DEFAULT '',        -- optional, default empty
    sku VARCHAR(50) UNIQUE NOT NULL,       
    price DECIMAL(10,2) NOT NULL CHECK (price >= 0),

    -- Stock in smallest unit (always pieces)
    stock_quantity INT DEFAULT 0 CHECK (stock_quantity >= 0),

    -- Unit type for display and conversion
    unit_type ENUM('piece','pack','dozen','bundle') DEFAULT 'piece',
    units_per_pack INT DEFAULT 1, -- number of pieces per pack/dozen/bundle

    -- Auto-calculated stock status
    stock_status VARCHAR(20) AS (
        CASE 
            WHEN stock_quantity > 20 THEN 'in_stock'
            WHEN stock_quantity > 0 THEN 'low_stock'
            ELSE 'out_of_stock'
        END
    ) STORED,

    -- Optional image
    image_url VARCHAR(255) DEFAULT '',

    -- Product status for admin control
    status ENUM('active','hidden') DEFAULT 'active',

    -- Foreign keys
    FOREIGN KEY (category_id) REFERENCES categories(category_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),

    -- Indexes for faster search
    INDEX idx_category (category_id),
    INDEX idx_supplier (supplier_id),
    INDEX idx_brand (brand),
    INDEX idx_stock_status (stock_status),
    INDEX idx_sku (sku),
    INDEX idx_status (status)
);


-- Sample product data
INSERT INTO products (name, category_id, supplier_id, price, stock_quantity, unit_type, units_per_pack, brand, sku, image_url, status) VALUES 
('Pentonic Blue 0.7mm', 1, 1, 50, 100, 'piece', 1, 'Pentonic', 'BALL-003-B07', 'static/images/Pentonic.png', 'active'),
('Pentonic Blue 1.0mm', 1, 1, 50, 80, 'piece', 1, 'Pentonic', 'BALL-003-B10', 'static/images/Pentonic.png', 'active'),
('Pentonic Black 0.7mm', 1, 1, 50, 120, 'piece', 1, 'Pentonic', 'BALL-004-K07', 'static/images/Pentonic.png', 'active'),
('Pentonic Black 1.0mm', 1, 1, 50, 100, 'piece', 1, 'Pentonic', 'BALL-004-K10', 'static/images/Pentonic.png', 'active'),
('Goldex 0.7mm', 1, 2, 50, 75, 'piece', 1, 'Goldex', 'BALL-005-B07', 'static/images/goldexblue.png', 'active'),
('Goldex 1.0mm', 1, 2, 50, 65, 'piece', 1, 'Goldex', 'BALL-005-B10', 'static/images/goldexblue.png', 'active'),
('Goldex 0.5mm Gel', 2, 2, 50, 85, 'piece', 1, 'Goldex', 'GEL-002', 'static/images/goldexblue.png', 'hidden'),
('Unomax Blue', 2, 3, 180, 20, 'piece', 1, 'Unomax', 'GEL-001-B', 'static/images/Unomaxblue.png', 'active'),
('Unomax Black', 2, 3, 180, 15, 'piece', 1, 'Unomax', 'GEL-001-K', 'static/images/Unomaxblack.png', 'active'),
('Permanent Marker - Red', 4, 4, 50, 45, 'piece', 1, 'Generic', 'MARK-001', 'static/images/markers.png', 'active'),
('Permanent Marker - Blue', 4, 4, 50, 50, 'piece', 1, 'Generic', 'MARK-002', 'static/images/markers.png', 'active'),
('DOMS Big (12 colors)', 6, 2, 120, 25, 'piece', 1, 'DOMS', 'PENC-001', 'static/images/bigdoms.png', 'active'),
('DOMS Small (12 colors)', 6, 2, 60, 40, 'piece', 1, 'DOMS', 'PENC-002', 'static/images/smalldoms.png', 'hidden'),
('Pentonic Pen Pack (10pcs)', 1, 1, 450, 30, 'pack', 10, 'Pentonic', 'BALL-PACK-001', 'static/images/Pentonic.png', 'active'),
('Marker Pack (6pcs)', 4, 4, 250, 15, 'pack', 6, 'Generic', 'MARK-PACK-001', 'static/images/markers.png', 'hidden'),
('MR YOD Football', 9, 5, 950, 12, 'piece', 1, 'MR YOD', 'SPORT-001', 'static/images/football.png', 'active'),
('VSE Badminton Racket', 9, 5, 5000, 8, 'piece', 1, 'VSE', 'SPORT-008', 'static/images/badminton.png', 'active'),
('No.10 Stapler', 8, 6, 100, 25, 'piece', 1, 'Generic', 'OFF-001', 'static/images/stapler.png', 'active'),
('Small Paper Clips', 8, 6, 100, 80, 'pack', 100, 'Generic', 'OFF-007', 'static/images/paperclip.png', 'hidden');

-- ========================
-- 5. INVENTORY MANAGEMENT
-- ========================

-- STOCK HISTORY TABLE
CREATE TABLE stock_history (
    history_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    supplier_id INT NOT NULL,
    quantity_received INT NOT NULL CHECK (quantity_received >= 0),
    purchase_price DECIMAL(10,2) NOT NULL CHECK (purchase_price >= 0),
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
    
    INDEX idx_product (product_id),
    INDEX idx_received (received_at),
    INDEX idx_supplier (supplier_id)
);

-- ========================
-- NEW ARRIVAL ALERTS TABLE
-- ========================
CREATE TABLE new_arrival_alerts (
    arrival_id INT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity_received INT NOT NULL CHECK (quantity_received >= 0),
    supplier_id INT NULL,
    purchase_price DECIMAL(10,2) NULL,
    status ENUM('Pending', 'Approved', 'Rejected') DEFAULT 'Pending',
    staff_notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (staff_id) REFERENCES users(user_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),

    INDEX idx_staff (staff_id),
    INDEX idx_product (product_id),
    INDEX idx_status (status),
    INDEX idx_supplier (supplier_id)
);

-- ========================
-- STOCK REQUESTS TABLE
-- ========================
CREATE TABLE stock_requests (
    request_id INT AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    product_id INT NOT NULL,
    supplier_id INT,
    requested_quantity INT NOT NULL CHECK (requested_quantity >= 0),
    reason TEXT,
    status ENUM('Pending','Approved','Rejected') DEFAULT 'Pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (staff_id) REFERENCES users(user_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),

    INDEX idx_staff (staff_id),
    INDEX idx_product (product_id),
    INDEX idx_supplier (supplier_id),
    INDEX idx_status (status)
);

-- CART ITEMS TABLE
CREATE TABLE cart_items (
    cart_item_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL CHECK (quantity >= 0),
    
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    
    INDEX idx_user (user_id),
    INDEX idx_product (product_id)
);

CREATE TABLE orders (
    order_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    staff_id INT NULL,
    order_type ENUM('POS', 'Online') NOT NULL DEFAULT 'Online',
    payment_type ENUM('Pay at Store','Pay Online') NOT NULL,
    payment_status ENUM('Paid','Unpaid') DEFAULT 'Unpaid',
    order_status ENUM('processing','ready_for_pickup','completed','cancelled') DEFAULT 'processing',
    total_amount DECIMAL(10,2) NOT NULL CHECK (total_amount >= 0),
    transaction_code VARCHAR(100) UNIQUE NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (staff_id) REFERENCES users(user_id),
    
    INDEX idx_user (user_id),
    INDEX idx_staff (staff_id),
    INDEX idx_status (order_status),
    INDEX idx_created (created_at),
    INDEX idx_payment_status (payment_status),
    INDEX idx_transaction_code (transaction_code),
    INDEX idx_order_type (order_type)
);

-- ORDER ITEMS TABLE
CREATE TABLE order_items (
    order_item_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    sold_unit ENUM('piece','pack','dozen','bundle') DEFAULT 'piece',
    price_at_order DECIMAL(10,2) NOT NULL,
    
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    
    INDEX idx_order (order_id),
    INDEX idx_product (product_id)
);

-- ========================
-- 7. STORE OPERATIONS
-- ========================

-- PRODUCT EXCHANGES TABLE (NO REFUNDS)
CREATE TABLE product_exchanges (
    exchange_id INT AUTO_INCREMENT PRIMARY KEY,
    original_product_id INT NOT NULL,
    exchanged_product_id INT NOT NULL,
    quantity INT NOT NULL,
    reason ENUM('damaged', 'defective', 'wrong_item', 'other') NOT NULL,
    notes TEXT,
    handled_by INT NOT NULL,
    exchanged_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (original_product_id) REFERENCES products(product_id),
    FOREIGN KEY (exchanged_product_id) REFERENCES products(product_id),
    FOREIGN KEY (handled_by) REFERENCES users(user_id),
    
    INDEX idx_original_product (original_product_id),
    INDEX idx_exchanged_product (exchanged_product_id),
    INDEX idx_exchanged_at (exchanged_at),
    INDEX idx_handled_by (handled_by)
);

-- TASKS TABLE
CREATE TABLE tasks (
    task_id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    assigned_to INT NOT NULL,
    due_date DATE NOT NULL,
    priority ENUM('low','medium','high') DEFAULT 'medium',
    category VARCHAR(100) DEFAULT 'General',
    status ENUM('pending','in-progress','completed') DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (assigned_to) REFERENCES users(user_id),

    INDEX idx_priority (priority),
    INDEX idx_due_date (due_date),
    INDEX idx_status (status),
    INDEX idx_assigned_to (assigned_to),
    INDEX idx_created (created_at)
);
