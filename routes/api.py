from flask import Blueprint, request, jsonify
from datetime import datetime, date, timedelta
import calendar
from collections import defaultdict
import jwt
import os, uuid
from werkzeug.utils import secure_filename
from app import db
from models import User, Employee, AttendanceRecord, AttendanceLog,UserLoginHistory ,FCMToken,AttendanceDispute ,AttendanceDisputeHistory,MobileAppLoginHistory,AttendanceDisputeAttachment,EmployeeLeave,AnnualLeave
from sqlalchemy import func
from flask_login import login_required, current_user, logout_user, login_user

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

@bp.route("/update_last_active", methods=["POST"])
def update_last_active():

    data = request.get_json()
    user_id = data.get("user_id")

    if not user_id:
        return jsonify({
            "success": False,
            "message": "User ID required"
        }), 400

    # latest login record find
    record = MobileAppLoginHistory.query \
        .filter_by(user_id=user_id) \
        .order_by(MobileAppLoginHistory.login_time.desc()) \
        .first()

    if not record:
        return jsonify({
            "success": False,
            "message": "Login history not found"
        }), 404

    record.last_active_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Last active updated",
        "last_active_at": record.last_active_at
    }), 200  

@bp.route('/mark_dispute_viewed', methods=['POST'])
def mark_dispute_viewed():

    dispute_id = request.json.get("dispute_id")
    user_id = request.json.get("user_id")  # mobile user id

    print(dispute_id, user_id, "=====================")

    AttendanceDisputeHistory.query.filter(
        AttendanceDisputeHistory.dispute_id == dispute_id,
        AttendanceDisputeHistory.is_viewed == False,
        AttendanceDisputeHistory.by_user_id != user_id   # ✅ only admin replies
    ).update({
        "is_viewed": True
    }, synchronize_session=False)

    db.session.commit()

    return jsonify({"success": True})

@bp.route('/my_disputes', methods=['GET'])
def my_disputes():

    try:

        user_id = request.args.get("user_id")

        if not user_id:
            return jsonify({
                "success": False,
                "message": "User ID required"
            }), 400


        # ===============================
        # LATEST ACTIVITY SUBQUERY
        # ===============================
        latest_activity = db.session.query(
            AttendanceDisputeHistory.dispute_id.label("dispute_id"),
            func.max(AttendanceDisputeHistory.created_at).label("last_activity")
        ).group_by(
            AttendanceDisputeHistory.dispute_id
        ).subquery()


        # ===============================
        # FETCH DISPUTES (LATEST REPLY FIRST)
        # ===============================
        tickets = AttendanceDispute.query.filter(
            AttendanceDispute.user_id == user_id
        ).outerjoin(
            latest_activity,
            AttendanceDispute.id == latest_activity.c.dispute_id
        ).order_by(
            func.coalesce(
                latest_activity.c.last_activity,
                AttendanceDispute.created_at
            ).desc()
        ).all()


        response = []


        for t in tickets:

            # ===============================
            # UNREAD COUNT
            # ===============================
            unread_count = AttendanceDisputeHistory.query.filter(
                AttendanceDisputeHistory.dispute_id == t.id,
                AttendanceDisputeHistory.is_viewed == False,
                AttendanceDisputeHistory.by_user_id != int(user_id)
            ).count()


            # ===============================
            # DISPUTE ATTACHMENTS
            # ===============================
            dispute_attachments = AttendanceDisputeAttachment.query.filter_by(
                dispute_id=t.id,
                history_id=None
            ).all()

            dispute_files = []

            for a in dispute_attachments:

                dispute_files.append({
                    "id": a.id,
                    "file_name": a.file_name,
                    "url": f"/dispute_attachment/{a.id}"
                })


            # ===============================
            # FETCH HISTORY
            # ===============================
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


                # IMAGE
                image_data = employee.image if employee and employee.image else None


                # ===============================
                # HISTORY ATTACHMENTS
                # ===============================
                history_attachments = AttendanceDisputeAttachment.query.filter_by(
                    history_id=h.id
                ).all()

                history_files = []

                for a in history_attachments:

                    history_files.append({
                        "id": a.id,
                        "file_name": a.file_name,
                        "url": f"/dispute_attachment/{a.id}"
                    })


                history_list.append({
                    "history_id": h.id,
                    "by_user_id": h.by_user_id,
                    "name": employee.name if employee else (user.name if user else "Unknown"),
                    "image": image_data,
                    "remark": h.remark,
                    "status": h.status,
                    "datetime": h.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "attachments": history_files
                })


            response.append({
                "id": t.id,
                "date": t.dispute_date.strftime("%Y-%m-%d"),
                "type": t.dispute_type,
                "remarks": t.remarks,
                "status": t.status,
                "attachments": dispute_files,
                "history": history_list,
                "unread_count": unread_count,
                "admin_remarks": t.admin_remarks
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

@bp.route('/reply_dispute', methods=['POST'])
def reply_dispute():

    user_id = request.form.get("user_id")

    if not user_id:
        return jsonify({"message": "Unauthorized"}), 401

    dispute_id = request.form.get("dispute_id")
    remark = request.form.get("remark")

    dispute_record = AttendanceDispute.query.get(int(dispute_id))

    if not dispute_record:
        return jsonify({"message": "Dispute not found"}), 404

    files = request.files.getlist("attachments")

    # ==========================
    # SAVE HISTORY
    # ==========================
    history = AttendanceDisputeHistory(
        dispute_id=dispute_id,
        by_user_id=user_id,
        remark=remark,
        status=None,
        created_at=datetime.utcnow(),
        is_viewed=False
    )

    db.session.add(history)
    db.session.flush()

    # ==========================
    # UPDATE MAIN DISPUTE REMARK
    # ==========================
    dispute_record.remarks = remark

    # ==========================
    # FILE UPLOAD
    # ==========================
    upload_folder = "uploads/disputes"

    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)

    for file in files:

        filename = secure_filename(file.filename)
        unique_name = f"{uuid.uuid4()}_{filename}"

        file_path = os.path.join(upload_folder, unique_name)
        file.save(file_path)

        attach = AttendanceDisputeAttachment(
            dispute_id=dispute_id,
            history_id=history.id,
            file_name=filename,
            file_path=file_path
        )

        db.session.add(attach)

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Reply added successfully"
    })
    
