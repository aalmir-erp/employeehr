"""
Process overtime for attendance records.

Examples:
    python process_overtime.py --date 2026-04-02
    python process_overtime.py --date-from 2026-04-01 --date-to 2026-04-30
    python process_overtime.py --date 2026-04-02 --employee-id 1458
"""
import argparse
import os
from datetime import datetime

os.environ.setdefault("DISABLE_APP_BACKGROUND_SERVICES", "true")

from main import app  # Import the Flask app
from app import db
from models import Employee
from utils.overtime_engine import process_attendance_records


def parse_date(value):
    """Parse a YYYY-MM-DD date argument."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Date must be in YYYY-MM-DD format") from exc


def build_parser():
    parser = argparse.ArgumentParser(
        description="Recalculate overtime for attendance records."
    )
    parser.add_argument(
        "--date",
        type=parse_date,
        help="Recalculate one attendance date, for example 2026-04-02.",
    )
    parser.add_argument(
        "--date-from",
        type=parse_date,
        help="Start date for recalculation, inclusive.",
    )
    parser.add_argument(
        "--date-to",
        type=parse_date,
        help="End date for recalculation, inclusive. Defaults to --date-from.",
    )
    parser.add_argument(
        "--employee-id",
        type=int,
        help="Optional employee id if only one employee should be recalculated.",
    )
    parser.add_argument(
        "--skip-shift-update",
        action="store_true",
        help="Skip updating employees' current shift assignments after recalculation.",
    )
    return parser


def resolve_date_range(args):
    if args.date and (args.date_from or args.date_to):
        raise SystemExit("Use either --date or --date-from/--date-to, not both.")

    if args.date:
        return args.date, args.date

    if args.date_from:
        return args.date_from, args.date_to or args.date_from

    if args.date_to:
        raise SystemExit("--date-to requires --date-from.")

    return None, None


def main():
    """Main function to execute the script."""
    args = build_parser().parse_args()
    date_from, date_to = resolve_date_range(args)

    if date_from and date_to and date_from > date_to:
        raise SystemExit("--date-from cannot be after --date-to.")

    scope = "all attendance records"
    if date_from and date_to:
        scope = f"attendance records from {date_from} to {date_to}"
    if args.employee_id:
        scope += f" for employee_id={args.employee_id}"

    print(f"Processing overtime calculations for {scope}...")

    # Use the Flask application context
    with app.app_context():
        count = process_attendance_records(
            date_from=date_from,
            date_to=date_to,
            employee_id=args.employee_id,
            recalculate=True,
        )
        print(f"Successfully processed {count} attendance records")

        if not args.skip_shift_update:
            update_current_shifts()

    print("Done!")


def update_current_shifts():
    """Update employee current_shift_id based on latest assignments."""
    from models import ShiftAssignment

    print("Updating employee current shifts...")

    try:
        # Get all employees
        employees = Employee.query.all()
        update_count = 0

        for employee in employees:
            # Get the most recent shift assignment
            latest_assignment = ShiftAssignment.query.filter(
                ShiftAssignment.employee_id == employee.id,
                ShiftAssignment.is_active == True
            ).order_by(ShiftAssignment.start_date.desc()).first()

            if latest_assignment and latest_assignment.shift_id != employee.current_shift_id:
                employee.current_shift_id = latest_assignment.shift_id
                db.session.add(employee)
                update_count += 1

        # Commit all changes
        db.session.commit()
        print(f"Updated current shift for {update_count} employees")
    except Exception as e:
        db.session.rollback()
        print(f"Error updating current shifts: {str(e)}")


if __name__ == "__main__":
    main()
