import csv
import io
import re
from datetime import datetime
import logging

logging.basicConfig(level=logging.DEBUG)

def parse_zkteco_csv(file_path):
    """Parse the ZKTeco CSV file format and extract attendance data"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            reader = csv.reader(file)
            records = []
            
            # Debug information
            logging.debug("Starting to parse CSV file")
            
            # First check if this is the complex MIR report format
            first_row = next(reader, None)
            file.seek(0)  # Reset file pointer
            reader = csv.reader(file)
            
            is_mir_format = False
            if first_row and len(first_row) > 0 and first_row[0] == "Event Viewer Report":
                is_mir_format = True
                logging.info("Detected MIR Event Viewer Report format")
            
            # Process each row
            for row_idx, row in enumerate(reader):
                if not row or len(row) < 3:
                    continue
                    
                logging.debug(f"Row {row_idx}: Processing row with length {len(row)}")
                
                try:
                    # Special handling for MIR format rows
                    if is_mir_format:
                        # Extract data from the row
                        employee_id = None
                        employee_name = None
                        event_type = None
                        punch_timestamp = None
                        
                        # Extract employee ID from "Employee ID:" field
                        for i in range(len(row) - 1):
                            if row[i] == "Employee ID:":
                                employee_id = row[i + 1].strip()
                                break
                        
                        # Extract employee name from "Employee Name:" field
                        for i in range(len(row) - 1):
                            if row[i] == "Employee Name:":
                                raw_name = row[i + 1].strip()
                                employee_name = ''.join(c for c in raw_name if ord(c) < 128)
                                break
                        
                        # Find the event type (IN/OUT)
                        for i in range(len(row)):
                            if row[i] == "IN" or row[i] == "OUT":
                                event_type = row[i]
                                break
                        
                        # We have two patterns to handle:
                        # 1. DD-MMM-YY  HH:MM am/pm directly in the cell
                        # 2. One cell has the date (01-Mar-25) and another cell has time (08:23 am)
                        
                        # First try to find a complete timestamp in a single cell
                        complete_timestamp_found = False
                        for i in range(len(row)):
                            value = row[i].strip()
                            if re.match(r'\d{2}-[A-Za-z]{3}-\d{2}\s+\d{1,2}:\d{2}\s*[ap]m', value):
                                punch_timestamp = value
                                complete_timestamp_found = True
                                break
                        
                        # If not found, try to find separate date and time cells
                        if not complete_timestamp_found:
                            # Find date (01-Mar-25 format)
                            date_str = None
                            time_str = None
                            
                            for i in range(len(row)):
                                value = row[i].strip()
                                # Check for date in format 01-Mar-25
                                if re.match(r'\d{2}-[A-Za-z]{3}-\d{2}$', value):
                                    date_str = value
                                # Check for time in format 08:23 am
                                elif re.match(r'\d{1,2}:\d{2}\s*[ap]m$', value):
                                    time_str = value
                            
                            # If found both, combine them
                            if date_str and time_str:
                                punch_timestamp = f"{date_str}  {time_str}"
                                logging.debug(f"Combined timestamp: {punch_timestamp}")
                        
                        # Check for direct date values in the format that doesn't need parsing
                        date_value = None
                        for i in range(len(row)):
                            if row[i] == "Date":
                                if i+1 < len(row) and re.match(r'\d{2}-[A-Za-z]{3}-\d{2}$', row[i+1]):
                                    date_value = row[i+1]
                                    break
                        
                        # If we have a date_value and event type, try to find punch timestamp
                        if date_value and event_type and not punch_timestamp:
                            # Try to find punch next to "Punch" header
                            for i in range(len(row) - 1):
                                if row[i] == "Punch":
                                    # The next value might be the timestamp
                                    time_match = re.search(r'(\d{1,2}:\d{2}\s*[ap]m)', row[i+1])
                                    if time_match:
                                        time_str = time_match.group(1)
                                        punch_timestamp = f"{date_value}  {time_str}"
                                        logging.debug(f"Extracted timestamp from Punch field: {punch_timestamp}")
                                    break
                        
                        # If we found all required fields, create a record
                        if employee_id and event_type and punch_timestamp:
                            # Normalize the timestamp - fix common issues
                            cleaned_timestamp = punch_timestamp.strip()
                            # Ensure there's a space before am/pm
                            cleaned_timestamp = re.sub(r'(\d)([ap]m)', r'\1 \2', cleaned_timestamp)
                            # Standardize multiple spaces
                            cleaned_timestamp = re.sub(r'\s+', ' ', cleaned_timestamp)
                            
                            # Try different formats
                            formats_to_try = [
                                '%d-%b-%y  %I:%M %p',     # Double space with AM/PM (01-Mar-25  08:23 am)
                                '%d-%b-%y %I:%M %p',      # Single space with AM/PM
                                '%d-%b-%y  %I:%M%p',      # No space before am/pm
                                '%d-%b-%y %I:%M%p',       # Single space, no space before am/pm
                            ]
                            
                            timestamp = None
                            for fmt in formats_to_try:
                                try:
                                    timestamp = datetime.strptime(cleaned_timestamp, fmt)
                                    break
                                except ValueError:
                                    continue
                            
                            if timestamp:
                                logging.debug(f"Row {row_idx}: {employee_id}, {employee_name}, {event_type}, {timestamp}")
                            else:
                                logging.warning(f"Could not parse timestamp '{punch_timestamp}'")
                        else:
                            if not employee_id:
                                logging.warning(f"Row {row_idx}: Missing employee ID")
                            if not event_type:
                                logging.warning(f"Row {row_idx}: Missing event type")
                            if not punch_timestamp:
                                logging.warning(f"Row {row_idx}: Missing timestamp")
                    
                except Exception as e:
                    logging.error(f"Error processing row {row_idx}: {str(e)}")
                    continue
            
            logging.info(f"Done processing file")
    except Exception as e:
        logging.error(f"Fatal error parsing CSV: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    parse_zkteco_csv('/tmp/import.csv')