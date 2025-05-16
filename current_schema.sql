-- Complete Database Schema for MIR AMS
-- Generated on 2025-05-10 (Verified against live database)

-- Drop tables if they exist (in reverse order of dependencies)
DROP TABLE IF EXISTS otp_verification;
DROP TABLE IF EXISTS erp_config;
DROP TABLE IF EXISTS odoo_config;
DROP TABLE IF EXISTS odoo_mapping;
DROP TABLE IF EXISTS device_log;
DROP TABLE IF EXISTS holiday;
DROP TABLE IF EXISTS shift_assignment;
DROP TABLE IF EXISTS attendance_log;
DROP TABLE IF EXISTS attendance_record;
DROP TABLE IF EXISTS shift;
DROP TABLE IF EXISTS overtime_rule;
DROP TABLE IF EXISTS attendance_device;
DROP TABLE IF EXISTS employee;
DROP TABLE IF EXISTS "user";
DROP TABLE IF EXISTS system_config;
DROP TABLE IF EXISTS alembic_version;

-- User table
CREATE TABLE "user" (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(256),
    is_admin BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    odoo_id INTEGER,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITHOUT TIME ZONE,
    force_password_change BOOLEAN DEFAULT FALSE,
    role VARCHAR(64) DEFAULT 'employee',
    department VARCHAR(128)
);

-- Employee table
-- IMPORTANT OVERTIME ELIGIBILITY:
-- Each employee can be individually configured for different types of overtime:
-- 1. eligible_for_weekday_overtime: Overtime on regular weekdays
-- 2. eligible_for_weekend_overtime: Overtime on configured weekend days
-- 3. eligible_for_holiday_overtime: Overtime on holidays
CREATE TABLE employee (
    id SERIAL PRIMARY KEY,
    odoo_id INTEGER UNIQUE,
    user_id INTEGER REFERENCES "user"(id),
    name VARCHAR(128) NOT NULL,
    employee_code VARCHAR(64) UNIQUE,
    department VARCHAR(128),
    position VARCHAR(128),
    join_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    phone VARCHAR(20),
    current_shift_id INTEGER, -- FK to shift table (added later with ALTER)
    last_sync TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    weekend_days JSON,
    eligible_for_weekday_overtime BOOLEAN DEFAULT TRUE,
    eligible_for_weekend_overtime BOOLEAN DEFAULT TRUE,
    eligible_for_holiday_overtime BOOLEAN DEFAULT TRUE
);

-- Shift table
CREATE TABLE shift (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    is_overnight BOOLEAN DEFAULT FALSE,
    break_duration FLOAT DEFAULT 0.0,
    grace_period_minutes INTEGER DEFAULT 15,
    is_active BOOLEAN DEFAULT TRUE,
    color_code VARCHAR(7) DEFAULT '#3498db',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    weekend_days JSON
);

-- Add foreign key constraints that couldn't be added initially due to order
ALTER TABLE employee 
ADD CONSTRAINT fk_employee_current_shift 
FOREIGN KEY (current_shift_id) REFERENCES shift(id);

