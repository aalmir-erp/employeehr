import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from html import escape

from sqlalchemy.orm import joinedload

from models import AttendanceRecord, Employee, User, db
from services.odoo_mail_service import send_email_via_odoo
from utils.attendance_processor import mark_absent_for_past_dates, process_unprocessed_logs
from utils.overtime_engine import process_attendance_records

logger = logging.getLogger(__name__)

# Fixed recipients can be edited here if preferred, or provided as a comma-separated
# ATTENDANCE_REPORT_CC environment variable.
DEFAULT_ATTENDANCE_REPORT_CC = [
    # "hr@company.com",
    # "ops@company.com",
]
DEFAULT_ATTENDANCE_REPORT_FROM = None

ISSUE_STATUSES = {
    "absent",
    "missing",
    "missing_in",
    "missing_out",
    "in_progress",
    "pending",
    "no_record",
}

EXCEPTION_STATUSES = {
    "absent",
    "late",
    "half-day",
    "missing",
    "missing_in",
    "missing_out",
    "in_progress",
    "pending",
    "no_record",
}


def _parse_email_list(value):
    if not value:
        return []
    if isinstance(value, str):
        normalized = value.replace(";", ",").replace("\n", ",")
        candidates = normalized.split(",")
    else:
        candidates = value
    return [email.strip() for email in candidates if email and email.strip()]


def _configured_cc_recipients():
    env_recipients = _parse_email_list(os.environ.get("ATTENDANCE_REPORT_CC", ""))
    return env_recipients or DEFAULT_ATTENDANCE_REPORT_CC


def _configured_email_from():
    return os.environ.get("ODOO_ATTENDANCE_EMAIL_FROM") or DEFAULT_ATTENDANCE_REPORT_FROM


def _format_datetime(value):
    return value.strftime("%Y-%m-%d %H:%M") if value else "-"


def _format_hours(value):
    return f"{float(value or 0):.2f}"


def _safe_status(record):
    if not record:
        return "no_record"
    return record.status or "pending"


def _classify_shift(record, employee):
    shift_name = None
    shift_type = None
    check_in = None

    if record:
        shift_name = record.shift.name if record.shift else None
        shift_type = (record.shift_type or "").lower()
        check_in = record.check_in

    if not shift_name and employee and employee.current_shift:
        shift_name = employee.current_shift.name

    normalized_shift_name = (shift_name or "").lower()

    if "night" in normalized_shift_name or shift_type == "night":
        return "Night Shift"

    if "day" in normalized_shift_name or shift_type == "day":
        return "Day Shift"

    if check_in:
        if check_in.hour >= 18 or check_in.hour < 6:
            return "Night Shift"
        if 6 <= check_in.hour < 18:
            return "Day Shift"

    return "Other / Unknown Shift"




def _attendance_record_rank(record):
    """Rank duplicate records so reports prefer the most complete row."""
    return (
        0 if record.check_in else 1,
        0 if record.check_out else 1,
        0 if record.status != "absent" else 1,
        -(max(
            record.updated_at.timestamp() if record.updated_at else 0,
            record.created_at.timestamp() if record.created_at else 0,
        )),
        -record.id,
    )

def _record_has_exception(record):
    if not record:
        return True
    status = _safe_status(record)
    return (
        status in EXCEPTION_STATUSES
        or record.check_in is None
        or record.check_out is None
    )


def _department_supervisor_emails(department):
    supervisors = User.query.filter(
        User.role == "supervisor",
        User.department == department,
        User.account_active.is_(True),
        User.email.isnot(None),
        User.email != "",
    ).order_by(User.username).all()
    return [supervisor.email for supervisor in supervisors]


def ensure_attendance_ready(report_date):
    """Run the existing attendance processing pipeline before report creation."""
    processing_from = report_date
    processing_to = report_date + timedelta(days=1)

    records_created, logs_processed = process_unprocessed_logs(
        date_from=processing_from,
        date_to=processing_to,
    )

    # Ensure yesterday-only missing records are created before we email supervisors.
    mark_absent_for_past_dates(report_date, report_date)

    overtime_processed = process_attendance_records(
        date_from=report_date,
        date_to=report_date,
        recalculate=True,
    )

    db.session.commit()

    return {
        "records_created": records_created,
        "logs_processed": logs_processed,
        "overtime_processed": overtime_processed,
    }


