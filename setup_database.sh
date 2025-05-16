#!/bin/bash

# This script helps set up the PostgreSQL database for MIR AMS

# Function to display script usage
usage() {
  echo "Usage: $0 [OPTIONS]"
  echo "Set up PostgreSQL database for MIR AMS"
  echo ""
  echo "Options:"
  echo "  -h, --help              Display this help message"
  echo "  -u, --user USERNAME     Database username (default: mir_ams)"
  echo "  -p, --pass PASSWORD     Database password"
  echo "  -d, --db DATABASE       Database name (default: mir_ams)"
  echo "  -f, --force             Force recreation of database and user (caution: data loss)"
  echo ""
  exit 1
}

# Default values
DB_USER="mir_ams"
DB_PASS=""
DB_NAME="mir_ams"
FORCE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help)
      usage
      ;;
    -u|--user)
      DB_USER="$2"
      shift 2
      ;;
    -p|--pass)
      DB_PASS="$2"
      shift 2
      ;;
    -d|--db)
      DB_NAME="$2"
      shift 2
      ;;
    -f|--force)
      FORCE=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

# Check for PostgreSQL
if ! command -v psql &> /dev/null; then
  echo "Error: PostgreSQL is not installed or not in PATH"
  echo "Please install PostgreSQL first:"
  echo "  sudo apt update"
  echo "  sudo apt install -y postgresql postgresql-contrib"
  exit 1
fi

# Generate password if not provided
if [ -z "$DB_PASS" ]; then
  DB_PASS=$(LC_ALL=C tr -dc 'A-Za-z0-9!@#$%^&*()' </dev/urandom | head -c 16)
  echo "No password provided, generated password: $DB_PASS"
fi

# Database operations as postgres user
if [ "$FORCE" = true ]; then
  echo "Force flag set, dropping database and user if they exist..."
  sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;"
  sudo -u postgres psql -c "DROP USER IF EXISTS $DB_USER;"
fi

# Create user if not exists
USER_EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'")
if [ "$USER_EXISTS" != "1" ]; then
  echo "Creating database user $DB_USER..."
  sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
else
  echo "User $DB_USER already exists, updating password..."
  sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASS';"
fi

# Create database if not exists
DB_EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'")
if [ "$DB_EXISTS" != "1" ]; then
  echo "Creating database $DB_NAME..."
  sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
else
  echo "Database $DB_NAME already exists, ensuring correct ownership..."
  sudo -u postgres psql -c "ALTER DATABASE $DB_NAME OWNER TO $DB_USER;"
fi

# Set privileges
echo "Granting privileges..."
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

# Update .env file if it exists
if [ -f .env ]; then
  echo "Updating .env file with database configuration..."
  if grep -q "DATABASE_URL" .env; then
    # Update existing DATABASE_URL
    sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost/$DB_NAME|" .env
  else
    # Add DATABASE_URL if not found
    echo "DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost/$DB_NAME" >> .env
  fi
else
  echo "Creating .env file with database configuration..."
  echo "DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost/$DB_NAME" > .env
fi

echo "\nDatabase setup complete!"
echo "Connection string: postgresql://$DB_USER:$DB_PASS@localhost/$DB_NAME"
echo "This has been saved to your .env file."

echo "\nNext steps:"
echo "1. Initialize the database schema:"
echo "   flask db init"
echo "   flask db migrate -m 'Initial migration'"
echo "   flask db upgrade"
echo "2. Start the application"
echo ""
