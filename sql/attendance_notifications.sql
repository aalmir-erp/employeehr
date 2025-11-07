-- Manual SQL to align the database with the AttendanceNotification model changes.
-- These statements assume a PostgreSQL database, matching app.py's SQLALCHEMY_DATABASE_URI.

BEGIN;

-- 1. Create a dedicated sequence for the primary key (only if you are not using the generic SERIAL helper).
CREATE SEQUENCE IF NOT EXISTS attendance_notification_id_seq
    INCREMENT BY 1
    MINVALUE 1
    MAXVALUE 2147483647
    START WITH 1
    CACHE 1;

-- 2. Create the attendance_notification table when it does not exist yet.
CREATE TABLE IF NOT EXISTS attendance_notification (
    id INTEGER NOT NULL DEFAULT nextval('attendance_notification_id_seq'::regclass),
    attendance_log_id INTEGER NOT NULL,
    employee_id INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'hr',
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT attendance_notification_pkey PRIMARY KEY (id),
    CONSTRAINT fk_attendance_notification_log FOREIGN KEY (attendance_log_id)
        REFERENCES attendance_log (id)
);

-- 3. Create indexes that match the ORM model + migration for efficient lookups.
CREATE INDEX IF NOT EXISTS ix_attendance_notification_role_is_read
    ON attendance_notification (role, is_read);

CREATE INDEX IF NOT EXISTS ix_attendance_notification_created_at
    ON attendance_notification (created_at);

-- 4. (Optional) Backfill notifications for attendance logs created before the trigger was deployed.
--    Adjust the time window or WHERE clause if you need to limit the backfill.
INSERT INTO attendance_notification (attendance_log_id, employee_id, role, message, is_read, created_at)
SELECT
    al.id,
    al.employee_id,
    'hr' AS role,
    CONCAT('Attendance ', al.log_type, ' recorded for employee ID ', al.employee_id,
           ' at ', to_char(al.timestamp, 'YYYY-MM-DD HH24:MI')) AS message,
    FALSE AS is_read,
    COALESCE(al.created_at, CURRENT_TIMESTAMP)
FROM attendance_log al
WHERE NOT EXISTS (
    SELECT 1
    FROM attendance_notification an
    WHERE an.attendance_log_id = al.id
);

COMMIT;
