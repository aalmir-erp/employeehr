#!/usr/bin/env python

"""
This script fixes circular import issues between app.py and models.py

Usage:
  python fix_circular_import.py
"""

import os
import sys
import re

def fix_app_py():
    """Fix the app.py file to avoid circular imports"""
    app_file = 'app.py'
    if not os.path.exists(app_file):
        print(f"Error: {app_file} not found")
        return False
    
    with open(app_file, 'r') as f:
        content = f.read()
    
    # Pattern to look for: import models and from models import User
    if 'import models' in content and 'from models import User' in content:
        # Remove 'from models import User'
        new_content = re.sub(r'from models import User', '# Moved to avoid circular import', content)
        
        # Add @login_manager.user_loader after app configuration
        if '@login_manager.user_loader' not in new_content:
            # Check if login_manager is defined
            if 'login_manager = LoginManager()' in new_content:
                # Add user_loader function near the end of initialization
                user_loader_code = """
# User loader callback for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    from models import User  # Import here to avoid circular import
    return User.query.get(int(user_id))
"""
                # Find a good spot to insert it - after db.create_all() but before route imports
                if 'db.create_all()' in new_content:
                    new_content = new_content.replace('db.create_all()', 'db.create_all()' + user_loader_code)
                else:
                    # Just append at the end before route imports
                    route_import_pattern = r'(from routes|import routes)'
                    match = re.search(route_import_pattern, new_content)
                    if match:
                        index = match.start()
                        new_content = new_content[:index] + user_loader_code + new_content[index:]
                    else:
                        # If no route imports, just append to end
                        new_content += user_loader_code
        
        # Write the changes back
        with open(app_file, 'w') as f:
            f.write(new_content)
        
        print(f"Updated {app_file} to fix circular import")
        return True
    else:
        print(f"No circular import pattern found in {app_file}")
        return False

def check_main_py():
    """Check if main.py is properly configured"""
    main_file = 'main.py'
    if not os.path.exists(main_file):
        print(f"Warning: {main_file} not found. Creating...")
        with open(main_file, 'w') as f:
            f.write("""from app import app  # This imports the Flask app instance

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
""")
        print(f"Created {main_file}")
        return True
    
    with open(main_file, 'r') as f:
        content = f.read()
    
    if 'from app import app' not in content:
        print(f"Warning: {main_file} might not be properly importing the app instance")
        print("Consider modifying it to contain:'from app import app'")
        return False
    
    print(f"{main_file} appears to be correctly configured")
    return True

def fix_models_py():
    """Fix models.py to ensure no circular imports"""
    models_file = 'models.py'
    if not os.path.exists(models_file):
        print(f"Error: {models_file} not found")
        return False
    
    with open(models_file, 'r') as f:
        content = f.read()
    
    # Check imports
    if 'from app import' in content:
        # Only modify if needed
        lines = content.split('\n')
        modified_lines = []
        app_imports = []
        
        for line in lines:
            # Collect all imports from app
            if line.strip().startswith('from app import'):
                imports = line.replace('from app import', '').strip().split(',')
                for imp in imports:
                    imp = imp.strip()
                    if imp and imp not in app_imports:
                        app_imports.append(imp)
                # Skip this line, we'll add a modified version later
            else:
                modified_lines.append(line)
        
        # Add the import at the top
        if app_imports:
            modified_lines.insert(0, f"from app import {', '.join(app_imports)}")
        
        # Write the changes back
        new_content = '\n'.join(modified_lines)
        with open(models_file, 'w') as f:
            f.write(new_content)
        
        print(f"Updated {models_file} to consolidate app imports")
        return True
    else:
        print(f"No imports from app found in {models_file}, no changes needed")
        return False

def main():
    print("\n=== Circular Import Fix Tool ===\n")
    
    print("Analyzing and fixing circular import issues...\n")
    
    app_fixed = fix_app_py()
    models_fixed = fix_models_py()
    main_checked = check_main_py()
    
    if app_fixed or models_fixed:
        print("\nChanges were made to fix circular import issues.")
        print("You should now be able to run the application without circular import errors.")
        print("\nTry running: python main.py")
    else:
        print("\nNo changes were needed or issues could not be automatically fixed.")
        print("If you still experience circular import issues, you may need to manually restructure your code.")
        print("Consider creating a separate file for your database models or initializing your app in a different way.")

if __name__ == "__main__":
    main()
