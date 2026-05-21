from apscheduler.schedulers.background import BackgroundScheduler
from datetime import date, datetime, timedelta

# from google.auth import message

from utils.overtime_engine import process_attendance_records
from utils.attendance_processor import process_unprocessed_logs, mark_absent_for_past_dates
from models import BonusEvaluationPeriod,db, BonusSubmission, BonusEvaluation, Employee, PayrollStatus, AttendanceRecord, Department, BonusAuditLog,\
    AttendanceNotification,User
# from extensions import db
from calendar import monthrange
import requests
from sqlalchemy import distinct, func
# from sqlalchemy import func


def bonus_submission_daily_job(app):
    with app.app_context():
        today = datetime.utcnow()
        day = today.day

        # get all draft submissions
        submissions = BonusSubmission.query.filter_by(status='draft').all()

        for submission in submissions:

            # 🔔 15–20 → remind supervisor
            if 15 <= day <= 24:
                supervisors = User.query.filter_by(
                    department=submission.department,
                    role='supervisor',
                    account_active=True
                ).all()

                for sup in supervisors:
                    db.session.add(
                        AttendanceNotification(
                            # attendance_log_id=None,
                            employee_id=sup.employee_id or 0,
                            role='supervisor',
                            message=(
                                f"Reminder: Bonus submission is pending "
                                f"for department '{submission.department}' "
                                f"(Period {submission.period.name})."
                            )
                        )
                    )
                    print(" added notification ")

            # ✅ After 20 → auto-submit
            elif day > 20:
                submission.status = 'submitted'
                submission.submitted_at = today
                submission.updated_at = today

        db.session.commit()


scheduler = BackgroundScheduler()


scheduler.start()

# -------------------------------
# EXISTING JOB (runs every minute)
# -------------------------------
def process_attendance_job(app):
    with app.app_context():
        print("process_attendance_job started")
        process_unprocessed_logs(date_from=date(2026, 2, 1))


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

# ----------------------------------------
# NEW JOB (runs on 10th of every month)
# ----------------------------------------

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

        # print("Evaluation period created:", period_name)



ODOO_PAYROLL_URL = "http://localhost:8070/payroll/fetch_payroll_id"

def fetch_payroll_from_odoo_job(app):
    with app.app_context():
        print("fetch_payroll_from_odoo_job started")

        submissions = BonusSubmission.query.filter_by(
            is_open_fetch=True
        ).all()

        if not submissions:
            print("No open fetch submissions")
            return

        for submission in submissions:

            #  Fetch employee + odoo_id
            rows = (
                db.session.query(
                    distinct(BonusEvaluation.employee_id),
                    Employee.odoo_id
                )
                .join(Employee, Employee.id == BonusEvaluation.employee_id)
                .filter(BonusEvaluation.submission_id == submission.id)
                .all()
            )

            if not rows:
                print(f"No employees for submission {submission.id}")
                submission.is_open_fetch = False
                db.session.commit()
                continue

            overtime_data = []
            for emp_id, odoo_id in rows:
                if not odoo_id:
                    print(f"Skipping employee {emp_id} (no odoo_id)")
                    continue

                overtime_data.append({
                    "employee_id": odoo_id,  # Odoo employee ID
                    "id": emp_id             # Local employee ID
                })

            if not overtime_data:
                print(f"No valid employees for submission {submission.id}")
                submission.is_open_fetch = False
                db.session.commit()
                continue

            # Build payload (MATCHES UI EXACTLY)
            from_date='2026-02-01'
            to_date= '2026-02-28'
            payload = {
                "employee_ids": overtime_data,
                "run_id": 350,  # keep same as UI
                "from_date": from_date, # submission.period.start_date.isoformat(),
                "to_date": to_date, #submission.period.end_date.isoformat()
            }

            print("Sending payload to Odoo:", payload)
            # 9/0

            try:
                response = requests.post(
                    ODOO_PAYROLL_URL,
                    json=payload,
                    timeout=60
                )

                if response.status_code == 200:
                    print(f"Payroll fetch success for submission {submission.id}")

                    # 3️⃣ CLOSE FLAG (CRITICAL)
                    submission.is_open_fetch = False
                    submission.bonus_pushed = False
                    db.session.commit()
                else:
                    print(
                        f"Odoo error for submission {submission.id}",
                        response.status_code,
                        response.text
                    )
                odoo_response = response.json()
                print("---------------------------------------------------------")

                payroll_data = odoo_response.get('result', [])

                # print
                print(payroll_data, "payroll_data =========")
                for item in payroll_data:
                    try:
                        odoo_id = item['employee_id']
                        payroll_number = item['payroll_number']
                        payroll_id = item['payroll_id']
                        payroll_date = datetime.strptime(item['payroll_date'], '%Y-%m-%d').date()
                        state = item['state']

                        # Optional: prevent duplicates (e.g., same emp, same payroll_id)
                        print("odoo_id", odoo_id)
                        employee = Employee.query.filter_by(odoo_id=odoo_id).first()
                        print(employee, "payroll_id", payroll_id)
                        print(payroll_number, "payroll_number ==")
                        existing = PayrollStatus.query.filter_by(employee_id=employee.id,
                                                                 payroll_id_odoo=payroll_id).first()
                        if existing:
                            print(" already existing reacird for payrol for this EMP")
                            continue  # Skip existing record

                        new_status = PayrollStatus(
                            employee_id=employee.id,
                            payroll_id_odoo=payroll_id,
                            payroll_name=payroll_number,
                            payroll_date=payroll_date,
                            odoo_status='pending',
                            status='created'
                        )
                        db.session.add(new_status)
                    except Exception as e:
                        print("❌ Error processing item:", item)
                        print("Error:", e)
                    #     print(" error  here  =========")
                    #     print (odoo_id, "odoo_id")
                    #     print("payroll_number", payroll_number)
                    #     print(payroll_id, "payroll_id")
                    #     continue

                db.session.commit()

                return {'message': 'Payroll status records saved successfully.', 'count': len(payroll_data)}
            except Exception as e:
                print("❌ Error processing item:", item)

