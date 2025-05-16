# MIR AMS - Attendance Management System

## Installation Guide for Ubuntu

This guide will help you set up the MIR Attendance Management System on an Ubuntu server.

### Prerequisites

- Ubuntu 20.04 or newer
- Python 3.8 or newer
- PostgreSQL 12 or newer
- Git

### Step 1: Install Required System Packages

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib git
```

### Step 2: Create a PostgreSQL Database

```bash
sudo -u postgres psql -c "CREATE USER mir_ams WITH PASSWORD 'your_secure_password';"
sudo -u postgres psql -c "CREATE DATABASE mir_ams OWNER mir_ams;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE mir_ams TO mir_ams;"
```

### Step 3: Clone the Repository (When you have a Git repository)

```bash
git clone <your-repository-url>
cd mir-ams
```

### Step 4: Create and Activate a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 5: Install Python Dependencies

```bash
pip install -r requirements.txt
```

If no requirements.txt file exists, install the required packages manually:

```bash
pip install flask flask-login flask-sqlalchemy flask-migrate flask-wtf psycopg2-binary apscheduler email-validator python-dateutil pyzk requests twilio gunicorn
```

### Step 6: Set Up Environment Variables

Create a `.env` file in the project root directory:

```bash
echo "DATABASE_URL=postgresql://mir_ams:your_secure_password@localhost/mir_ams" > .env
echo "FLASK_APP=main.py" >> .env
echo "FLASK_DEBUG=0" >> .env
echo "FLASK_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(16))')" >> .env

# If using Wassenger for WhatsApp OTP
echo "WASSENGER_API_KEY=your_wassenger_api_key" >> .env

# If using Twilio for SMS
echo "TWILIO_ACCOUNT_SID=your_twilio_account_sid" >> .env
echo "TWILIO_AUTH_TOKEN=your_twilio_auth_token" >> .env
echo "TWILIO_PHONE_NUMBER=your_twilio_phone_number" >> .env

# If using ZKTeco devices directly
echo "DEVICE_API_KEY=your_device_api_key" >> .env
```

### Step 7: Set Up the Database

```bash
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

### Step 8: Create Initial Admin User

Start the application and navigate to `/auth/setup` in your web browser, or use the provided setup route.

### Step 9: Run with Gunicorn (Production)

```bash
gunicorn --bind 0.0.0.0:5000 --workers 4 main:app
```

### Step 10: Set Up as a System Service (Optional)

Create a systemd service file:

```bash
sudo nano /etc/systemd/system/mir-ams.service
```

Add the following content:

```
[Unit]
Description=MIR Attendance Management System
After=network.target

[Service]
User=<your-username>
WorkingDirectory=/path/to/mir-ams
EnvironmentFile=/path/to/mir-ams/.env
ExecStart=/path/to/mir-ams/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 main:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl enable mir-ams.service
sudo systemctl start mir-ams.service
```

### Step 11: Set Up Nginx as a Reverse Proxy (Optional)

```bash
sudo apt install -y nginx
```

Create a Nginx configuration:

```bash
sudo nano /etc/nginx/sites-available/mir-ams
```

Add the following content:

```
server {
    listen 80;
    server_name your_domain.com; # or your server IP

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the site and restart Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/mir-ams /etc/nginx/sites-enabled
sudo systemctl restart nginx
```

### Step 12: Set Up SSL with Let's Encrypt (Optional)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your_domain.com
```

## Troubleshooting

### Database Connection Issues

If you encounter database connection issues:

1. Ensure PostgreSQL is running:
   ```bash
   sudo systemctl status postgresql
   ```

2. Check your `.env` file to ensure DATABASE_URL is correct

3. Make sure the database user has proper permissions:
   ```bash
   sudo -u postgres psql -c "ALTER USER mir_ams WITH PASSWORD 'your_secure_password';"
   sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE mir_ams TO mir_ams;"
   ```

### Python Module Issues

If you encounter issues with Python modules:

```bash
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### ZKTeco Device Connection Issues

If you have trouble connecting to biometric devices:

1. Ensure the device is on the same network
2. Check if the correct IP and port are configured
3. Run the test connection script:
   ```bash
   python direct_zk_test.py <device_ip_address>
   ```
