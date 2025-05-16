#!/bin/bash

# This script packages the MIR AMS project for distribution

# Function to display script usage
usage() {
  echo "Usage: $0 [OPTIONS]"
  echo "Package the MIR AMS project for distribution"
  echo ""
  echo "Options:"
  echo "  -h, --help              Display this help message"
  echo "  -o, --output FILENAME   Output filename (default: mir-ams.tar.gz)"
  echo "  -e, --exclude-venv      Exclude virtual environment (recommended)"
  echo ""
  exit 1
}

# Default values
OUTPUT_FILE="mir-ams.tar.gz"
EXCLUDE_VENV=true

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help)
      usage
      ;;
    -o|--output)
      OUTPUT_FILE="$2"
      shift 2
      ;;
    -e|--exclude-venv)
      EXCLUDE_VENV=true
      shift
      ;;
    --include-venv)
      EXCLUDE_VENV=false
      shift
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

# Clean up old package if it exists
if [ -f "$OUTPUT_FILE" ]; then
  echo "Removing existing package $OUTPUT_FILE"
  rm "$OUTPUT_FILE"
fi

# Create a list of files to exclude
EXCLUDE_LIST=()
EXCLUDE_LIST+=("__pycache__")
EXCLUDE_LIST+=("*.pyc")
EXCLUDE_LIST+=("*.pyo")
EXCLUDE_LIST+=("*.pyd")
EXCLUDE_LIST+=("*.db")
EXCLUDE_LIST+=("*.sqlite")
EXCLUDE_LIST+=("*.log")
EXCLUDE_LIST+=("*.tar.gz")
EXCLUDE_LIST+=("*.zip")
EXCLUDE_LIST+=("*.tgz")
EXCLUDE_LIST+=("*.bak")
EXCLUDE_LIST+=("*~")
EXCLUDE_LIST+=("_tmp_*")
EXCLUDE_LIST+=("tmp*")
EXCLUDE_LIST+=(".git")

# Add virtual environment to exclude list if needed
if [ "$EXCLUDE_VENV" = true ]; then
  EXCLUDE_LIST+=("venv")
  EXCLUDE_LIST+=(".venv")
fi

# Build the exclude arguments for tar
EXCLUDE_ARGS=()
for item in "${EXCLUDE_LIST[@]}"; do
  EXCLUDE_ARGS+=("--exclude=$item")
done

# Create the documentation directory
if [ ! -d "docs" ]; then
  mkdir -p docs
fi

# Package the project
echo "Packaging project to $OUTPUT_FILE..."
tar -czf "$OUTPUT_FILE" "${EXCLUDE_ARGS[@]}" .

if [ $? -eq 0 ]; then
  echo "Package created successfully: $OUTPUT_FILE"
  echo "Size: $(du -h "$OUTPUT_FILE" | cut -f1)"
  echo ""
  echo "To deploy this package:"
  echo "1. Copy $OUTPUT_FILE to your target server"
  echo "2. Extract it: tar -xzf $OUTPUT_FILE"
  echo "3. Run setup scripts:"
  echo "   ./setup_dependencies.sh"
  echo "   ./setup_database.sh"
  echo "4. Initialize the database:"
  echo "   flask db init"
  echo "   flask db migrate -m 'Initial migration'"
  echo "   flask db upgrade"
  echo "5. Start the application:"
  echo "   gunicorn --bind 0.0.0.0:5000 main:app"
else
  echo "Error creating package"
  exit 1
fi
