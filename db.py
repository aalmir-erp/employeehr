"""Contains database instance to avoid circular imports

This file creates and exports only the SQLAlchemy database instance.
It's used by both models.py and app.py to avoid circular imports.
"""
import os
import logging
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

# Create the SQLAlchemy extension instance
db = SQLAlchemy(model_class=Base)

# Add custom JSONB handling for SQLite compatibility
class JSONBType:
    """
    JSONB type adapter for SQLite compatibility
    
    This provides a simple substitute for the PostgreSQL JSONB type when using SQLite
    It uses the SQLAlchemy Text type with JSON serialization/deserialization
    """
    import json
    from sqlalchemy import Text
    
    @classmethod
    def load_dialect_impl(cls, dialect):
        # Use Text type for SQLite
        if dialect.name == 'sqlite':
            return dialect.type_descriptor(cls.Text)
        from sqlalchemy.dialects.postgresql import JSONB
        return dialect.type_descriptor(JSONB)
    
    @classmethod
    def process_bind_param(cls, value, dialect):
        # Serialize to JSON string for SQLite
        if dialect.name == 'sqlite' and value is not None:
            return cls.json.dumps(value)
        return value
    
    @classmethod
    def process_result_value(cls, value, dialect):
        # Deserialize from JSON string for SQLite
        if dialect.name == 'sqlite' and value is not None:
            return cls.json.loads(value)
        return value