@bp.route('/create_dispute', methods=['POST'])
def create_dispute():

    user_id = request.form.get("user_id")
    dispute_date = request.form.get("dispute_date")
    dispute_type = request.form.get("dispute_type")
    remarks = request.form.get("remarks", "").strip()

    files = request.files.getlist("attachments")

    if not user_id or not dispute_date or not dispute_type:
        return jsonify({"success": False, "message": "Missing fields"}), 400

    user = User.query.get(user_id)

    if not user or not user.employee_id:
        return jsonify({"success": False, "message": "Invalid user"}), 400

    new_ticket = AttendanceDispute(
        user_id=user_id,
        employee_id=user.employee_id,
        dispute_date=datetime.strptime(dispute_date, "%Y-%m-%d").date(),
        dispute_type=dispute_type,
        remarks=remarks,
        status="PENDING"
    )

    db.session.add(new_ticket)
    db.session.flush()

    upload_folder = "uploads/disputes"

    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)

    for file in files:

        filename = secure_filename(file.filename)

        unique_name = f"{uuid.uuid4()}_{filename}"

        file_path = os.path.join(upload_folder, unique_name)

        file.save(file_path)

        attachment = AttendanceDisputeAttachment(
            dispute_id=new_ticket.id,
            file_name=filename,
            file_path=file_path
        )

        db.session.add(attachment)

    history = AttendanceDisputeHistory(
        dispute_id=new_ticket.id,
        by_user_id=user_id,
        remark=remarks,
        status="PENDING",
        created_at=datetime.utcnow()
    )

    db.session.add(history)

    db.session.commit()

    return jsonify({"success": True})

