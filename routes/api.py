from flask import Blueprint, request, jsonify
from datetime import datetime, date, timedelta
import calendar
from collections import defaultdict
import jwt
import os

from app import db
from models import User, Employee, AttendanceRecord, AttendanceLog,UserLoginHistory ,FCMToken,AttendanceDispute ,AttendanceDisputeHistory
from sqlalchemy import func

bp = Blueprint("api", __name__)

# ---------------------------------------------------
# Helpers
# ---------------------------------------------------
def get_date_range(start_date, end_date):
    days = []
    cur = start_date
    while cur <= end_date:
        days.append(cur)
        cur += timedelta(days=1)
    return days


def token_required(fn):
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "message": "Missing token"}), 401

        token = auth_header.split(" ", 1)[1].strip()

        try:
            payload = jwt.decode(token, os.getenv("JWT_SECRET_KEY"), algorithms=["HS256"])
            user = User.query.get(payload.get("user_id"))
            if not user:
                return jsonify({"success": False, "message": "Invalid user"}), 401

            request.current_user = user  # ✅ attach user
        except Exception as e:
            return jsonify({"success": False, "message": "Invalid token", "error": str(e)}), 401

        return fn(*args, **kwargs)

    wrapper.__name__ = fn.__name__
    return wrapper

@bp.route('/fcm_token', methods=['POST'])
def save_fcm_token():
    print("fcm_token calling====================================")
    data = request.json
    user_id = data.get('user_id')
    token = data.get('token')
    print(user_id,token,"======================================")

    if not user_id or not token:
        return jsonify({"error": "Missing user_id or token"}), 400

    existing = FCMToken.query.filter_by(user_id=user_id).first()
    if existing:
        existing.token = token
    else:
        new_token = FCMToken(user_id=user_id, token=token)
        db.session.add(new_token)

    db.session.commit()
    return jsonify({"status": "ok"}) 

@bp.route('/my_disputes', methods=['GET'])
def my_disputes():

    try:
        user_id = request.args.get("user_id")

        if not user_id:
            return jsonify({
                "success": False,
                "message": "User ID required"
            }), 400

        tickets = AttendanceDispute.query.filter_by(
            user_id=user_id
        ).order_by(
            AttendanceDispute.created_at.desc()
        ).all()

        response = []

        for t in tickets:

            # ==========================
            # FETCH HISTORY
            # ==========================
            history_rows = AttendanceDisputeHistory.query.filter_by(
                dispute_id=t.id
            ).order_by(
                AttendanceDisputeHistory.created_at.desc()
            ).all()

            history_list = []

            for h in history_rows:

                user = User.query.get(h.by_user_id)

                employee = None
                if user and user.employee_id:
                    employee = Employee.query.filter_by(
                        id=user.employee_id
                    ).first()

                # IMAGE HANDLING (BASE64)
                if employee and employee.image:
                    image_data = employee.image  # base64 from DB
                else:
                    image_data = None

                history_list.append({
                    "history_id": h.id,
                    "by_user_id": h.by_user_id,
                    "name": employee.name if employee else (user.name if user else "Unknown"),
                    "image": image_data,
                    "remark": h.remark,
                    "status": h.status,
                    "datetime": h.created_at.strftime("%Y-%m-%d %H:%M:%S")
                })

            response.append({
                "id": t.id,
                "date": t.dispute_date.strftime("%Y-%m-%d"),
                "type": t.dispute_type,
                "remarks": t.remarks,
                "status": t.status,
                "history": history_list  # 🔥 added here
            })

        return jsonify({
            "success": True,
            "tickets": response
        })

    except Exception as e:
        print("❌ my_disputes error:", e)
        return jsonify({
            "success": False,
            "message": "Server error"
        }), 500
    
@bp.route('/create_dispute', methods=['POST'])
def create_dispute():

    try:
        data = request.json

        user_id = data.get("user_id")
        dispute_date = data.get("dispute_date")
        dispute_type = data.get("dispute_type")
        remarks = data.get("remarks", "").strip()

        print("📌 Calling create dispute")

        if not user_id or not dispute_date or not dispute_type:
            return jsonify({
                "success": False,
                "message": "Missing fields"
            }), 400

        user = User.query.get(user_id)

        if not user or not user.employee_id:
            return jsonify({
                "success": False,
                "message": "Invalid user"
            }), 400

        # =========================
        # CREATE DISPUTE
        # =========================
        new_ticket = AttendanceDispute(
            user_id=user_id,
            employee_id=user.employee_id,
            dispute_date=datetime.strptime(
                dispute_date, "%Y-%m-%d"
            ).date(),
            dispute_type=dispute_type,
            remarks=remarks,
            status="PENDING"  # default status
        )

        db.session.add(new_ticket)
        db.session.flush()  
        # 🔥 Important: flush to get new_ticket.id before commit

        # =========================
        # INSERT INTO HISTORY
        # =========================
        history = AttendanceDisputeHistory(
            dispute_id=new_ticket.id,
            by_user_id=user_id,
            remark=remarks,
            status="PENDING",
            created_at=datetime.utcnow()
        )

        db.session.add(history)

        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Ticket submitted successfully"
        })

    except Exception as e:
        db.session.rollback()
        print("❌ Create dispute error:", e)

        return jsonify({
            "success": False,
            "message": "Server error"
        }), 500  

