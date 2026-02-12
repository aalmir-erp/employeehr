from apscheduler.schedulers.background import BackgroundScheduler
from datetime import date
from utils.overtime_engine import process_attendance_records

scheduler = BackgroundScheduler()

def process_attendance_job(app):
    with app.app_context():
        print(" process_attendance_job started ")
        process_attendance_records(date_from=date.today())

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
