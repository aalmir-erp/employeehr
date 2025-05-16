"""
Direct SQL migration script to add late_minutes column to attendance_record table.
"""

import os
import sys
import psycopg2
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Main function to execute the migration"""
    try:
        # Get database connection info from environment variables
        db_url = os.environ.get('DATABASE_URL')
        
        if not db_url:
            logger.error("DATABASE_URL environment variable not found")
            return False
            
        logger.info("Connecting to database")
        
        # Connect to the database
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        cursor = conn.cursor()
        
        try:
            # Check if column already exists
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'attendance_record' AND column_name = 'late_minutes'
            """)
            
            column_exists = cursor.fetchone() is not None
            
            if column_exists:
                logger.info("Column late_minutes already exists in attendance_record table")
                return True
                
            # Add the column
            logger.info("Adding late_minutes column to attendance_record table")
            cursor.execute("""
                ALTER TABLE attendance_record 
                ADD COLUMN late_minutes INTEGER DEFAULT 0 NOT NULL
            """)
            
            # Commit the changes
            conn.commit()
            logger.info("Migration completed successfully")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error during migration: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        return False
        
if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)