"""
Check if required_approvals column exists in system_config and display its value
"""
import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Create a new minimal Flask app just for checking config
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
db.init_app(app)

# Define a minimal SystemConfig model
class SystemConfig(db.Model):
    __tablename__ = 'system_config'
    
    id = db.Column(db.Integer, primary_key=True)
    system_name = db.Column(db.String)
    required_approvals = db.Column(db.Integer)

def check_config():
    """Check system configuration for required_approvals"""
    with app.app_context():
        config = SystemConfig.query.first()
        if config:
            print(f"System name: {config.system_name}")
            # Try to access the required_approvals column
            try:
                print(f"Required approvals: {config.required_approvals}")
            except Exception as e:
                print(f"Error accessing required_approvals: {str(e)}")
        else:
            print("No system configuration found")

if __name__ == "__main__":
    check_config()