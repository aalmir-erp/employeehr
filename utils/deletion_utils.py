"""
Utilities for safely deleting database records with complex relationships.
"""
from datetime import datetime
from flask import current_app
from sqlalchemy import func, delete, text

from db import db
from models import AttendanceRecord, AttendanceLog



# from sqlalchemy import text
# from flask import current_app

def safe_delete_attendance_records_logs(employee_id=None, from_date=None, to_date=None):
    """
    Safely delete attendance records, logs, and linked notifications.
    """
    # try:
    if 1:
        params = {}
        where_conditions = ["1=1"]

        if employee_id:
            where_conditions.append("employee_id = :employee_id")
            params["employee_id"] = employee_id

        if from_date and to_date:
            where_conditions.append("DATE(timestamp) BETWEEN :from_date AND :to_date")
            params["from_date"] = from_date
            params["to_date"] = to_date

        where_clause = " AND ".join(where_conditions)

        # Step 1: Delete related notifications first
        delete_notifications_sql = f"""
            DELETE FROM attendance_notification
            WHERE attendance_log_id IN (
                SELECT id FROM attendance_log WHERE {where_clause}
            )
        """
        result = db.session.execute(text(delete_notifications_sql), params)
        db.session.commit()
        notifications_count = result.rowcount
        current_app.logger.info(f"🗑 Deleted {notifications_count} attendance notifications")

        # Step 2: Unlink logs from attendance records
        unlink_sql = f"""
            UPDATE attendance_log
            SET attendance_record_id = NULL
            WHERE {where_clause}
        """
        result = db.session.execute(text(unlink_sql), params)
        db.session.commit()
        unlinked_count = result.rowcount
        current_app.logger.info(f"✅ Unlinked {unlinked_count} attendance logs")

        # Step 3: Delete attendance records
        record_conditions = ["1=1"]
        if employee_id:
            record_conditions.append("employee_id = :employee_id")
        elif from_date and to_date:
            record_conditions.append("date BETWEEN :from_date AND :to_date")
        else:
            current_app.logger.info("Something went worng we can not delete all records")
            raise


        record_clause = " AND ".join(record_conditions)
        delete_records_sql = f"DELETE FROM attendance_record WHERE {record_clause}"
        result = db.session.execute(text(delete_records_sql), params)
        db.session.commit()
        records_count = result.rowcount
        current_app.logger.info(f"🗑 Deleted {records_count} attendance records")

        # Step 4: Delete logs now that they’re unlinked and notifications removed
        delete_logs_sql = f"DELETE FROM attendance_log WHERE {where_clause}"
        result = db.session.execute(text(delete_logs_sql), params)
        db.session.commit()
        logs_count = result.rowcount
        current_app.logger.info(f"🗑 Deleted {logs_count} attendance logs")

        current_app.logger.info(
            f"✅ Done: Records={records_count}, Logs={logs_count}, Notifications={notifications_count}"
        )
        # return records_count, logs_count, notifications_count
        return records_count, logs_count


    # except Exception as e:
    #     db.session.rollback()
    #     current_app.logger.error(f"❌ Error in safe_delete_attendance_records_logs: {str(e)}")
    #     raise


def safe_delete_attendance_records_logs_old(employee_id=None, from_date=None, to_date=None):
    """
    Safely delete attendance records and logs with proper relationship handling.
    
    Args:
        employee_id: Optional employee ID to filter by
        from_date: Optional start date to filter by (inclusive)
        to_date: Optional end date to filter by (inclusive)
        
    Returns:
        Tuple of (deleted_records_count, deleted_logs_count)
    """
    try:
        # Use SQL to solve session attachment issues in complex Flask app
        # Step 1: Reset attendance_record_id in logs first to avoid foreign key issues
        update_logs_sql = """
        UPDATE attendance_log SET attendance_record_id = NULL 
        WHERE 1=1
        """
        params = {}
        
        if employee_id:
            update_logs_sql += " AND employee_id = :employee_id"
            params['employee_id'] = employee_id
        
        if from_date and to_date:
            update_logs_sql += " AND DATE(timestamp) BETWEEN :from_date AND :to_date"
            params['from_date'] = from_date
            params['to_date'] = to_date
            
        result = db.session.execute(text(update_logs_sql), params)
        db.session.commit()
        unlinked_count = result.rowcount
        current_app.logger.info(f"Unlinked {unlinked_count} logs from attendance records")
        
        # Step 2: Delete attendance records
        delete_records_sql = """
        DELETE FROM attendance_record WHERE 1=1
        """
        
        if employee_id:
            delete_records_sql += " AND employee_id = :employee_id"
        
        if from_date and to_date:
            delete_records_sql += " AND date BETWEEN :from_date AND :to_date"
            
        result = db.session.execute(text(delete_records_sql), params)
        db.session.commit()
        records_count = result.rowcount
        current_app.logger.info(f"Deleted {records_count} attendance records")
        
        # Step 3: Delete attendance logs (now that they're unlinked)
        delete_logs_sql = """
        DELETE FROM attendance_log WHERE 1=1
        """
        
        if employee_id:
            delete_logs_sql += " AND employee_id = :employee_id"
        
        if from_date and to_date:
            delete_logs_sql += " AND DATE(timestamp) BETWEEN :from_date AND :to_date"
            
        result = db.session.execute(text(delete_logs_sql), params)
        db.session.commit()
        logs_count = result.rowcount
        current_app.logger.info(f"Deleted {logs_count} attendance logs")
        
        return records_count, logs_count
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in safe_delete_attendance_records_logs: {str(e)}")
        raise e