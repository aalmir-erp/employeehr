#!/usr/bin/env python

"""
This script helps fix migration issues by checking if a column already exists
before attempting to add it during migration.

Usage:
  python fix_migration.py
"""

import os
import sys
import psycopg2
import psycopg2.extras

def get_database_url():
    """Get database URL from environment or prompt user"""
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print('DATABASE_URL environment variable not found.')
        host = input('Database host [localhost]: ') or 'localhost'
        port = input('Database port [5432]: ') or '5432'
        user = input('Database user: ')
        password = input('Database password: ')
        db_name = input('Database name: ')
        db_url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    return db_url

def parse_db_url(db_url):
    """Parse database URL into components"""
    # Remove postgresql:// prefix
    if db_url.startswith('postgresql://'):
        db_url = db_url[len('postgresql://'):]        
    
    # Split into credentials and host_part
    if '@' in db_url:
        credentials, host_part = db_url.split('@', 1)
    else:
        credentials, host_part = '', db_url
    
    # Parse credentials
    if ':' in credentials:
        user, password = credentials.split(':', 1)
    else:
        user, password = credentials, ''
    
    # Parse host part
    host_port, db_name = host_part.split('/', 1)
    
    if ':' in host_port:
        host, port = host_port.split(':', 1)
    else:
        host, port = host_port, '5432'
    
    # Remove query parameters if present
    if '?' in db_name:
        db_name = db_name.split('?', 1)[0]
        
    return {
        'host': host,
        'port': int(port),
        'user': user,
        'password': password,
        'dbname': db_name
    }

def check_column_exists(connection, table_name, column_name):
    """Check if a column exists in a table"""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s AND column_name = %s
        """, (table_name, column_name))
        return cursor.fetchone() is not None

def fix_migration_force_password_change():
    """Fix the force_password_change column migration issue"""
    db_url = get_database_url()
    conn_params = parse_db_url(db_url)
    
    try:
        connection = psycopg2.connect(**conn_params)
        connection.autocommit = True

        # Check if column exists
        column_exists = check_column_exists(connection, 'user', 'force_password_change')
        
        if column_exists:
            print("\nThe 'force_password_change' column already exists in the 'user' table.")
            print("Modifying migration file to handle this case...")
            
            # Get migration directory
            migration_dir = input("\nEnter the path to your migrations/versions directory: ")
            migration_file = None
            
            # Find the migration file that adds force_password_change
            for filename in os.listdir(migration_dir):
                if filename.endswith('.py') and 'force_password_change' in filename:
                    migration_file = os.path.join(migration_dir, filename)
                    break
            
            if migration_file and os.path.exists(migration_file):
                with open(migration_file, 'r') as file:
                    content = file.read()
                
                # Modify the upgrade function to check if column exists
                if "op.add_column('user', sa.Column('force_password_change'" in content:
                    new_content = content.replace(
                        "op.add_column('user', sa.Column('force_password_change'", 
                        "# Check if column exists before adding\n    if not op.get_bind().dialect.has_column(op.get_bind(), 'user', 'force_password_change'):\n        op.add_column('user', sa.Column('force_password_change'"
                    )
                    
                    # Write back the modified content
                    with open(migration_file, 'w') as file:
                        file.write(new_content)
                    
                    print(f"\nSuccessfully modified migration file: {migration_file}")
                    print("You can now run 'flask db upgrade' again.")
                else:
                    print("\nCouldn't find the 'add_column' command in the migration file.")
                    print("You might need to manually edit the migration file.")
            else:
                print("\nCouldn't find the migration file that adds 'force_password_change'.")
                print("You might need to manually create a new migration or edit the existing one.")
                
        else:
            print("\nThe 'force_password_change' column does not exist in the 'user' table.")
            print("The migration should proceed normally.")
            
    except Exception as e:
        print(f"\nError: {str(e)}")
    finally:
        if 'connection' in locals() and connection is not None:
            connection.close()

def manually_add_column():
    """Manually add the force_password_change column if needed"""
    db_url = get_database_url()
    conn_params = parse_db_url(db_url)
    
    try:
        connection = psycopg2.connect(**conn_params)
        connection.autocommit = True

        # Check if column exists
        column_exists = check_column_exists(connection, 'user', 'force_password_change')
        
        if not column_exists:
            print("\nAdding 'force_password_change' column to 'user' table...")
            with connection.cursor() as cursor:
                cursor.execute("""
                    ALTER TABLE "user" ADD COLUMN force_password_change BOOLEAN DEFAULT FALSE
                """)
            print("Column added successfully.")
        else:
            print("\nThe 'force_password_change' column already exists.")
            
    except Exception as e:
        print(f"\nError: {str(e)}")
    finally:
        if 'connection' in locals() and connection is not None:
            connection.close()

def main():
    print("\n=== Database Migration Fix Tool ===\n")
    print("This tool helps fix issues with database migrations.")
    print("Choose an action:")
    print("1. Fix 'force_password_change' migration issue")
    print("2. Manually add 'force_password_change' column")
    print("3. Exit")
    
    choice = input("\nEnter your choice (1-3): ")
    
    if choice == '1':
        fix_migration_force_password_change()
    elif choice == '2':
        manually_add_column()
    else:
        print("Exiting.")

if __name__ == "__main__":
    main()
