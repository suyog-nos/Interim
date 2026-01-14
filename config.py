import mysql.connector

# Database connection configuration
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="interim_test_database"
)