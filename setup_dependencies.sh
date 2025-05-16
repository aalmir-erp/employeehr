#!/bin/bash

# This script installs all required dependencies for the MIR AMS system

# Function to display script usage
usage() {
  echo "Usage: $0 [OPTIONS]"
  echo "Install dependencies for MIR AMS"
  echo ""
  echo "Options:"
  echo "  -h, --help          Display this help message"
  echo "  -v, --virtualenv    Create and use a Python virtual environment (recommended)"
  echo "  -s, --system        Install dependencies system-wide (requires sudo)"
  echo ""
  exit 1
}

# Default options
USE_VENV=true
SYSTEM_WIDE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help)
      usage
      ;;
    -v|--virtualenv)
      USE_VENV=true
      shift
      ;;
    -s|--system)
      SYSTEM_WIDE=true
      USE_VENV=false
      shift
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

# Check if running as root when installing system-wide
if [ "$SYSTEM_WIDE" = true ] && [ "$(id -u)" != "0" ]; then
  echo "Error: System-wide installation requires sudo privileges."
  echo "Run with sudo or use the --virtualenv option instead."
  exit 1
fi

# Install system dependencies
echo "===== Installing system dependencies ====="
if [ "$(id -u)" = "0" ]; then
  apt update
  apt install -y python3 python3-pip python3-venv postgresql postgresql-contrib git
else
  echo "Not running as root, skipping system package installation."
  echo "Make sure the following packages are installed:"
  echo "  - python3"
  echo "  - python3-pip"
  echo "  - python3-venv"
  echo "  - postgresql"
  echo "  - postgresql-contrib"
  echo "  - git"
fi

# Set up Python environment
if [ "$USE_VENV" = true ]; then
  echo "\n===== Setting up Python virtual environment ====="
  python3 -m venv venv
  source venv/bin/activate
  echo "Virtual environment created and activated."
  PIP="venv/bin/pip"
else
  echo "\n===== Using system Python ====="
  PIP="pip3"
fi

# Install Python dependencies
echo "\n===== Installing Python dependencies ====="
$PIP install --upgrade pip

# These are the core dependencies for MIR AMS
echo "Installing Flask and related packages..."
$PIP install flask flask-login flask-sqlalchemy flask-migrate flask-wtf

echo "Installing database drivers..."
$PIP install psycopg2-binary

echo "Installing utility packages..."
$PIP install apscheduler email-validator python-dateutil python-dotenv pytest requests

echo "Installing device integration packages..."
$PIP install pyzk

echo "Installing messaging packages..."
$PIP install twilio

echo "Installing server packages..."
$PIP install gunicorn

# Create a sample .env file
if [ ! -f .env ]; then
  echo "\n===== Creating sample .env file ====="
  cat > .env << EOL
# Database configuration
DATABASE_URL=postgresql://username:password@localhost/mir_ams

# Flask configuration
FLASK_APP=main.py
FLASK_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(16))')

# WhatsApp integration (Wassenger)
WASSENGER_API_KEY=your_wassenger_api_key

# Twilio configuration (for SMS)
#TWILIO_ACCOUNT_SID=your_twilio_account_sid
#TWILIO_AUTH_TOKEN=your_twilio_auth_token
#TWILIO_PHONE_NUMBER=your_twilio_phone_number

# ZKTeco device configuration
#DEVICE_API_KEY=your_device_api_key
EOL
  echo "Created sample .env file. Make sure to update it with your actual configuration."
fi

echo "\n===== Dependencies installation complete ====="
if [ "$USE_VENV" = true ]; then
  echo "To activate the virtual environment in the future, run:"
  echo "  source venv/bin/activate"
fi

echo "\nNext steps:"
echo "1. Update the .env file with your database and API credentials"
echo "2. Initialize the database:" 
echo "   flask db init"
echo "   flask db migrate -m 'Initial migration'"
echo "   flask db upgrade"
echo "3. Start the application:"
echo "   gunicorn --bind 0.0.0.0:5000 main:app"
echo ""
echo "For more details, see INSTALLATION.md"