# ---------------------------------------------------
# TODAY ATTENDANCE LOG API
# ---------------------------------------------------
@bp.route('/today_attendance_logs', methods=['GET'])
def today_attendance_logs():

    requested_user_id = request.args.get("user_id")

    if not requested_user_id:
        return jsonify({
            "success": False,
            "message": "User ID required"
        }), 400

    target_user = User.query.get(int(requested_user_id))

    if not target_user:
        return jsonify({
            "success": False,
            "message": "User not found"
        }), 404

    if not target_user.employee_id:
        return jsonify({
            "success": False,
            "message": "Employee not linked to user"
        }), 404

    employee = Employee.query.get(target_user.employee_id)

    if not employee:
        return jsonify({
            "success": False,
            "message": "Employee record not found"
        }), 404

    today = date.today()
    start_datetime = datetime.combine(today, datetime.min.time())
    end_datetime = datetime.combine(today, datetime.max.time())

    # 🔹 ASC for duration calculation
    logs = AttendanceLog.query.filter(
        AttendanceLog.employee_id == employee.id,
        AttendanceLog.timestamp >= start_datetime,
        AttendanceLog.timestamp <= end_datetime
    ).order_by(AttendanceLog.timestamp.asc()).all()

    response_logs = []
    total_seconds = 0
    last_in_time = None

    for log in logs:

        if log.log_type == "IN":
            last_in_time = log.timestamp

        elif log.log_type == "OUT" and last_in_time:
            session_seconds = int((log.timestamp - last_in_time).total_seconds())
            total_seconds += session_seconds
            last_in_time = None

    # 🔹 Now create response list in DESC order
    for log in reversed(logs):

        response_logs.append({
            "id": log.id,
            "time": log.timestamp.strftime('%H:%M:%S'),
            "type": log.log_type,
            "device_id": log.device_id,
            "location": log.location
        })

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    total_duration = f"{hours:02}:{minutes:02}:{seconds:02}"

    is_checked_in = False
    if logs:
        if logs[-1].log_type == "IN":  # last log in ASC
            is_checked_in = True

    return jsonify({
        "success": True,
        "employee_id": employee.id,
        "logs": response_logs,   # 🔥 Now newest on top
        "total_duration": total_duration,
        "is_checked_in": is_checked_in
    }), 200    

