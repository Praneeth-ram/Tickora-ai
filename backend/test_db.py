from backend.db import test_connection as check_database_connection

def main():
    database_name = check_database_connection()
    print(f"Successfully connected to PostgreSQL: {database_name}")

if __name__ == "__main__":
    main()