"""
Script to fix all database models to use the custom JSONB type
"""
import re

def fix_models_file():
    """Replace all PostgreSQL JSONB references with custom JSONB type"""
    try:
        # Read the current models.py file
        with open('models.py', 'r') as f:
            content = f.read()
        
        # Replace all references to db.dialects.postgresql.JSONB with JSONB
        fixed_content = re.sub(
            r'db\.dialects\.postgresql\.JSONB', 
            'JSONB', 
            content
        )
        
        # Write the updated content back to models.py
        with open('models.py', 'w') as f:
            f.write(fixed_content)
        
        print("Successfully replaced all PostgreSQL JSONB references with custom JSONB type")
        return True
    except Exception as e:
        print(f"Error fixing models: {e}")
        return False

if __name__ == "__main__":
    fix_models_file()