def _load_department_report_data(report_date):
    employees = Employee.query.options(
        joinedload(Employee.current_shift)
    ).filter_by(is_active=True).order_by(Employee.department, Employee.name).all()

    records = AttendanceRecord.query.options(
        joinedload(AttendanceRecord.employee),
        joinedload(AttendanceRecord.shift),
    ).filter(AttendanceRecord.date == report_date).order_by(AttendanceRecord.id).all()

    records_by_employee = {}
    for record in records:
        existing = records_by_employee.get(record.employee_id)
        if existing is None or _attendance_record_rank(record) < _attendance_record_rank(existing):
            records_by_employee[record.employee_id] = record

    departments = defaultdict(lambda: {
        "rows": [],
        "shift_groups": defaultdict(list),
        "exceptions": [],
        "summary": defaultdict(float),
    })

    for employee in employees:
        department = employee.department or "Unassigned Department"
        record = records_by_employee.get(employee.id)
        shift_group = _classify_shift(record, employee)
        status = _safe_status(record)

        row = {
            "employee_code": employee.employee_code or str(employee.id),
            "employee_name": employee.name or "-",
            "department": department,
            "shift_group": shift_group,
            "shift_name": (record.shift.name if record and record.shift else (employee.current_shift.name if employee.current_shift else "-")),
            "check_in": _format_datetime(record.check_in) if record else "-",
            "check_out": _format_datetime(record.check_out) if record else "-",
            "status": status,
            "late_minutes": record.late_minutes if record else 0,
            "work_hours": record.work_hours if record else 0,
            "break_duration": record.break_duration if record else 0,
            "overtime_hours": record.overtime_hours if record else 0,
            "notes": record.notes if record and record.notes else "",
            "is_missing_punch": bool(record and (record.check_in is None or record.check_out is None) and status != "absent"),
        }

        is_issue_row = (status in ISSUE_STATUSES) or row["is_missing_punch"]

        if not is_issue_row:
            continue

        dept_data = departments[department]
        dept_data["rows"].append(row)
        dept_data["shift_groups"][shift_group].append(row)

        summary = dept_data["summary"]
        summary["total_issues"] += 1
        summary[status] += 1
        if row["is_missing_punch"]:
            summary["missing_punch"] += 1

        if _record_has_exception(record):
            dept_data["exceptions"].append(row)

    return departments


def _summary_value(summary, key):
    value = summary.get(key, 0)
    if key in {"work_hours", "overtime_hours"}:
        return f"{value:.2f}"
    return str(int(value))


def _build_summary_html(summary):
    summary_items = [
        ("Total Issues", "total_issues"),
        ("Absent", "absent"),
        ("Missing Punch", "missing_punch"),
        ("No Record", "no_record"),
            ]

    cells = "".join(
        f"""
        <td style=\"padding:10px;border:1px solid #ddd;text-align:center;\">
            <div style=\"font-size:12px;color:#666;\">{escape(label)}</div>
            <div style=\"font-size:20px;font-weight:bold;\">{escape(_summary_value(summary, key))}</div>
        </td>
        """
        for label, key in summary_items
    )
    return f"<table style=\"border-collapse:collapse;margin-bottom:18px;\"><tr>{cells}</tr></table>"


def _build_rows_table(rows):
    if not rows:
        return "<p>No employees in this section.</p>"

    body_rows = []
    for row in rows:
        body_rows.append(
            f"""
            <tr>
                <td>{escape(row['employee_code'])}</td>
                <td>{escape(row['employee_name'])}</td>
                <td>{escape(row['shift_name'])}</td>
                <td>{escape(row['check_in'])}</td>
                <td>{escape(row['check_out'])}</td>
                <td>{escape(row['status'])}</td>
                <td style=\"text-align:right;\">{int(row['late_minutes'] or 0)}</td>
                <td style=\"text-align:right;\">{_format_hours(row['work_hours'])}</td>
                <td style=\"text-align:right;\">{_format_hours(row['break_duration'])}</td>
                <td style=\"text-align:right;\">{_format_hours(row['overtime_hours'])}</td>
            </tr>
            """
        )

    return f"""
    <table style=\"border-collapse:collapse;width:100%;margin-bottom:20px;\">
        <thead>
            <tr style=\"background:#f1f5f9;\">
                <th>Code</th>
                <th>Name</th>
                <th>Shift</th>
                <th>Check In</th>
                <th>Check Out</th>
                <th>Status</th>
                <th>Late Min</th>
                <th>Work Hrs</th>
                <th>Break Hrs</th>
                <th>OT Hrs</th>
            </tr>
        </thead>
        <tbody>{''.join(body_rows)}</tbody>
    </table>
    """