-- Overtime Rule table
CREATE TABLE overtime_rule (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    apply_on_weekday BOOLEAN DEFAULT TRUE,
    apply_on_weekend BOOLEAN DEFAULT TRUE,
    apply_on_holiday BOOLEAN DEFAULT TRUE,
    departments VARCHAR(512),
    daily_regular_hours FLOAT DEFAULT 8.0,
    weekday_multiplier FLOAT DEFAULT 1.5,
    weekend_multiplier FLOAT DEFAULT 2.0,
    holiday_multiplier FLOAT DEFAULT 2.5,
    night_shift_start_time TIME,
    night_shift_end_time TIME,
    night_shift_multiplier FLOAT DEFAULT 1.2,
    max_daily_overtime FLOAT DEFAULT 4.0,
    max_weekly_overtime FLOAT DEFAULT 15.0,
    max_monthly_overtime FLOAT DEFAULT 36.0,
    priority INTEGER DEFAULT 10,
    is_active BOOLEAN DEFAULT TRUE,
    valid_from DATE,
    valid_until DATE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Attendance Device table
CREATE TABLE attendance_device (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    device_id VARCHAR(64) NOT NULL UNIQUE,
    device_type VARCHAR(64) NOT NULL,
    model VARCHAR(64),
    location VARCHAR(256),
    ip_address VARCHAR(45),
    port INTEGER,
    username VARCHAR(64),
    password VARCHAR(256),
    api_key VARCHAR(256),
    serial_number VARCHAR(64),
    firmware_version VARCHAR(64),
    is_active BOOLEAN DEFAULT TRUE,
    last_ping TIMESTAMP WITHOUT TIME ZONE,
    last_sync TIMESTAMP WITHOUT TIME ZONE,
    status VARCHAR(64) DEFAULT 'offline',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Attendance Record table
-- IMPORTANT OVERTIME BEHAVIOR:
-- 1. On weekends and holidays, ALL hours worked are considered overtime
-- 2. On regular days, only hours beyond standard shift hours are overtime
-- 3. Night shift overtime is tracked separately in overtime_night_hours field
CREATE TABLE attendance_record (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employee(id),
    shift_id INTEGER REFERENCES shift(id),
    date DATE NOT NULL,
    check_in TIMESTAMP WITHOUT TIME ZONE,
    check_out TIMESTAMP WITHOUT TIME ZONE,
    status VARCHAR(20) DEFAULT 'pending',
    is_holiday BOOLEAN DEFAULT FALSE,
    is_weekend BOOLEAN DEFAULT FALSE,
    work_hours FLOAT DEFAULT 0.0,
    overtime_hours FLOAT DEFAULT 0.0,
    break_duration FLOAT DEFAULT 0.0,
    notes TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    overtime_rule_id INTEGER REFERENCES overtime_rule(id),
    overtime_rate FLOAT DEFAULT 1.0,
    -- Specific overtime categories for detailed tracking
    regular_overtime_hours FLOAT DEFAULT 0.0,  -- Weekday overtime
    weekend_overtime_hours FLOAT DEFAULT 0.0,  -- Weekend overtime
    holiday_overtime_hours FLOAT DEFAULT 0.0,  -- Holiday overtime
    overtime_night_hours FLOAT DEFAULT 0.0,    -- Night shift overtime
    shift_type VARCHAR(20) DEFAULT 'day',
    total_duration FLOAT DEFAULT 0.0,
    late_minutes INTEGER DEFAULT 0 NOT NULL
);

-- Add indexes to improve search performance for attendance records
CREATE INDEX ix_attendance_record_date ON attendance_record(date);
CREATE INDEX ix_attendance_record_employee_id_date ON attendance_record(employee_id, date);

-- Attendance Log table
CREATE TABLE attendance_log (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employee(id),
    device_id INTEGER NOT NULL REFERENCES attendance_device(id),
    timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    log_type VARCHAR(10) NOT NULL,
    is_processed BOOLEAN DEFAULT FALSE,
    attendance_record_id INTEGER REFERENCES attendance_record(id),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Add unique constraint to prevent duplicate logs
CREATE UNIQUE INDEX ix_attendance_log_employee_timestamp_log_type 
ON attendance_log(employee_id, timestamp, log_type);

-- Shift Assignment table
CREATE TABLE shift_assignment (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employee(id),
    shift_id INTEGER NOT NULL REFERENCES shift(id),
    start_date DATE NOT NULL,
    end_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Holiday table
CREATE TABLE holiday (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    date DATE NOT NULL,
    is_recurring BOOLEAN DEFAULT FALSE,
    is_employee_specific BOOLEAN DEFAULT FALSE,
    employee_id INTEGER REFERENCES employee(id),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Device Log table
CREATE TABLE device_log (
    id SERIAL PRIMARY KEY,
    device_id INTEGER NOT NULL REFERENCES attendance_device(id),
    log_type VARCHAR(20) NOT NULL,
    message TEXT,
    timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Odoo Mapping table
CREATE TABLE odoo_mapping (
    id SERIAL PRIMARY KEY,
    employee_field VARCHAR(64) NOT NULL,
    odoo_field VARCHAR(64) NOT NULL,
    field_type VARCHAR(20) DEFAULT 'text',
    is_required BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    default_value VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Odoo Config table
CREATE TABLE odoo_config (
    id SERIAL PRIMARY KEY,
    host VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL DEFAULT 5432,
    database VARCHAR(255) NOT NULL,
    user VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    auto_sync BOOLEAN DEFAULT FALSE,
    sync_interval_hours INTEGER DEFAULT 24,
    last_sync TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ERP Config table
CREATE TABLE erp_config (
    id SERIAL PRIMARY KEY,
    api_url VARCHAR(255) NOT NULL DEFAULT 'https://erp.mir.ae:4082',
    username VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    auto_sync BOOLEAN DEFAULT FALSE,
    sync_interval_hours INTEGER DEFAULT 24,
    last_sync TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- OTP Verification table
CREATE TABLE otp_verification (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20) NOT NULL,
    otp_code VARCHAR(6) NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    employee_id INTEGER REFERENCES employee(id)
);

-- System Config table
CREATE TABLE system_config (
    id SERIAL PRIMARY KEY,
    system_name VARCHAR(128),
    weekend_days JSON,  -- JSON array of weekend days, e.g., [5, 6] for Friday, Saturday
    default_work_hours FLOAT DEFAULT 8.0,
    timezone VARCHAR(64) DEFAULT 'UTC',
    date_format VARCHAR(32) DEFAULT 'DD/MM/YYYY',
    time_format VARCHAR(32) DEFAULT 'HH:mm',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    openai_api_key VARCHAR(255),
    ai_assistant_enabled BOOLEAN DEFAULT FALSE,
    ai_model VARCHAR(64) DEFAULT 'gpt-4o'
);

-- Alembic version tracking (for migrations)
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);

-- Insert admin user if not exists
INSERT INTO "user" (username, email, password_hash, is_admin, is_active)
SELECT 'admin', 'erp@mir.ae', 'pbkdf2:sha256:150000$F03RbHtb$8a69bd46eb8c21c45bb9ac5f71f8cbcb4d97a4e8c08d31cccca76cd6378e5d8a', TRUE, TRUE
WHERE NOT EXISTS (SELECT 1 FROM "user" WHERE username = 'admin');

-- Create default general shift
INSERT INTO shift (name, start_time, end_time, break_duration, grace_period_minutes)
SELECT 'General Shift', '08:00:00', '17:00:00', 1.0, 15
WHERE NOT EXISTS (SELECT 1 FROM shift WHERE name = 'General Shift');

-- Default night shift
INSERT INTO shift (name, start_time, end_time, is_overnight, break_duration, grace_period_minutes, color_code)
SELECT 'Night Shift', '20:00:00', '06:00:00', TRUE, 1.0, 15, '#9b59b6'
WHERE NOT EXISTS (SELECT 1 FROM shift WHERE name = 'Night Shift');

-- Default standard overtime rule
INSERT INTO overtime_rule (
    name, description, 
    apply_on_weekday, apply_on_weekend, apply_on_holiday,
    daily_regular_hours, 
    weekday_multiplier, weekend_multiplier, holiday_multiplier,
    night_shift_start_time, night_shift_end_time, night_shift_multiplier,
    priority, is_active
)
SELECT 
    'Standard Overtime Rule', 'Default overtime rule with standard multipliers', 
    TRUE, TRUE, TRUE,
    8.0, 
    1.5, 2.0, 2.5,
    '22:00:00', '06:00:00', 1.2,
    10, TRUE
WHERE NOT EXISTS (SELECT 1 FROM overtime_rule WHERE name = 'Standard Overtime Rule');

-- Create default system configuration if not exists
INSERT INTO system_config (
    system_name, 
    weekend_days, 
    default_work_hours, 
    timezone, 
    date_format,
    time_format
)
SELECT 
    'MIR Attendance Management System', 
    '[5, 6]'::json, -- Friday and Saturday as default weekend days
    8.0, 
    'Asia/Dubai', 
    'DD/MM/YYYY',
    'HH:mm'
WHERE 
    NOT EXISTS (SELECT 1 FROM system_config);