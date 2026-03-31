import mysql.connector
from mysql.connector import Error

def get_db_connection():
    """Get a fresh database connection"""
    try:
        connection = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="smart_stationery"
        )
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

# Global connection for backward compatibility
conn = get_db_connection()

def check_connection():
    """Check if global connection is still alive"""
    global conn
    try:
        if conn is None or not conn.is_connected():
            conn = get_db_connection()
        return conn
    except:
        conn = get_db_connection()
        return conn

# pip install mysql-connector-python