def _build_exceptions_table(rows):
    if not rows:
        return "<p>No exceptions found.</p>"

    body_rows = []
    for row in rows:
        issue_parts = []
        if row["status"] == "no_record":
            issue_parts.append("No attendance record")
        if row["status"] in EXCEPTION_STATUSES and row["status"] != "no_record":
            issue_parts.append(row["status"])
        if row["is_missing_punch"]:
            issue_parts.append("Missing punch")
        issue = ", ".join(issue_parts) or "Exception"

        body_rows.append(
            f"""
            <tr>
                <td>{escape(row['employee_code'])}</td>
                <td>{escape(row['employee_name'])}</td>
                <td>{escape(row['shift_group'])}</td>
                <td>{escape(row['check_in'])}</td>
                <td>{escape(row['check_out'])}</td>
                <td>{escape(issue)}</td>
            </tr>
            """
        )

    return f"""
    <table style=\"border-collapse:collapse;width:100%;margin-bottom:20px;\">
        <thead>
            <tr style=\"background:#fee2e2;\">
                <th>Code</th>
                <th>Name</th>
                <th>Shift Group</th>
                <th>Check In</th>
                <th>Check Out</th>
                <th>Issue</th>
            </tr>
        </thead>
        <tbody>{''.join(body_rows)}</tbody>
    </table>
    """


def build_department_report_html(department, department_data, report_date):
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    sections = []

    for shift_group in ["Day Shift", "Night Shift", "Other / Unknown Shift"]:
        rows = department_data["shift_groups"].get(shift_group, [])
        sections.append(f"<h3>{escape(shift_group)}</h3>{_build_rows_table(rows)}")

    return f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; color: #1f2937; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; font-size: 13px; }}
            th {{ text-align: left; }}
            h2 {{ margin-bottom: 4px; }}
            h3 {{ margin-top: 24px; color: #0f172a; }}
        </style>
    </head>
    <body>
        <h2>Daily Attendance Report</h2>
        <p>
            <strong>Department:</strong> {escape(department)}<br>
            <strong>Report Date:</strong> {report_date.isoformat()}<br>
            <strong>Generated At:</strong> {escape(generated_at)}
        </p>

        <h3>Summary</h3>
        {_build_summary_html(department_data['summary'])}

        {''.join(sections)}

        <h3>Exceptions</h3>
        {_build_exceptions_table(department_data['exceptions'])}
    </body>
    </html>
    """


def send_daily_attendance_reports(report_date=None, ensure_ready=True):
    """Send one department-wise daily attendance report email per department."""
    if report_date is None:
        report_date = date.today() - timedelta(days=1)

    processing_result = None
    if ensure_ready:
        processing_result = ensure_attendance_ready(report_date)
        logger.info("Attendance processing before email report completed: %s", processing_result)

    departments = _load_department_report_data(report_date)
    cc_recipients = _configured_cc_recipients()
    email_cc = ",".join(cc_recipients)
    email_from = _configured_email_from()

    results = []
    for department, department_data in sorted(departments.items()):
        supervisor_emails = _department_supervisor_emails(department)

        if not supervisor_emails:
            results.append({
                "department": department,
                "success": False,
                "error": "No active supervisor email configured for department",
            })
            logger.warning("Skipping attendance email for %s: no supervisor email", department)
            continue

        subject = f"Daily Attendance Report - {department} - {report_date.isoformat()}"
        body_html = build_department_report_html(department, department_data, report_date)

        result = send_email_via_odoo(
            subject=subject,
            body_html=body_html,
            email_to=",".join(supervisor_emails),
            email_cc=email_cc,
            email_from=email_from,
        )
        result["department"] = department
        result["email_to"] = supervisor_emails
        result["email_cc"] = cc_recipients
        results.append(result)

        if result.get("success"):
            logger.info("Sent attendance report for %s via Odoo mail %s", department, result.get("mail_id"))
        else:
            logger.error("Failed attendance report for %s: %s", department, result.get("error"))

    return {
        "report_date": report_date.isoformat(),
        "processing": processing_result,
        "departments": results,
    }
