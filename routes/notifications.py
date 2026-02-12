from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from db import db
from models import AttendanceNotification


bp = Blueprint('notifications', __name__)


def _user_can_view_notifications() -> bool:
    """Return True if the current user is allowed to view HR notifications."""

    if not current_user.is_authenticated:
        return False

    if current_user.is_admin:
        return True

    return current_user.has_role('hr')


@bp.route('/')
@login_required
def list_notifications():
    if not _user_can_view_notifications():
        abort(403)

    query = AttendanceNotification.query.order_by(
        AttendanceNotification.created_at.desc()
    )

    if not current_user.is_admin:
        query = query.filter(AttendanceNotification.role == current_user.role)
    else:
        requested_role = request.args.get('role')
        if requested_role:
            query = query.filter(AttendanceNotification.role == requested_role)

    notifications = query.limit(200).all()

    return render_template(
        'notifications/index.html',
        notifications=notifications,
    )


@bp.route('/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    if not _user_can_view_notifications():
        abort(403)

    query = AttendanceNotification.query.filter(
        AttendanceNotification.is_read.is_(False)
    )

    if not current_user.is_admin:
        query = query.filter(AttendanceNotification.role == current_user.role)
    else:
        requested_role = request.form.get('role')
        if requested_role:
            query = query.filter(AttendanceNotification.role == requested_role)

    updated = query.update({AttendanceNotification.is_read: True})
    db.session.commit()

    if request.is_json:
        return jsonify({'updated': updated}), 200

    next_url = request.form.get('next') or request.referrer
    return redirect(next_url or url_for('notifications.list_notifications'))


@bp.route('/<int:notification_id>/mark-read', methods=['POST'])
@login_required
def mark_read(notification_id: int):
    if not _user_can_view_notifications():
        abort(403)

    notification = AttendanceNotification.query.get_or_404(notification_id)

    if not current_user.is_admin and notification.role != current_user.role:
        abort(403)

    notification.is_read = True
    db.session.commit()

    if request.is_json:
        return jsonify({'status': 'ok'})

    next_url = request.form.get('next') or request.referrer
    return redirect(next_url or url_for('notifications.list_notifications'))
