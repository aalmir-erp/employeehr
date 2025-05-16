"""
Script to generate an updated database schema SQL file.
This script extracts the current database structure and generates a SQL file.
"""
import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.schema import MetaData

def get_table_info(conn, table_name):
    """Get table column definitions"""
    query = f"""
    SELECT 
        column_name, 
        data_type, 
        is_nullable,
        column_default
    FROM 
        information_schema.columns
    WHERE 
        table_name = '{table_name}'
    ORDER BY 
        ordinal_position;
    """
    
    result = conn.execute(text(query))
    columns = []
    
    for row in result:
        column_name = row[0]
        data_type = row[1]
        is_nullable = "NULL" if row[2] == "YES" else "NOT NULL"
        default = f" DEFAULT {row[3]}" if row[3] is not None else ""
        
        columns.append(f"    {column_name} {data_type} {is_nullable}{default}")
    
    return columns

def get_primary_keys(conn, table_name):
    """Get primary key constraints"""
    query = f"""
    SELECT 
        tc.constraint_name, 
        kcu.column_name
    FROM 
        information_schema.table_constraints AS tc
    JOIN 
        information_schema.key_column_usage AS kcu
        ON tc.constraint_name = kcu.constraint_name
    WHERE 
        tc.table_name = '{table_name}'
        AND tc.constraint_type = 'PRIMARY KEY';
    """
    
    result = conn.execute(text(query))
    primary_keys = []
    
    for row in result:
        constraint_name = row[0]
        column_name = row[1]
        primary_keys.append(f"    CONSTRAINT {constraint_name} PRIMARY KEY ({column_name})")
    
    return primary_keys

def get_foreign_keys(conn, table_name):
    """Get foreign key constraints"""
    query = f"""
    SELECT 
        tc.constraint_name, 
        kcu.column_name, 
        ccu.table_name AS foreign_table_name,
        ccu.column_name AS foreign_column_name
    FROM 
        information_schema.table_constraints AS tc
    JOIN 
        information_schema.key_column_usage AS kcu
        ON tc.constraint_name = kcu.constraint_name
    JOIN 
        information_schema.constraint_column_usage AS ccu
        ON ccu.constraint_name = tc.constraint_name
    WHERE 
        tc.table_name = '{table_name}'
        AND tc.constraint_type = 'FOREIGN KEY';
    """
    
    result = conn.execute(text(query))
    foreign_keys = []
    
    for row in result:
        constraint_name = row[0]
        column_name = row[1]
        foreign_table = row[2]
        foreign_column = row[3]
        
        foreign_keys.append(
            f"    CONSTRAINT {constraint_name} FOREIGN KEY ({column_name}) REFERENCES {foreign_table}({foreign_column})"
        )
    
    return foreign_keys

def get_unique_constraints(conn, table_name):
    """Get unique constraints"""
    query = f"""
    SELECT 
        tc.constraint_name, 
        kcu.column_name
    FROM 
        information_schema.table_constraints AS tc
    JOIN 
        information_schema.key_column_usage AS kcu
        ON tc.constraint_name = kcu.constraint_name
    WHERE 
        tc.table_name = '{table_name}'
        AND tc.constraint_type = 'UNIQUE';
    """
    
    result = conn.execute(text(query))
    constraints = {}
    
    for row in result:
        constraint_name = row[0]
        column_name = row[1]
        
        if constraint_name not in constraints:
            constraints[constraint_name] = []
        
        constraints[constraint_name].append(column_name)
    
    unique_constraints = []
    for constraint_name, columns in constraints.items():
        columns_str = ", ".join(columns)
        unique_constraints.append(f"    CONSTRAINT {constraint_name} UNIQUE ({columns_str})")
    
    return unique_constraints

def get_indexes(conn, table_name):
    """Get indexes (excluding those for constraints)"""
    query = f"""
    SELECT
        indexname,
        indexdef
    FROM
        pg_indexes
    WHERE
        tablename = '{table_name}'
        AND indexname NOT IN (
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = '{table_name}'
        );
    """
    
    result = conn.execute(text(query))
    indexes = []
    
    for row in result:
        indexes.append(row[1] + ";")
    
    return indexes

def get_sequences(conn):
    """Get all sequence information"""
    query = """
    SELECT
        sequence_name,
        data_type,
        start_value,
        minimum_value,
        maximum_value,
        increment
    FROM
        information_schema.sequences
    WHERE
        sequence_schema = 'public'
    ORDER BY
        sequence_name;
    """
    
    result = conn.execute(text(query))
    sequences = []
    
    for row in result:
        sequence_name = row[0]
        data_type = row[1]
        start_value = row[2]
        min_value = row[3]
        max_value = row[4]
        increment = row[5]
        
        seq_def = f"CREATE SEQUENCE IF NOT EXISTS {sequence_name} "
        seq_def += f"INCREMENT BY {increment} "
        seq_def += f"MINVALUE {min_value} "
        seq_def += f"MAXVALUE {max_value} "
        seq_def += f"START WITH {start_value} "
        seq_def += "CACHE 1;"
        
        sequences.append((sequence_name, seq_def))
    
    return sequences

def generate_schema_file():
    """Generate schema SQL file for all tables"""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        print("DATABASE_URL environment variable not set")
        sys.exit(1)
    
    engine = create_engine(database_url)
    
    # In SQLAlchemy 2.0, we need to use connection and run transactions
    with engine.connect() as conn:
        with open('database_schema.sql', 'w') as f:
            f.write("-- Updated database schema for MIR Attendance Management System\n")
            f.write("-- Generated on: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
            
            # First add sequences
            f.write("-- Sequences\n")
            sequences = get_sequences(conn)
            for seq_name, seq_def in sequences:
                f.write(f"{seq_def}\n")
            f.write("\n")
            
            # Then add tables
            query = """
            SELECT tablename 
            FROM pg_catalog.pg_tables
            WHERE schemaname='public'
            ORDER BY tablename;
            """
            
            result = conn.execute(text(query))
            tables = [row[0] for row in result]
            
            for table in tables:
                if table == 'alembic_version':
                    continue  # Skip migration management table
                    
                f.write(f"-- Table: {table}\n")
                f.write(f"CREATE TABLE IF NOT EXISTS {table} (\n")
                
                # Get columns
                columns = get_table_info(conn, table)
                
                # Get constraints
                primary_keys = get_primary_keys(conn, table)
                foreign_keys = get_foreign_keys(conn, table)
                unique_constraints = get_unique_constraints(conn, table)
                
                # Combine all parts
                all_parts = columns + primary_keys + foreign_keys + unique_constraints
                
                # Join with commas except for the last element
                for i, part in enumerate(all_parts):
                    if i < len(all_parts) - 1:
                        f.write(part + ",\n")
                    else:
                        f.write(part + "\n")
                
                f.write(");\n\n")
                
                # Add indexes
                indexes = get_indexes(conn, table)
                if indexes:
                    f.write("-- Indexes for table: " + table + "\n")
                    for idx in indexes:
                        f.write(idx + "\n")
                    f.write("\n")
            
            # Add a comment about how to run this schema
            f.write("-- Note: This schema is for reference only and includes all tables and sequences.\n")
            f.write("-- If you want to recreate the database, run the sequences first, then the tables in dependency order.\n")
        
        print(f"Schema successfully written to database_schema.sql")

if __name__ == "__main__":
    from datetime import datetime
    generate_schema_file()