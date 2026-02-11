from datetime import date
from utils.overtime_engine import process_attendance_records
from models import AttendanceLog, db

def process_single_attendance_log(attendance_log_id):
    log = AttendanceLog.query.get(attendance_log_id)
    if not log or log.is_processed:
        return False

    process_attendance_records(
        date_from=log.timestamp.date(),
        date_to=log.timestamp.date(),
        employee_id=log.employee_id,
        recalculate=True
    )

    log.is_processed = True
    db.session.commit()
    return True
