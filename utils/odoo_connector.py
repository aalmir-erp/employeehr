import logging
import psycopg2
import psycopg2.extras
import json
from datetime import datetime
from flask import current_app
from app import db
from models import Employee, User, OdooMapping, OdooConfig

logger = logging.getLogger(__name__)

class OdooConnector:
    def __init__(self, app=None):
        self.app = app
        self.connection = None
        self.cursor = None
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        self.app = app
    
    def connect(self):
        """Establish connection to Odoo PostgreSQL database"""
        try:
            # Try to get connection settings from OdooConfig first
            config = OdooConfig.query.first()
            
            if config:
                print (config, "config 1")
                host = config.host
                port = config.port
                user = config.user
                password = config.password
                database = config.database
                host = 'sib.mir.ae'
                port = '5432'
                user = 'odoo9'
                password = 'odoo9'
                database = 'aalmir__2025_05_06'
                

                # Log connection parameters (mask password)
                logger.info(f"Connecting to Odoo database at {host}:{port} with user {user} for database {database}")
            else:
                print ( "no confih")
                # Fall back to app config
                host = current_app.config.get('ODOO_HOST')
                port = current_app.config.get('ODOO_PORT')
                user = current_app.config.get('ODOO_USER')
                password = current_app.config.get('ODOO_PASSWORD')
                database = current_app.config.get('ODOO_DATABASE')
                
                # Log fallback usage
                logger.info(f"No OdooConfig found, falling back to app config: {host}:{port}")
            
            # Validate connection parameters
            if not host or not port or not user or not password or not database:
                missing = []
                if not host: missing.append("host")
                if not port: missing.append("port")
                if not user: missing.append("user")
                if not password: missing.append("password")
                if not database: missing.append("database")
                
                logger.error(f"Missing required Odoo connection parameters: {', '.join(missing)}")
                return False
            
            logger.info(f"Attempting connection to Odoo PostgreSQL at {host}:{port}...")
            self.connection = psycopg2.connect(
    "host=sib.mir.ae port=5432 dbname=aalmir__2025_05_06 user=odoo9 password=odoo9"
)
            # self.connection = psycopg2.connect(
            #     host=host,
            #     port=port,
            #     user=user,
            #     password=password,
            #     database=database
            # )
            self.cursor = self.connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
            logger.info("Successfully connected to Odoo database")
            
            # Update last_sync in config if it exists
            if config:
                config.last_sync = datetime.utcnow()
                db.session.commit()
                
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Odoo database: {str(e)}")
            logger.exception("Detailed exception information:")
            return False
    
    def disconnect(self):
        """Close connection to Odoo database"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        self.cursor = None
        self.connection = None
        logger.info("Disconnected from Odoo database")
    
    def get_available_odoo_fields(self):
        """Get a list of available fields in Odoo's employee table"""
        if not self.connect():
            return []
        
        try:
            # Query the information schema to get column names from hr_employee
            self.cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'hr_employee'
                ORDER BY column_name
            """)
            
            columns = [row['column_name'] for row in self.cursor.fetchall()]
            return columns
        except Exception as e:
            logger.error(f"Error getting Odoo field names: {str(e)}")
            return []
        finally:
            self.disconnect()
    
    def build_dynamic_query(self):
        """Build a dynamic SQL query based on field mappings"""
        # Get active field mappings
        mappings = OdooMapping.query.filter_by(is_active=True).all()
        
        if not mappings:
            # Default query if no mappings exist
            return """
                SELECT 
                    e.id as odoo_id,
                    e.name_related as name,
                    e.work_phone,
                    e.work_email,
                    e.mobile_phone,
                    p.name as department_name,
                    j.name as job_name,
                    e.create_date as join_date,
                    e.active
                FROM hr_employee e
                LEFT JOIN hr_department p ON e.department_id = p.id
                LEFT JOIN hr_job j ON e.job_id = j.id
                WHERE e.active = true;
            """
        
        # Build dynamic select statement
        field_selects = ["e.id as odoo_id"]  # Always include odoo_id
        
        for mapping in mappings:
            if mapping.odoo_field in ['job_id']:
                continue  # This is handled specially via joins
            
            field_selects.append(f"e.{mapping.odoo_field}")
        
        # Always include job_id field for joins
        # Note: We don't use department_id directly anymore as we store department name
        if "job_id" not in [m.odoo_field for m in mappings]:
            field_selects.append("e.job_id")
            
        # Add department and job names
        field_selects.append("p.name as department_name")
        field_selects.append("j.name as job_name")
        
        # Build the query
        query = f"""
            SELECT 
                {', '.join(field_selects)}
            FROM hr_employee e
            LEFT JOIN hr_department p ON e.department_id = p.id
            LEFT JOIN hr_job j ON e.job_id = j.id
            WHERE e.active = true
        """
        
        return query
    
    def sync_employees(self):
        """Sync employee data from Odoo to local database using dynamic field mappings"""
        if not self.connect():
            logger.error("Could not connect to Odoo database for employee sync")
            return False
        
        try:
            # Build and execute the dynamic query
            query = self.build_dynamic_query()
            self.cursor.execute(query)
            
            employees_data = self.cursor.fetchall()
            sync_count = 0
            
            # Get field mappings for applying to employee model
            mappings = {m.odoo_field: m.employee_field for m in OdooMapping.query.filter_by(is_active=True).all()}
            
            for emp_data in employees_data:
                # Check if employee exists in our database
                employee = Employee.query.filter_by(odoo_id=emp_data['odoo_id']).first()
                
                if employee:
                    # Update existing employee with standard fields
                    if 'name' in emp_data:
                        employee.name = emp_data['name']
                    if 'department_name' in emp_data:
                        employee.department = emp_data['department_name']
                    if 'job_name' in emp_data:
                        employee.position = emp_data['job_name']
                        
                    # Update phone number for WhatsApp OTP if available
                    if 'mobile_phone' in emp_data and emp_data['mobile_phone']:
                        employee.phone = emp_data['mobile_phone']
                    elif 'work_phone' in emp_data:
                        employee.phone = emp_data['work_phone']
                        
                    if 'active' in emp_data:
                        employee.is_active = emp_data['active']
                    
                    # Apply any dynamic mapped fields
                    for odoo_field, employee_field in mappings.items():
                        if odoo_field in emp_data and hasattr(employee, employee_field):
                            setattr(employee, employee_field, emp_data[odoo_field])
                    
                    employee.last_sync = datetime.utcnow()
                else:
                    # Create new employee with default required fields
                    employee_data = {
                        'odoo_id': emp_data['odoo_id'],
                        'name': emp_data.get('name', 'Unknown'),
                        'department': emp_data.get('department_name'),
                        'position': emp_data.get('job_name'),
                        'is_active': emp_data.get('active', True),
                        'employee_code': f"EMP{emp_data['odoo_id']:04d}"
                    }
                    
                    # Set phone for WhatsApp OTP (prefer mobile over work phone)
                    if 'mobile_phone' in emp_data and emp_data['mobile_phone']:
                        employee_data['phone'] = emp_data['mobile_phone']
                    elif 'work_phone' in emp_data:
                        employee_data['phone'] = emp_data['work_phone']
                        
                    if 'join_date' in emp_data:
                        employee_data['join_date'] = emp_data['join_date']
                    
                    # Apply any dynamic mapped fields
                    for odoo_field, employee_field in mappings.items():
                        if odoo_field in emp_data:
                            employee_data[employee_field] = emp_data[odoo_field]
                    
                    employee = Employee(**employee_data)
                    db.session.add(employee)
                
                sync_count += 1
            
            db.session.commit()
            
            # Update OdooConfig last_sync time
            config = OdooConfig.query.first()
            if config:
                config.last_sync = datetime.utcnow()
                db.session.commit()
                
            logger.info(f"Successfully synced {sync_count} employees from Odoo")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error syncing employees from Odoo: {str(e)}")
            return False
        finally:
            self.disconnect()
    
    def sync_departments(self):
        """Sync department data from Odoo to local database"""
        if not self.connect():
            return False
        
        try:
            # Query Odoo's hr.department table
            self.cursor.execute("""
                SELECT 
                    id,
                    name,
                    active
                FROM hr_department
            """)
            
            departments_data = self.cursor.fetchall()
            logger.info(f"Retrieved {len(departments_data)} departments from Odoo")
            
            # Process departments as needed
            # This could be extended to create a Department model and store data
            
            return True
            
        except Exception as e:
            logger.error(f"Error syncing departments from Odoo: {str(e)}")
            return False
        finally:
            self.disconnect()
    
    def get_employee_leaves(self, employee_odoo_id):
        """Get employee leave records from Odoo"""
        if not self.connect():
            return []
        
        try:
            # Query Odoo's hr.holidays table for leave records
            self.cursor.execute("""
                SELECT 
                    id,
                    employee_id,
                    date_from,
                    date_to,
                    holiday_status_id,
                    state
                FROM hr_holidays
                WHERE employee_id = %s AND state = 'validate' 
                    AND type = 'remove'
            """, (employee_odoo_id,))
            
            leaves_data = self.cursor.fetchall()
            return leaves_data
            
        except Exception as e:
            logger.error(f"Error fetching employee leaves from Odoo: {str(e)}")
            return []
        finally:
            self.disconnect()

# Create a global instance of the connector
odoo_connector = OdooConnector()