# ---------------------------------------------------
# DASHBOARD API
# ---------------------------------------------------
@bp.route('/dashboard', methods=['GET'])
def dashboard_api():

    requested_user_id = request.args.get("user_id")

    if not requested_user_id:
        return jsonify({
            "success": False,
            "message": "User ID required"
        }), 400

    # ------------------------------------------------
    # GET USER
    # ------------------------------------------------
    target_user = User.query.get(int(requested_user_id))

    if not target_user:
        return jsonify({
            "success": False,
            "message": "User not found"
        }), 404

    if not target_user.employee_id:
        return jsonify({
            "success": False,
            "message": "Employee not linked to user"
        }), 404

    # ------------------------------------------------
    # GET EMPLOYEE FROM EMPLOYEE MODEL
    # ------------------------------------------------
    employee = Employee.query.get(target_user.employee_id)

    if not employee:
        return jsonify({
            "success": False,
            "message": "Employee record not found"
        }), 404

    # ------------------------------------------------
    # DATE RANGE (Current Month)
    # ------------------------------------------------
    today = date.today()
    start_date = date(today.year, today.month, 1)
    end_date = date(
        today.year,
        today.month,
        calendar.monthrange(today.year, today.month)[1]
    )

    records = AttendanceRecord.query.filter(
        AttendanceRecord.employee_id == employee.id,
        AttendanceRecord.date.between(start_date, end_date)
    ).all()

    # ------------------------------------------------
    # STATISTICS
    # ------------------------------------------------
    present = sum(1 for r in records if r.status == 'present')
    absent = sum(1 for r in records if r.status == 'absent')
    late = sum(1 for r in records if r.status == 'late')
    early_out = sum(1 for r in records if r.status in ['early_out', 'early-out'])
    missing = sum(1 for r in records if r.status not in
                  ['present', 'absent', 'late', 'early_out', 'early-out'])

    total_hours = sum(r.work_hours or 0 for r in records)
    overtime_hours = sum(r.overt_time_weighted or 0 for r in records)

    # ------------------------------------------------
    # TREND DATA
    # ------------------------------------------------
    dates = []
    trend_present = []
    trend_absent = []
    trend_late = []

    d = start_date
    while d <= end_date:
        dates.append(d.strftime('%Y-%m-%d'))

        day_records = [r for r in records if r.date == d]

        trend_present.append(sum(1 for r in day_records if r.status == 'present'))
        trend_absent.append(sum(1 for r in day_records if r.status == 'absent'))
        trend_late.append(sum(1 for r in day_records if r.status == 'late'))

        d += timedelta(days=1)

    records = sorted(records, key=lambda x: x.date, reverse=True)[:7]

    daily_logs = defaultdict(lambda: {"IN": None, "OUT": None, "DURATION": None})

    for r in records:
        date_str = r.date.strftime('%Y-%m-%d')

        if r.check_in:
            daily_logs[date_str]["IN"] = r.check_in.strftime('%H:%M:%S')

        if r.check_out:
            daily_logs[date_str]["OUT"] = r.check_out.strftime('%H:%M:%S')

       
        if r.check_in and r.check_out:
            duration = r.check_out - r.check_in

            total_seconds = int(duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60

            daily_logs[date_str]["DURATION"] = f"{hours:02}:{minutes:02}:{seconds:02}"


    # ------------------------------------------------
    # EMPLOYEE SUMMARY
    # ------------------------------------------------
    employee_summary = [{
        "id": employee.id,
        "name": employee.name,
        "department": employee.department,
        "position": employee.position,
        "join_date": employee.join_date.strftime('%Y-%m-%d') if employee.join_date else None,
        "phone": employee.phone,
        "email": employee.email,
        "present_days": present,
        "absent_days": absent,
        "late_count": late,
        "early_out_count": early_out,
        "missing_count": missing,
        "total_hours": total_hours,
        "overtime_hours": overtime_hours
    }]

    # ------------------------------------------------
    # RESPONSE
    # ------------------------------------------------
    return jsonify({
        "success": True,
        "employee": {
            "id": employee.id,
            "name": employee.name,
            "department": employee.department,
            "position": employee.position,
            "employee_code": employee.employee_code,
            "join_date": employee.join_date.strftime('%Y-%m-%d') if employee.join_date else None,
            "phone": employee.phone,
            "email": employee.email
        },
        "statistics": {
            "present": present,
            "absent": absent,
            "late": late,
            "early_out": early_out,
            "missing": missing,
            "total_hours": total_hours,
            "overtime_hours": overtime_hours
        },
        "trend": {
            "dates": dates,
            "present": trend_present,
            "absent": trend_absent,
            "late": trend_late
        },
        "daily_logs": dict(daily_logs),
        "employee_summary": employee_summary
    }), 200



@bp.route("/login", methods=["POST"])
def api_login():

    data = request.get_json()

    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({
            "success": False,
            "message": "Username and password required"
        }), 400

    # 🔍 Username numeric matching logic
    user = User.query.filter(
        func.right(
            func.regexp_replace(User.username, r'\D', '', 'g'),
            len(username)
        ) == username
    ).first()


    if not user or not user.check_password(password):
        return jsonify({
            "success": False,
            "message": "Invalid username or password"
        }), 401

    # 🔥 Fetch employee name from Employee model
    employee = None
    employee_name = None
    employee_image = None

    if user.username:
        employee = Employee.query.filter_by(employee_code=user.username).first()
        if employee:
            employee_name = employee.name
            employee_image = employee.image

    # 🔐 Generate permanent JWT token (no expiry)
    token_payload = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "is_admin": user.is_admin
    }
    print(token_payload,"=====================================")

    token = jwt.encode(
        token_payload,
        "Dxb@mir0190",
        algorithm="HS256"
    )

    # Update last login
    user.last_login = datetime.utcnow()

    try:
        login_record = UserLoginHistory(
            user_id=user.id,
            username=user.username,
            login_type="password",
            login_time=datetime.utcnow()
        )
        db.session.add(login_record)
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        print("Login history error:", e)

    return jsonify({
        "success": True,
        "message": "Login successful",
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "name": employee_name, 
            "image": employee_image,
            "role": user.role,
            "is_admin": user.is_admin
        }
    }), 200
