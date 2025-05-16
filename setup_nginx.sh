#!/bin/bash

# This script sets up Nginx as a reverse proxy for the MIR AMS application

# Function to display script usage
usage() {
  echo "Usage: $0 [OPTIONS]"
  echo "Set up Nginx as a reverse proxy for MIR AMS"
  echo ""
  echo "Options:"
  echo "  -h, --help              Display this help message"
  echo "  -d, --domain DOMAIN      Domain name to use (required)"
  echo "  -p, --port PORT          Application port (default: 5000)"
  echo "  -s, --ssl                Set up SSL with Let's Encrypt"
  echo ""
  exit 1
}

# Default values
APP_PORT=5000
USE_SSL=false
DOMAIN=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help)
      usage
      ;;
    -d|--domain)
      DOMAIN="$2"
      shift 2
      ;;
    -p|--port)
      APP_PORT="$2"
      shift 2
      ;;
    -s|--ssl)
      USE_SSL=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

# Check if domain is provided
if [ -z "$DOMAIN" ]; then
  echo "Error: Domain name is required"
  usage
fi

# Check if running as root or with sudo
if [ "$(id -u)" != "0" ]; then
  echo "Error: This script must be run as root or with sudo"
  exit 1
fi

# Check if nginx is installed
if ! command -v nginx &> /dev/null; then
  echo "Nginx is not installed. Installing..."
  apt update
  apt install -y nginx
fi

# Create nginx configuration file
echo "Creating Nginx configuration for $DOMAIN..."
cat > /etc/nginx/sites-available/mir-ams << EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Enable the site
echo "Enabling the site..."
ln -sf /etc/nginx/sites-available/mir-ams /etc/nginx/sites-enabled/

# Test Nginx configuration
echo "Testing Nginx configuration..."
nginx -t

if [ $? -ne 0 ]; then
  echo "Error: Nginx configuration test failed"
  exit 1
fi

# Reload Nginx
echo "Reloading Nginx..."
systemctl reload nginx

# Set up SSL if requested
if [ "$USE_SSL" = true ]; then
  echo "Setting up SSL with Let's Encrypt..."
  
  # Check if certbot is installed
  if ! command -v certbot &> /dev/null; then
    echo "Certbot is not installed. Installing..."
    apt update
    apt install -y certbot python3-certbot-nginx
  fi
  
  # Request certificate
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email webmaster@"$DOMAIN"
  
  if [ $? -ne 0 ]; then
    echo "Error: Failed to obtain SSL certificate"
    exit 1
  fi
  
  echo "SSL setup complete!"
fi

echo "\nNginx setup complete!"
echo "Your application is now accessible at:"
if [ "$USE_SSL" = true ]; then
  echo "  https://$DOMAIN"
else
  echo "  http://$DOMAIN"
fi
echo ""
echo "To set up SSL later, run this script with the --ssl flag"
echo ""
