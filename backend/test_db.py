from backend.db import test_connection

def main():
    database_name = test_connection()
    print(f"Successfully connected to PostgreSQL: {database_name}")

if __name__ == "__main__":
    main()