HR_USER_IDS = [17]  # 👈 hardcoded HR user IDs

def bonus_hr_review_reminder_job(app):
    with app.app_context():

        today = datetime.utcnow()
        day = today.day

        # Only run between 20–25
        if not (20 <= day <= 25):
            return

        submitted_submissions = BonusSubmission.query.filter_by(
            status='submitted'
        ).all()

        for submission in submitted_submissions:
            approved_users = submission.approvers or []

            # HR users who have NOT approved
            pending_hr_users = [
                uid for uid in HR_USER_IDS
                if uid not in approved_users
            ]

            if not pending_hr_users:
                continue

            for hr_user_id in pending_hr_users:
                hr_user = User.query.get(hr_user_id)
                if not hr_user or not hr_user.account_active:
                    continue
                message = (
                            f"Bonus submission pending HR review.\n"
                            f"Department: {submission.department}\n"
                            f"Period: {submission.period.name}"
                        )
                db.session.add(
                    AttendanceNotification(
                        attendance_log_id=None,
                        employee_id=hr_user.employee_id,
                        role='hr',
                        message=message
                    )
                )
                data = []
                data.append({
                    'emps': hr_user.employee.odoo_id,
                    'message': message,
                    'subject': 'Bonus submission pending'
                })

                requests.post("http://localhost:8070/notify_odoo_user_from_ams", json={'users': data}, timeout=3)

        # in review ==================================
        submitted_submissions = BonusSubmission.query.filter_by(
            status='in_review'
        ).all()


        for submission in submitted_submissions:

            hr_user_id = 49 # YAsmin User ID
            hr_user = User.query.get(hr_user_id)

            db.session.add(
                AttendanceNotification(
                    attendance_log_id=None,
                    employee_id=hr_user.employee_id,
                    role='hr',
                    message=(
                        f"Bonus submission pending Your review.\n"
                        f"Department: {submission.department}\n"
                        f"Period: {submission.period.name}"
                    )
                )
            )

        db.session.commit()

# -------------------------------
# SCHEDULER INITIALIZATION
# -------------------------------
def init_scheduler_custom(app):
    pass
    # scheduler.add_job(
    #     func=bonus_hr_review_reminder_job,
    #     trigger='interval',
    #     args=[app],
    #     minutes=1,  # every hour (safe)
    #     id='bonus_hr_review_reminder',
    #     replace_existing=False
    # )
    # scheduler.add_job(
    #     func=mark_absent_daily,
    #     args=[app],
    #     trigger="interval",
    #     minutes=5,
    #     id="attendance_processor_absent",
    #     replace_existing=False
    # )

    # Interval job (every 1 minute)
    # scheduler.add_job(
    #     func=process_attendance_job,
    #     args=[app],
    #     trigger="interval",
    #     minutes=1,
    #     id="attendance_processor",
    #     replace_existing=True
    # )
    # scheduler.add_job(
    #     func=bonus_submission_daily_job,
    #     trigger='interval',
    #     args=[app],
    #     # hour=9,  # runs every day at 9 AM
    #     minutes=1,
    #     id='bonus_submission_daily',
    #     replace_existing=False
    # )

    # Cron job (10th of every month at 00:05)
    # scheduler.add_job(
    #     func=monthly_bonus_cron,
    #     args=[app],
    #     trigger="interval",
    #     # day=10,
    #     # hour=0,
    #     minutes=1,
    #     id="monthly_bonus_period",
    #     replace_existing=True
    # )
    # # Payroll fetch job (every 5 minutes)
    # scheduler.add_job(
    #     func=fetch_payroll_from_odoo_job,
    #     args=[app],
    #     trigger="interval",
    #     minutes=1,
    #     id="payroll_fetch_job",
    #     replace_existing=True
    # )
    #
    # scheduler.add_job(
    #     func=auto_push_bonus_after_payroll,
    #     args=[app],
    #     trigger="interval",
    #     minutes=10,
    #     id="auto_bonus_push",
    #     replace_existing=True
    # )

    # scheduler.add_job(
    #     args=[app],
    #     func=fetch_employee_dob_and_update_password,
    #     trigger='interval',  # can also use 'cron' trigger
    #     minutes=1,  # runs once a day
    #     id='update_employee_passwords1',
    #     replace_existing=False
    # )
    # scheduler.start()



