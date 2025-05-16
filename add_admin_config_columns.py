"""
Direct SQL migration script to add new configuration columns to SystemConfig and OdooConfig tables.
This script adds columns that are needed for the admin configuration pages.
"""
import os
import sys
import psycopg2
from psycopg2 import sql
from datetime import datetime


def get_db_connection():
    """Connect to the database using environment variables"""
    try:
        conn = psycopg2.connect(
            dbname=os.environ.get('PGDATABASE'),
            user=os.environ.get('PGUSER'),
            password=os.environ.get('PGPASSWORD'),
            host=os.environ.get('PGHOST'),
            port=os.environ.get('PGPORT')
        )
        conn.autocommit = True
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)


def check_column_exists(conn, table_name, column_name):
    """Check if a column exists in a table"""
    with conn.cursor() as cur:
        cur.execute(sql.SQL("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_name = %s AND column_name = %s
            )
        """), (table_name, column_name))
        return cur.fetchone()[0]


def add_system_config_columns(conn):
    """Add new columns to the system_config table"""
    columns_to_add = {
        # Break configuration
        'minimum_break_duration': 'INTEGER DEFAULT 15',
        'maximum_break_duration': 'INTEGER DEFAULT 300',
        
        # Default shift settings
        'default_shift_id': 'INTEGER REFERENCES shift(id)',
        
        # AI Assistant configuration
        'ai_enabled': 'BOOLEAN DEFAULT FALSE',
        'ai_provider': 'VARCHAR(64) DEFAULT \'openai\'',
        'ai_api_key': 'VARCHAR(256)',
        
        # AI Feature toggles
        'enable_employee_assistant': 'BOOLEAN DEFAULT FALSE',
        'enable_report_insights': 'BOOLEAN DEFAULT FALSE',
        'enable_anomaly_detection': 'BOOLEAN DEFAULT FALSE',
        'enable_predictive_scheduling': 'BOOLEAN DEFAULT FALSE',
        
        # AI advanced settings
        'max_tokens': 'INTEGER DEFAULT 1000',
        'temperature': 'FLOAT DEFAULT 0.7',
        'prompt_template': 'TEXT',
        
        # AI usage statistics
        'ai_total_queries': 'INTEGER DEFAULT 0',
        'ai_monthly_tokens': 'INTEGER DEFAULT 0',
        'ai_success_rate': 'FLOAT DEFAULT 0.0',
    }
    
    with conn.cursor() as cur:
        for column_name, column_def in columns_to_add.items():
            if not check_column_exists(conn, 'system_config', column_name):
                print(f"Adding column {column_name} to system_config table")
                cur.execute(sql.SQL("ALTER TABLE system_config ADD COLUMN {} {}").format(
                    sql.Identifier(column_name),
                    sql.SQL(column_def)
                ))
                
        # Update existing ai_assistant_enabled to ai_enabled if exists
        if check_column_exists(conn, 'system_config', 'ai_assistant_enabled') and check_column_exists(conn, 'system_config', 'ai_enabled'):
            print("Migrating ai_assistant_enabled values to ai_enabled")
            cur.execute("""
                UPDATE system_config 
                SET ai_enabled = ai_assistant_enabled 
                WHERE ai_enabled IS NULL AND ai_assistant_enabled IS NOT NULL
            """)
            
        # Update existing openai_api_key to ai_api_key if exists
        if check_column_exists(conn, 'system_config', 'openai_api_key') and check_column_exists(conn, 'system_config', 'ai_api_key'):
            print("Migrating openai_api_key values to ai_api_key")
            cur.execute("""
                UPDATE system_config 
                SET ai_api_key = openai_api_key 
                WHERE ai_api_key IS NULL AND openai_api_key IS NOT NULL
            """)


def add_odoo_config_columns(conn):
    """Add new columns to the odoo_config table"""
    columns_to_add = {
        'url': 'VARCHAR(255)',
        'username': 'VARCHAR(255)',
        'api_key': 'VARCHAR(255)',
        'is_active': 'BOOLEAN DEFAULT FALSE',
    }
    
    with conn.cursor() as cur:
        for column_name, column_def in columns_to_add.items():
            if not check_column_exists(conn, 'odoo_config', column_name):
                print(f"Adding column {column_name} to odoo_config table")
                cur.execute(sql.SQL("ALTER TABLE odoo_config ADD COLUMN {} {}").format(
                    sql.Identifier(column_name),
                    sql.SQL(column_def)
                ))
                
        # Update nullable attributes for old columns for backward compatibility
        for column_name in ['host', 'port', 'database', 'user', 'password']:
            if check_column_exists(conn, 'odoo_config', column_name):
                print(f"Making column {column_name} nullable in odoo_config table")
                cur.execute(sql.SQL("ALTER TABLE odoo_config ALTER COLUMN {} DROP NOT NULL").format(
                    sql.Identifier(column_name)
                ))
        
        # Migrate data from old columns to new ones
        if check_column_exists(conn, 'odoo_config', 'host') and check_column_exists(conn, 'odoo_config', 'url'):
            print("Migrating host/port to url where applicable")
            cur.execute("""
                UPDATE odoo_config 
                SET url = 'http://' || host || ':' || CAST(port AS VARCHAR) 
                WHERE url IS NULL AND host IS NOT NULL
            """)
        
        if check_column_exists(conn, 'odoo_config', 'user') and check_column_exists(conn, 'odoo_config', 'username'):
            print("Migrating user to username")
            cur.execute("""
                UPDATE odoo_config 
                SET username = user 
                WHERE username IS NULL AND user IS NOT NULL
            """)
        
        if check_column_exists(conn, 'odoo_config', 'password') and check_column_exists(conn, 'odoo_config', 'api_key'):
            print("Migrating password to api_key")
            cur.execute("""
                UPDATE odoo_config 
                SET api_key = password 
                WHERE api_key IS NULL AND password IS NOT NULL
            """)
        
        if check_column_exists(conn, 'odoo_config', 'auto_sync') and check_column_exists(conn, 'odoo_config', 'is_active'):
            print("Migrating auto_sync to is_active")
            cur.execute("""
                UPDATE odoo_config 
                SET is_active = auto_sync 
                WHERE is_active IS NULL AND auto_sync IS NOT NULL
            """)


def main():
    """Main function to execute the migration"""
    start_time = datetime.now()
    print(f"Starting migration at {start_time}")
    
    conn = get_db_connection()
    
    try:
        # Add new columns to system_config
        add_system_config_columns(conn)
        
        # Add new columns to odoo_config
        add_odoo_config_columns(conn)
        
        print("Migration completed successfully!")
        print(f"Time elapsed: {datetime.now() - start_time}")
    except Exception as e:
        print(f"Error during migration: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()