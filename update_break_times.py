#!/usr/bin/env python3
"""
Script to back-fill break_start and break_end fields for existing records.
Uses the midpoint of the work period for records with existing break_duration.
"""
import os
import sys
from datetime import datetime, timedelta

def main():
    """Main function to execute the update"""
    # Import within function to avoid circular imports
    from models import AttendanceRecord
    from app import app, db
    # Count records that need updating
    query = AttendanceRecord.query.filter(
        AttendanceRecord.check_in.isnot(None),
        AttendanceRecord.check_out.isnot(None),
        AttendanceRecord.break_duration > 0,
        AttendanceRecord.break_start.is_(None),
        AttendanceRecord.break_end.is_(None)
    )
    
    total_records = query.count()
    print(f"Found {total_records} records that need break times updated")
    
    # Process in batches to avoid memory issues with large datasets
    batch_size = 100
    processed = 0
    
    while processed < total_records:
        batch = query.limit(batch_size).all()
        if not batch:
            break
        
        for record in batch:
            # Calculate work period duration in hours
            work_period = (record.check_out - record.check_in).total_seconds() / 3600
            
            # Set default break start time at midpoint of work period
            midpoint = record.check_in + timedelta(hours=work_period / 2)
            
            # Adjust break start to be in the middle of the work period
            # minus half the break duration
            break_start = midpoint - timedelta(hours=record.break_duration / 2)
            
            # Break end time is break start plus break duration
            break_end = break_start + timedelta(hours=record.break_duration)
            
            # Update the record
            record.break_start = break_start
            record.break_end = break_end
        
        # Commit the batch
        db.session.commit()
        processed += len(batch)
        print(f"Processed {processed}/{total_records} records")
    
    print("Update completed successfully")

if __name__ == "__main__":
    # Import here to avoid circular dependencies
    from app import app
    
    with app.app_context():
        main()