def fetch_employee_dob_and_update_password(app):
    with app.app_context():

        print("Cron job started: Fetching DOBs from Odoo...")
        ODOO_API_URL = "http://localhost:8070/get_employees_for_dob"
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



def auto_push_bonus_after_payroll(app):
    with app.app_context():
        print("auto_push_bonus_after_payroll started")

        submissions = BonusSubmission.query.filter_by(
            is_open_fetch=False,   # payroll already fetched
            status="approved"
        ).all()

        submissions = BonusSubmission.query.filter(
            BonusSubmission.is_open_fetch == False,  # payroll already fetched
            BonusSubmission.status == "approved",
            BonusSubmission.bonus_pushed == False  # bonus not pushed yet
        ).all()

        for submission in submissions:

            rows = (
                db.session.query(
                    Employee.id.label("emp_id"),
                    Employee.employee_code,
                    Employee.odoo_id,
                    func.sum(BonusEvaluation.value).label("bonus_point"),
                    func.max(PayrollStatus.id).label("payslip_id")
                )
                .join(BonusEvaluation, BonusEvaluation.employee_id == Employee.id)
                .join(PayrollStatus, PayrollStatus.employee_id == Employee.id)
                .filter(BonusEvaluation.submission_id == submission.id)
                .group_by(Employee.id, Employee.employee_code, Employee.odoo_id)
                .all()
            )

            if not rows:
                continue

            employees = [
                {
                    "emp_id": r.emp_id,
                    "employee_code": r.employee_code,
                    "odoo_id": r.odoo_id,
                    "bonus_point": r.bonus_point or 0,
                    "payslip_id": r.payslip_id
                }
                for r in rows
                if r.odoo_id and r.payslip_id
            ]

            if not employees:
                continue

            action_dict = {
                "is_bonus": True,
                "is_overtime": False,
                "is_leave": True
            }

            success = push_bonus_overtime_to_odoo(
                employees=employees,
                from_date=submission.period.start_date,
                to_date=submission.period.end_date,
                action_dict=action_dict
            )

            # if success:
            if success:
                submission.bonus_pushed = True
                db.session.commit()
                print(f"Bonus pushed for submission {submission.id}")


ODOO_UPDATE_URL = "https://localhost:8070/update_overtime_from_ams"

def push_bonus_overtime_to_odoo(
    employees,
    from_date,
    to_date,
    action_dict
):
    """
    employees = list of dicts:
    [
        {
            emp_id,
            employee_code,
            odoo_id,
            bonus_point,
            payslip_id
        }
    ]
    """

    absent = []

    for item in employees:
        emp_id = item["emp_id"]

        # ❌ Safety check
        if not item.get("payslip_id"):
            print(f"Skipping emp {emp_id} (no payslip)")
            continue

        empl_absent = AttendanceRecord.query.filter(
            AttendanceRecord.employee_id == emp_id,
            AttendanceRecord.date >= from_date,
            AttendanceRecord.date <= to_date,
            AttendanceRecord.status == "absent"
        ).all()

        for record in empl_absent:
            employee = Employee.query.get(record.employee_id)
            if not employee or not employee.odoo_id:
                continue

            absent.append({
                "odoo_employee_id": employee.odoo_id,
                "leave_date_str": str(record.date)
            })

    payload = {
        "payroll": employees,
        "absent": absent,
        "action_dict": action_dict
    }

    print("Sending bonus/overtime payload to Odoo")

    response = requests.post(
        ODOO_UPDATE_URL,
        json=payload,
        timeout=300
    )

    return response.status_code == 200