# ---------------------------------------------------
# TODAY ATTENDANCE LOG API
# ---------------------------------------------------
@bp.route('/attendance_logs', methods=['GET'])
def attendance_logs():

    requested_user_id = request.args.get("user_id")
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    log_type = request.args.get("type")

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

    query = AttendanceLog.query.filter(
        AttendanceLog.employee_id == employee.id
    )

    if from_date:
        start_datetime = datetime.strptime(from_date, '%Y-%m-%d')
        query = query.filter(AttendanceLog.timestamp >= start_datetime)

    if to_date:
        end_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date()
        end_datetime = datetime.combine(end_date_obj, datetime.max.time())
        query = query.filter(AttendanceLog.timestamp <= end_datetime)

    if log_type in ['IN', 'OUT']:
        query = query.filter(AttendanceLog.log_type == log_type)

    logs = query.order_by(AttendanceLog.timestamp.desc()).all()

    response_logs = []
    total_seconds = 0
    current_in = None

    asc_logs = sorted(logs, key=lambda l: l.timestamp)

    for log in asc_logs:
        if log.log_type == "IN":
            current_in = log.timestamp
        elif log.log_type == "OUT" and current_in:
            total_seconds += int((log.timestamp - current_in).total_seconds())
            current_in = None

    for log in logs:
        response_logs.append({
            "id": log.id,
            "date": log.timestamp.strftime('%Y-%m-%d'),
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
    if asc_logs and asc_logs[-1].log_type == "IN":
        is_checked_in = True

    return jsonify({
        "success": True,
        "employee_id": employee.id,
        "logs": response_logs,
        "total_duration": total_duration,
        "is_checked_in": is_checked_in
    }), 200  

@bp.route('/attendance/date-range-logs', methods=['GET'])
def attendance_date_range_logs():

    user_id = request.args.get("user_id")
    from_date_str = request.args.get("from_date")
    to_date_str = request.args.get("to_date")

    if not user_id or not from_date_str or not to_date_str:
        return jsonify({
            "success": False,
            "message": "user_id, from_date and to_date required"
        }), 400

    try:
        from_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()
    except:
        return jsonify({
            "success": False,
            "message": "Invalid date format. Use YYYY-MM-DD"
        }), 400

    if from_date > to_date:
        return jsonify({
            "success": False,
            "message": "From date cannot be greater than To date"
        }), 400

    # ------------------------------------------------
    # GET USER
    # ------------------------------------------------
    user = User.query.get(int(user_id))

    if not user or not user.employee_id:
        return jsonify({
            "success": False,
            "message": "User/Employee not found"
        }), 404

    employee = Employee.query.get(user.employee_id)

    if not employee:
        return jsonify({
            "success": False,
            "message": "Employee record not found"
        }), 404

    # ------------------------------------------------
    # FETCH RECORDS
    # ------------------------------------------------
    records = AttendanceRecord.query.filter(
        AttendanceRecord.employee_id == employee.id,
        AttendanceRecord.date.between(from_date, to_date)
    ).order_by(AttendanceRecord.date.desc()).all()

    daily_logs = defaultdict(lambda: {"IN": None, "OUT": None, "DURATION": None})

    for r in records:
        date_str = r.date.strftime('%Y-%m-%d')
        daily_logs[date_str]["STATUS"] = r.status

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

    return jsonify({
        "success": True,
        "from_date": from_date_str,
        "to_date": to_date_str,
        "total_days": len(daily_logs),
        "daily_logs": dict(daily_logs)
    }), 200    

# ---------------------------------------------------
# DASHBOARD API
# ---------------------------------------------------
@bp.route('/dashboard', methods=['GET'])
def dashboard_api():

    requested_user_id = request.args.get("user_id")

    if not requested_user_id:
        return jsonify({"success": False, "message": "User ID required"}), 400

    # ------------------------------------------------
    # GET USER
    # ------------------------------------------------
    target_user = User.query.get(int(requested_user_id))

    if not target_user:
        return jsonify({"success": False, "message": "User not found"}), 404

    if not target_user.employee_id:
        return jsonify({"success": False, "message": "Employee not linked to user"}), 404

    # ------------------------------------------------
    # GET EMPLOYEE
    # ------------------------------------------------
    employee = Employee.query.get(target_user.employee_id)

    if not employee:
        return jsonify({"success": False, "message": "Employee record not found"}), 404

    today = date.today()

    # =====================================================
    # SUMMARY / TREND DATE FILTER (Attendance Records only)
    # =====================================================
    from_date_str = request.args.get("from_date")
    to_date_str = request.args.get("to_date")
    print(from_date_str,to_date_str,"to_date_str==================================================")

    if from_date_str and to_date_str:
        try:
            start_date = datetime.strptime(from_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(to_date_str, "%Y-%m-%d").date()
        except Exception:
            return jsonify({"success": False, "message": "Invalid date format (YYYY-MM-DD required)"}), 400
    else:
        start_date = date(today.year, today.month, 1)
        end_date = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])

    if start_date > end_date:
        return jsonify({"success": False, "message": "from_date cannot be greater than to_date"}), 400

    # Apply filter on AttendanceRecord
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
    missing = sum(1 for r in records if r.status == 'missing')

    total_hours = sum(r.work_hours or 0 for r in records)
    overtime_hours = sum(r.overt_time_weighted or 0 for r in records)

    # ------------------------------------------------
    # TREND DATA (same summary range)
    # ------------------------------------------------
    dates = []
    trend_present = []
    trend_absent = []
    trend_late = []
    trend_missing = []

    d = start_date
    while d <= end_date:
        dates.append(d.strftime('%Y-%m-%d'))

        day_records = [r for r in records if r.date == d]

        trend_present.append(sum(1 for r in day_records if r.status == 'present'))
        trend_absent.append(sum(1 for r in day_records if r.status == 'absent'))
        trend_late.append(sum(1 for r in day_records if r.status == 'late'))
        trend_missing.append(sum(1 for r in day_records if r.status == 'missing'))

        d += timedelta(days=1)


    daily_logs = defaultdict(lambda: {"STATUS": None,"IN": None, "OUT": None, "DURATION": None})

    for r in records:
        date_str = r.date.strftime('%Y-%m-%d')
        daily_logs[date_str]["STATUS"] = r.status

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
        "summary_range": {
            "from_date": start_date.strftime('%Y-%m-%d'),
            "to_date": end_date.strftime('%Y-%m-%d')
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
            "late": trend_late,
            "missing": trend_missing
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

    device_name = data.get("device_name")
    gps_location = data.get("gps_location")
    app_version = data.get("app_version")

    device_ip = request.remote_addr

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

    if not user.is_active:

            return jsonify({
                "success": False,
                "message": "User inactive. Logging out.",
                "logout": True
            }), 401   

    if not user or not user.check_password(password):
        return jsonify({
            "success": False,
            "message": "Invalid username or password"
        }), 401

    # ====================================
    # FETCH EMPLOYEE
    # ====================================

    employee = None
    employee_name = None
    employee_image = None
    odoo_id = None
    department = None

    supervisor_id = None
    supervisor_name = None

    if user.username:

        employee = Employee.query.filter_by(
            employee_code=user.username
        ).first()

        odoo_id = user.odoo_id

        if employee:

            employee_name = employee.name
            employee_image = employee.image
            odoo_id = employee.odoo_id
            department = employee.department

            # ====================================
            # FIND DEPARTMENT SUPERVISOR
            # ====================================

            supervisor_user = User.query.filter(
                User.department == department,
                User.role == "supervisor",
            ).first()

            print(supervisor_user,"===============================supervisor_user",employee_name,user.department,odoo_id)

            if supervisor_user:

                supervisor_id = supervisor_user.id

                sup_emp = Employee.query.filter_by(
                    employee_code=supervisor_user.username
                ).first()

                if sup_emp:
                    supervisor_name = sup_emp.name

    # ====================================
    # GENERATE TOKEN
    # ====================================

    token_payload = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "is_admin": user.is_admin
    }

    token = jwt.encode(
        token_payload,
        "Dxb@mir0190",
        algorithm="HS256"
    )

    try:

        # ===============================
        # UPSERT MOBILE LOGIN HISTORY
        # ===============================

        existing_login = MobileAppLoginHistory.query.filter_by(
            user_id=user.id
        ).first()

        if existing_login:

            existing_login.login_time = datetime.utcnow()
            existing_login.device_name = device_name
            existing_login.device_ip = device_ip
            existing_login.gps_location = gps_location
            existing_login.app_version = app_version

        else:

            new_login = MobileAppLoginHistory(
                user_id=user.id,
                employee_id=employee.id if employee else None,
                login_time=datetime.utcnow(),
                device_name=device_name,
                device_ip=device_ip,
                gps_location=gps_location,
                app_version=app_version
            )

            db.session.add(new_login)

        # ===============================
        # NORMAL LOGIN HISTORY
        # ===============================

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
        print("Login history error:", str(e))

    # ====================================
    # RESPONSE
    # ====================================

    return jsonify({
        "success": True,
        "message": "Login successful",
        "token": token,
        "user": {
            "id": user.id,
            "odoo_id": odoo_id,
            "username": user.username,
            "name": employee_name,
            "image": employee_image,
            "role": user.role,
            "is_admin": user.is_admin,
            "department": department,
            "supervisor": {
                "id": supervisor_id,
                "name": supervisor_name
            }
        }
    }), 200


@bp.route("/leave-history/<int:user_id>")
def leave_history_api(user_id):

    leaves = EmployeeLeave.query.filter_by(
        user_id=user_id
    ).order_by(EmployeeLeave.created_at.desc()).all()

    result = []

    for leave in leaves:

        result.append({
            "id": leave.id,
            "from": leave.from_date.strftime("%Y-%m-%d"),
            "to": leave.to_date.strftime("%Y-%m-%d"),
            "reason": leave.reason,
            "hr_remark": leave.hr_remark,
            "status": leave.status
        })

    return jsonify(result)

@bp.route("/create-leave", methods=["POST"])
def create_leave():
    print("calling")
    data = request.get_json()
    print(data,"data=======================")

    user_id = data.get("user_id")
    from_date = data.get("from_date")
    to_date = data.get("to_date")
    reason = data.get("reason", "")
    print(user_id,from_date,to_date,reason,"=======================")

    leave = EmployeeLeave(
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
        reason=reason
    )

    db.session.add(leave)
    db.session.commit()

    return jsonify({"status":"success"})    

@bp.route("/annual-leave-history/<int:user_id>")
def annual_leave_history(user_id):

    leaves = AnnualLeave.query.filter_by(
        user_id=user_id
    ).order_by(AnnualLeave.created_at.desc()).all()

    result = []

    for l in leaves:
        result.append({
            "id": l.id,
            "from": l.date_from.strftime("%Y-%m-%d"),
            "to": l.date_to.strftime("%Y-%m-%d"),
            "reason": l.reason,
            "status": l.status,
            "supervisor_remark": l.supervisor_remark,
            "hr_remark": l.hr_remark,
            "admin_remark": l.admin_remark
        })

    return jsonify(result)

@bp.route("/create-annual-leave", methods=["POST"])
def create_annual_leave():

    data = request.get_json()

    user = User.query.get(data["user_id"])
    if not user:
        return jsonify({"error": "User not found"}), 404

    # employee_code = username
    employee = Employee.query.filter_by(
        employee_code=user.username
    ).first()

    employee_id = None
    department = None
    supervisor_id = None

    if employee:
        employee_id = employee.id
        department = employee.department

        # department supervisor
        supervisor_user = User.query.filter_by(
            department=department,
            role="supervisor"
        ).first()

        if supervisor_user:
            supervisor_id = supervisor_user.employee_id

    date_from = datetime.strptime(data["date_from"], "%Y-%m-%d").date()
    date_to = datetime.strptime(data["date_to"], "%Y-%m-%d").date()

    total_days = (date_to - date_from).days + 1

    leave = AnnualLeave(
        user_id=user.id,
        employee_id=employee_id,
        supervisor_id=supervisor_id,
        department=department,
        date_from=date_from,
        date_to=date_to,
        total_days=total_days,
        reason=data["reason"],
        status="pending_supervisor"
    )

    db.session.add(leave)
    db.session.commit()

    return jsonify({"status": "success"})


@bp.route("/check-user-active", methods=["POST"])
def check_user_active():

    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "message": "No data provided"
        }), 400

    token = data.get("token")
    device_name = data.get("device_name")
    gps_location = data.get("gps_location")
    app_version = data.get("app_version")

    device_ip = request.remote_addr

    if not token:
        return jsonify({
            "success": False,
            "message": "Token required"
        }), 401

    try:

        payload = jwt.decode(
            token,
            "Dxb@mir0190",
            algorithms=["HS256"]
        )

        user_id = payload.get("user_id")

        user = User.query.filter_by(id=user_id).first()

        if not user:
            return jsonify({
                "success": False,
                "message": "User not found",
                "logout": True
            }), 401

        # ==============================
        # CHECK USER ACTIVE
        # ==============================

        if not user.is_active:

            return jsonify({
                "success": False,
                "message": "User inactive. Logging out.",
                "logout": True
            }), 401

        # ==============================
        # FETCH EMPLOYEE
        # ==============================

        employee = Employee.query.filter_by(
            employee_code=user.username
        ).first()

        # ==============================
        # UPDATE / CREATE MOBILE LOGIN
        # ==============================

        try:

            existing_login = MobileAppLoginHistory.query.filter_by(
                user_id=user.id
            ).first()

            if existing_login:

                existing_login.login_time = datetime.utcnow()
                existing_login.device_name = device_name
                existing_login.device_ip = device_ip
                existing_login.gps_location = gps_location
                existing_login.app_version = app_version

            else:

                new_login = MobileAppLoginHistory(
                    user_id=user.id,
                    employee_id=employee.id if employee else None,
                    login_time=datetime.utcnow(),
                    device_name=device_name,
                    device_ip=device_ip,
                    gps_location=gps_location,
                    app_version=app_version
                )

                db.session.add(new_login)

            db.session.commit()

        except Exception as e:

            db.session.rollback()
            print("Device update error:", str(e))

        return jsonify({
            "success": True,
            "message": "User active"
        }), 200

    except jwt.InvalidTokenError:

        return jsonify({
            "success": False,
            "message": "Invalid token",
            "logout": True
        }), 401    