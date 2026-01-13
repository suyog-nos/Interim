import mysql.connector

# Database connection configuration
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="test"
)

# Install required package: pip install mysql-connector-python