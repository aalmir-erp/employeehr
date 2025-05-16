#!/usr/bin/env python3
import os
import re

def fix_route_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Replace blueprint definition
    content = re.sub(r'([\w_]+)_bp = Blueprint', r'bp = Blueprint', content)
    
    # Replace route decorators
    content = re.sub(r'@([\w_]+)_bp\.route', r'@bp.route', content)
    
    # Remove blueprint registration at the end
    content = re.sub(r'# Register blueprint with the app[\s\S]*?app\.register_blueprint\([\w_]+_bp\)[\s\n]*', '', content)
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    print(f"Fixed {filepath}")

def main():
    routes_dir = "routes"
    for filename in os.listdir(routes_dir):
        if filename.endswith(".py"):
            fix_route_file(os.path.join(routes_dir, filename))

if __name__ == "__main__":
    main()
