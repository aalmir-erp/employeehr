from apscheduler.schedulers.background import BackgroundScheduler
from datetime import date
from utils.overtime_engine import process_attendance_records
from utils.attendance_processor import process_unprocessed_logs

scheduler = BackgroundScheduler()

def process_attendance_job(app):
    with app.app_context():
        print(" process_attendance_job started ")
        process_unprocessed_logs(date_from=date.today())

def init_scheduler_custom(app):
    scheduler.add_job(
        func=process_attendance_job,
        args=[app],              # pass app explicitly
        trigger="interval",
        minutes=1,
        id="attendance_processor",
        replace_existing=True
    )
    scheduler.start()
