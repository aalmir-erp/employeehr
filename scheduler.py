from apscheduler.schedulers.background import BackgroundScheduler
from utils.overtime_engine import process_attendance_records
from utils.attendance_processor import (
    process_unprocessed_logs,
    mark_absent_for_past_dates,
    close_stale_in_progress_records,
)
import requests
from sqlalchemy import distinct, func
from datetime import date, datetime, timedelta
from models import BonusEvaluationPeriod,db, BonusSubmission, BonusEvaluation, Employee, PayrollStatus, AttendanceRecord, Department, BonusAuditLog,\
    AttendanceNotification,User
from services.daily_attendance_report_service import send_daily_attendance_reports



from calendar import monthrange

scheduler = BackgroundScheduler()


def monthly_bonus_cron(app):
    period_id = create_monthly_evaluation_period(app)

    if period_id:
        auto_create_bonus_submissions(app, period_id)

def create_monthly_evaluation_period(app):
    print(" create_monthly_evaluation_period started ")
    with app.app_context():
        today = date.today()
        print("create_monthly_evaluation_period called =======================================")

        year = today.year
        month = today.month

        if today.day < 10:
            # month -= 1
            if month == 0:
                month = 12
                year -= 1

        start_date = date(year, month, 1)
        end_date = date(year, month, monthrange(year, month)[1])
        period_name = start_date.strftime('%B %Y')

        print(start_date, end_date)
        exists = BonusEvaluationPeriod.query.filter_by(
            start_date=start_date,
            end_date=end_date
        ).first()

        if exists:
            print("Evaluation period already exists:", period_name)
            return

        period = BonusEvaluationPeriod(
            name=period_name,
            start_date=start_date,
            end_date=end_date,
            created_by=1  # system/admin
        )

        db.session.add(period)
        db.session.commit()
        period_id = period.id

        return period_id

def auto_create_bonus_submissions(app, period_id):
    with app.app_context():
        print("Auto creating bonus submissions...")

        departments = Department.query.filter_by(is_bonus_allow=True).all()

        for dept in departments:
            # Avoid duplicates
            exists = BonusSubmission.query.filter_by(
                period_id=period_id,
                department=dept.name
            ).first()

            if exists:
                continue

            # Create draft submission
            submission = BonusSubmission(
                period_id=period_id,
                department=dept.name,
                submitted_by=1,  # system
                status='draft'
            )
            db.session.add(submission)
            db.session.commit()

            # Audit log
            log = BonusAuditLog(
                submission_id=submission.id,
                action='created',
                user_id=1,
                notes=f'Auto draft submission created for {dept.name}, period {period_id}'
            )
            db.session.add(log)
            db.session.commit()

            # 🔔 Notify supervisors
            supervisors = User.query.filter_by(
                department=dept.name,
                role='supervisor',
                account_active=True
            ).all()

            for sup in supervisors:
                notification = AttendanceNotification(
                    attendance_log_id=0,  # system event (no attendance log)
                    employee_id=sup.employee_id or 0,
                    role='supervisor',
                    message=(
                        f"Bonus evaluation for '{period_id}' has started "
                        f"for department '{dept.name}'. Please submit evaluations."
                    )
                )
                db.session.add(notification)

            db.session.commit()
            print(f"Submission + notifications done for {dept.name}")

def process_attendance_job(app):
    with app.app_context():
        print(" process_attendance_job started ")
        date_from = date.today() - timedelta(days=2)
        date_to = date.today() - timedelta(days=1)     # yesterday

        process_unprocessed_logs(
            date_from=date_from,
            date_to=date_to
        )

        # process_unprocessed_logs(date_from=date_from)


def cleanup_stale_in_progress_job(app):
    with app.app_context():
        print("CRON - Cleaning stale in_progress attendance records")

        try:
            updated_count = close_stale_in_progress_records(
                hours_old=24,
                checkout_window_hours=24
            )
            print(f"CRON - Stale in_progress cleanup updated {updated_count} records")
        except Exception as e:
            db.session.rollback()
            print(f"CRON ERROR - Stale in_progress cleanup failed: {e}")



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




def send_daily_attendance_report_job(app):
    with app.app_context():
        report_date = date.today() - timedelta(days=1)
        print(f"CRON - Sending daily attendance report for {report_date}")

        try:
            result = send_daily_attendance_reports(report_date=report_date, ensure_ready=True)
            print(f"CRON - Daily attendance report result: {result}")
        except Exception as e:
            db.session.rollback()
            print(f"CRON ERROR - Daily attendance report failed: {e}")



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
    print(" init_scheduler_custom ...... ")
    scheduler.add_job(
        func=process_attendance_job,
        args=[app],              # pass app explicitly
        trigger="interval",
        # hours=4,                     # every 4 hours
        minutes=5,
        id="attendance_processor",
        replace_existing=False
    )


    scheduler.add_job(
        func=cleanup_stale_in_progress_job,
        args=[app],
        trigger="interval",
        hours=1,
        id="attendance_stale_in_progress_cleanup",
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

    scheduler.add_job(
        func=send_daily_attendance_report_job,
        args=[app],
        trigger="cron",
        hour=10,
        minute=30,
        id="daily_attendance_email_report",
        replace_existing=True
    )

    # Cron job (10th of every month at 00:05)
    scheduler.add_job(
        func=monthly_bonus_cron,
        args=[app],
        trigger="interval",
        # day=10,
        # hour=0,
        minutes=5,
        id="monthly_bonus_period",
        replace_existing=True
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
