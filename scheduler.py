from apscheduler.schedulers.background import BackgroundScheduler
from utils.overtime_engine import process_attendance_records
from utils.attendance_processor import process_unprocessed_logs, mark_absent_for_past_dates
import requests
from sqlalchemy import distinct, func
from datetime import date, datetime
from models import BonusEvaluationPeriod,db, BonusSubmission, BonusEvaluation, Employee, PayrollStatus, AttendanceRecord, Department, BonusAuditLog,\
    AttendanceNotification,User

scheduler = BackgroundScheduler()

def process_attendance_job(app):
    with app.app_context():
        print(" process_attendance_job started ")
        process_unprocessed_logs(date_from=date.today())



def mark_absent_daily(app):
    with app.app_context():

        yesterday = datetime.utcnow().date() - timedelta(days=1)

        print(f"CRON - Marking absents for {yesterday}")

        try:
            mark_absent_for_past_dates(
                date_from=yesterday,
                date_to=yesterday
            )
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"CRON ERROR - Absent job failed: {e}")




def fetch_employee_dob_and_update_password(app):
    with app.app_context():

        print("Cron job started: Fetching DOBs from Odoo...")
        ODOO_API_URL = "https://erp.mir.ae/get_employees_for_dob"
        payload ={"token":7676767}
        try:
            res = requests.post(
                ODOO_API_URL, json=payload,
                timeout=10
            )
            res.raise_for_status()
            data_list = res.json()['result'] # assuming Odoo returns list of employees
        except Exception as e:
            print(f"Failed to fetch employees from Odoo: {e}")
            return

        # Loop through employees
        cutoff_date = datetime(2026, 2, 10)

        for data in data_list:
            employee_odoo_id = data.get('id')  # Odoo employee ID
            dob = data.get('dob')  # format: 'YYYY-MM-DD'
            email = data.get('email')
            phone = data.get('phone')

            if not dob:
                print(f"No DOB for Odoo employee {employee_odoo_id}, skipping...")
                continue

            # Convert DOB to ddmmyyyy
            dob_clean = datetime.strptime(dob, '%Y-%m-%d').strftime('%d%m%Y')

            # Find the local employee by odoo_id
            employee = Employee.query.filter_by(odoo_id=employee_odoo_id).first()
            if not employee:
                print(f"No local employee found for Odoo ID {employee_odoo_id}, skipping...")
                continue
            user = User.query.filter(
                User.employee_id == employee.id,
                User.created_at >= cutoff_date
            ).first()
            if not user:
                continue
            else:
                user.set_password(dob_clean)

            print(f"Updated password for employee {employee.id}, DOB: {dob_clean}")

        db.session.commit()
        print("Cron job finished: All employee passwords updated.")



def init_scheduler_custom(app):
    scheduler.add_job(
        func=process_attendance_job,
        args=[app],              # pass app explicitly
        trigger="interval",
        hours=4,                     # every 4 hours
        id="attendance_processor",
        replace_existing=False
    )


    scheduler.add_job(
        func=mark_absent_daily,
        args=[app],
        trigger="interval",
        hours=12,                     # every 12 hours
        id="attendance_processor_absent",
        replace_existing=False
    )

    # scheduler.add_job(
    #     args=[app],
    #     func=fetch_employee_dob_and_update_password,
    #     trigger='interval',  # can also use 'cron' trigger
    #     minutes=1,  # runs once a day
    #     id='update_employee_passwords1',
    #     replace_existing=False
    # )

    scheduler.start()
