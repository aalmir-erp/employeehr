# Import the Flask app from app.py
from app import app

# Make sure app is accessible for gunicorn
# Note: This is the app referenced in the .replit workflow/gunicorn command

# If running directly, start the server
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
