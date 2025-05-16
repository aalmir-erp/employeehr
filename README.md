# MIR Attendance Management System (MIR AMS)

A comprehensive Flask-based attendance management system for 24/7 factory operations, providing advanced workforce tracking and management solutions with enhanced scalability and integration capabilities.

## Key Features

- Biometric attendance tracking with ZKTeco device integration
- Employee management with Odoo synchronization
- Work shift management and scheduling
- Comprehensive attendance reporting
- WhatsApp OTP login authentication
- Role-based access control
- Dark/light theme support
- Mobile-responsive design

## Git Setup and Deployment

### Initial Setup with GitHub

1. **Create a new repository on GitHub**
   - Go to GitHub and create a new repository at: https://github.com/aalmir-erp/employeehr.git
   - Don't initialize with README, .gitignore, or license files

2. **Clone the repository locally**
   ```bash
   git clone https://github.com/aalmir-erp/employeehr.git
   cd employeehr
   ```

3. **Copy project files to this directory**
   - Copy all files from your current project to this directory
   - Make sure to exclude files listed in .gitignore

4. **Add, commit, and push to GitHub**
   ```bash
   git add .
   git commit -m "Initial commit: MIR AMS Attendance System"
   git push -u origin main
   ```

### Dealing with Migration Issues

If you encounter a `DuplicateColumn` error during the database migration (as shown in the error log for the `force_password_change` column), you can use the provided `fix_migration.py` script:

```bash
# Run the migration fix tool
python fix_migration.py

# Or you can manually modify your migration file to check if column exists first
```

### Deployment on Ubuntu Server

1. **Clone your repository on the server**
   ```bash
   cd /opt/mir-ams
   git clone https://github.com/aalmir-erp/employeehr.git .
   ```

2. **Set up the environment**
   ```bash
   # Run the setup scripts
   chmod +x setup_dependencies.sh setup_database.sh
   ./setup_dependencies.sh
   ./setup_database.sh
   
   # Set up database migrations
   source venv/bin/activate
   flask db init
   flask db migrate -m "Initial migration"
   
   # If you encounter the duplicate column error, run the fix tool
   python fix_migration.py
   
   # Then run the upgrade
   flask db upgrade
   ```

3. **Create a systemd service for automatic startup**
   ```bash
   sudo nano /etc/systemd/system/mir-ams.service
   ```
   
   Add the following content:
   ```
   [Unit]
   Description=MIR Attendance Management System
   After=network.target postgresql.service
   
   [Service]
   User=www-data
   Group=www-data
   WorkingDirectory=/opt/mir-ams
   Environment="PATH=/opt/mir-ams/venv/bin"
   EnvironmentFile=/opt/mir-ams/.env
   ExecStart=/opt/mir-ams/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 main:app
   Restart=always
   
   [Install]
   WantedBy=multi-user.target
   ```

4. **Set proper permissions and start the service**
   ```bash
   sudo chown -R www-data:www-data /opt/mir-ams
   sudo systemctl enable mir-ams.service
   sudo systemctl start mir-ams.service
   ```

## System Requirements

- Python 3.8 or higher
- PostgreSQL 12 or higher
- Ubuntu 20.04 or higher (recommended)

## Quick Start Guide

### Installation

1. Clone the repository to your local machine:
   ```bash
   git clone <repository-url>
   cd mir-ams
   ```

2. Run the setup scripts:
   ```bash
   ./setup_dependencies.sh
   ./setup_database.sh
   ```

3. Initialize the database:
   ```bash
   source venv/bin/activate  # If using virtual environment
   flask db init
   flask db migrate -m "Initial migration"
   flask db upgrade
   ```

4. Start the application:
   ```bash
   gunicorn --bind 0.0.0.0:5000 main:app
   ```

5. Access the application at http://localhost:5000 and complete the initial setup.

### Configuration

Configure your application by editing the .env file with:

- Database connection settings
- API keys for WhatsApp integration (Wassenger)
- Twilio credentials for SMS
- Device API keys for ZKTeco integration

## Detailed Documentation

For complete installation and configuration instructions, see [INSTALLATION.md](INSTALLATION.md).

## Key Components

- **Flask web framework** with responsive design
- **Advanced attendance tracking system** with biometric integration
- **Odoo integration** capabilities for employee synchronization
- **Role-based admin and user dashboards**
- **Real-time device and employee synchronization**
- **Database migration** support with Flask-Migrate
- **Scheduled background task management** with APScheduler

## Security Features

- Password hashing with Werkzeug security
- WhatsApp OTP authentication
- Role-based access control
- Force password change capability
- Session management

## License

[Your License Information]

## Support

[Your Support Information]
