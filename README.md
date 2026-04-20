# Interim

A web application built with Python Flask and MySQL database.

## Quick Start

1. Extract the project files
2. Create and activate a virtual environment
3. Install dependencies
4. Start XAMPP (Apache + MySQL)
5. Import the database
6. Run the application

## Installation

### 1. Virtual Environment
```bash
python -m venv venv
```

**Windows:**
```bash
venv\Scripts\activate
```

**Mac/Linux:**
```bash
source venv/bin/activate
```

### 2. Dependencies
```bash
pip install -r requirements.txt
```

### 3. Database Setup
1. Start XAMPP (Apache + MySQL)
2. Open `http://localhost/phpmyadmin`
3. Create a new database
4. Import the provided SQL file

### 4. Run Application
```bash
python app.py
```

## Default Test Credentials

For QA and development purposes, the database is pre-configured with the following role-based accounts. All accounts share a unified password:

| Role | Email | Password |
|---|---|---|
| Admin | `admin@gmail.com` | `Admin@123` |
| Staff | `staff@gmail.com` | `Admin@123` |
| Customer | `customer@gmail.com` | `Admin@123` |

## Troubleshooting

**Database Connection:** Verify database credentials in config
**Missing Modules:** Ensure all dependencies are installed
**Environment Issues:** Make sure virtual environment is activated
