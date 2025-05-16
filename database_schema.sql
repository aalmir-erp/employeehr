-- Updated database schema for MIR Attendance Management System
-- Generated on: 2025-05-14 17:30:00

-- Sequences
CREATE SEQUENCE IF NOT EXISTS attendance_device_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS attendance_log_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS attendance_record_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS department_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS device_log_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS employee_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS erp_config_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS holiday_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS odoo_config_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS odoo_mapping_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS otp_verification_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS overtime_rule_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS shift_assignment_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS shift_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS system_config_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS user_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS bonus_question_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS bonus_evaluation_period_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS bonus_submission_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS bonus_evaluation_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;
CREATE SEQUENCE IF NOT EXISTS bonus_audit_log_id_seq INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1;

-- Table: attendance_device
CREATE TABLE IF NOT EXISTS attendance_device (
    id integer NOT NULL DEFAULT nextval('attendance_device_id_seq'::regclass),
    name character varying NOT NULL,
    device_id character varying NOT NULL,
    device_type character varying NOT NULL,
    location character varying NULL,
    ip_address character varying NULL,
    port integer NULL,
    api_key character varying NULL,
    is_active boolean NULL,
    last_ping timestamp without time zone NULL,
    last_sync timestamp without time zone NULL,
    status character varying NULL,
    created_at timestamp without time zone NULL,
    updated_at timestamp without time zone NULL,
    model character varying NULL,
    username character varying NULL,
    password character varying NULL,
    serial_number character varying NULL,
    firmware_version character varying NULL,
    CONSTRAINT attendance_device_pkey PRIMARY KEY (id),
    CONSTRAINT attendance_device_device_id_key UNIQUE (device_id)
);

-- Table: attendance_log
CREATE TABLE IF NOT EXISTS attendance_log (
    id integer NOT NULL DEFAULT nextval('attendance_log_id_seq'::regclass),
    employee_id integer NOT NULL,
    device_id integer NOT NULL,
    timestamp timestamp without time zone NOT NULL,
    log_type character varying NOT NULL,
    is_processed boolean NULL,
    created_at timestamp without time zone NULL,
    attendance_record_id integer NULL,
    CONSTRAINT attendance_log_pkey PRIMARY KEY (id),
    CONSTRAINT attendance_log_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES employee(id),
    CONSTRAINT attendance_log_device_id_fkey FOREIGN KEY (device_id) REFERENCES attendance_device(id),
    CONSTRAINT attendance_log_attendance_record_id_fkey FOREIGN KEY (attendance_record_id) REFERENCES attendance_record(id)
);

-- Table: attendance_record
CREATE TABLE IF NOT EXISTS attendance_record (
    id integer NOT NULL DEFAULT nextval('attendance_record_id_seq'::regclass),
    employee_id integer NOT NULL,
    shift_id integer NULL,
    date date NOT NULL,
    check_in timestamp without time zone NULL,
    check_out timestamp without time zone NULL,
    status character varying NULL,
    is_holiday boolean NULL,
    is_weekend boolean NULL,
    work_hours double precision NULL,
    overtime_hours double precision NULL,
    break_duration double precision NULL,
    notes text NULL,
    created_at timestamp without time zone NULL,
    updated_at timestamp without time zone NULL,
    overtime_rule_id integer NULL,
    overtime_rate double precision NULL,
    overtime_night_hours double precision NULL,
    shift_type character varying NULL,
    total_duration double precision NULL,
    late_minutes integer NOT NULL DEFAULT 0,
    regular_overtime_hours double precision NULL DEFAULT 0.0,
    weekend_overtime_hours double precision NULL DEFAULT 0.0,
    holiday_overtime_hours double precision NULL DEFAULT 0.0,
    break_start timestamp without time zone NULL,
    break_end timestamp without time zone NULL,
    break_calculated boolean NULL DEFAULT false,
    CONSTRAINT attendance_record_pkey PRIMARY KEY (id),
    CONSTRAINT attendance_record_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES employee(id),
    CONSTRAINT attendance_record_shift_id_fkey FOREIGN KEY (shift_id) REFERENCES shift(id),
    CONSTRAINT attendance_record_overtime_rule_id_fkey FOREIGN KEY (overtime_rule_id) REFERENCES overtime_rule(id)
);

-- Table: department
CREATE TABLE IF NOT EXISTS department (
    id integer NOT NULL DEFAULT nextval('department_id_seq'::regclass),
    name character varying NOT NULL,
    weekday_overtime_eligible boolean NULL,
    weekend_overtime_eligible boolean NULL,
    holiday_overtime_eligible boolean NULL,
    CONSTRAINT department_pkey PRIMARY KEY (id),
    CONSTRAINT department_name_key UNIQUE (name)
);

-- Table: device_log
CREATE TABLE IF NOT EXISTS device_log (
    id integer NOT NULL DEFAULT nextval('device_log_id_seq'::regclass),
    device_id integer NOT NULL,
    log_type character varying NOT NULL,
    message text NULL,
    timestamp timestamp without time zone NULL,
    CONSTRAINT device_log_pkey PRIMARY KEY (id),
    CONSTRAINT device_log_device_id_fkey FOREIGN KEY (device_id) REFERENCES attendance_device(id)
);

-- Table: employee
CREATE TABLE IF NOT EXISTS employee (
    id integer NOT NULL DEFAULT nextval('employee_id_seq'::regclass),
    odoo_id integer NULL,
    user_id integer NULL,
    name character varying NOT NULL,
    employee_code character varying NULL,
    department character varying NULL,
    position character varying NULL,
    join_date date NULL,
    is_active boolean NULL,
    phone character varying NULL,
    current_shift_id integer NULL,
    last_sync timestamp without time zone NULL,
    weekend_days jsonb NULL,
    eligible_for_weekday_overtime boolean NULL DEFAULT true,
    eligible_for_weekend_overtime boolean NULL DEFAULT true,
    eligible_for_holiday_overtime boolean NULL DEFAULT true,
    CONSTRAINT employee_pkey PRIMARY KEY (id),
    CONSTRAINT employee_user_id_fkey FOREIGN KEY (user_id) REFERENCES user(id),
    CONSTRAINT employee_current_shift_id_fkey FOREIGN KEY (current_shift_id) REFERENCES shift(id),
    CONSTRAINT employee_odoo_id_key UNIQUE (odoo_id),
    CONSTRAINT employee_employee_code_key UNIQUE (employee_code)
);

-- Table: erp_config
CREATE TABLE IF NOT EXISTS erp_config (
    id integer NOT NULL DEFAULT nextval('erp_config_id_seq'::regclass),
    api_url character varying NOT NULL,
    username character varying NOT NULL,
    password character varying NOT NULL,
    auto_sync boolean NULL,
    sync_interval_hours integer NULL,
    last_sync timestamp without time zone NULL,
    created_at timestamp without time zone NULL,
    updated_at timestamp without time zone NULL,
    CONSTRAINT erp_config_pkey PRIMARY KEY (id)
);

-- Table: holiday
CREATE TABLE IF NOT EXISTS holiday (
    id integer NOT NULL DEFAULT nextval('holiday_id_seq'::regclass),
    name character varying NOT NULL,
    date date NOT NULL,
    is_recurring boolean NULL,
    is_employee_specific boolean NULL,
    employee_id integer NULL,
    created_at timestamp without time zone NULL,
    CONSTRAINT holiday_pkey PRIMARY KEY (id),
    CONSTRAINT holiday_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES employee(id)
);

-- Table: odoo_config
CREATE TABLE IF NOT EXISTS odoo_config (
    id integer NOT NULL DEFAULT nextval('odoo_config_id_seq'::regclass),
    host character varying NULL,
    port integer NULL,
    database character varying NULL,
    user character varying NULL,
    password character varying NULL,
    auto_sync boolean NULL,
    sync_interval_hours integer NULL,
    last_sync timestamp without time zone NULL,
    created_at timestamp without time zone NULL,
    updated_at timestamp without time zone NULL,
    url character varying NULL,
    username character varying NULL,
    api_key character varying NULL,
    is_active boolean NULL DEFAULT false,
    CONSTRAINT odoo_config_pkey PRIMARY KEY (id)
);

-- Table: odoo_mapping
CREATE TABLE IF NOT EXISTS odoo_mapping (
    id integer NOT NULL DEFAULT nextval('odoo_mapping_id_seq'::regclass),
    employee_field character varying NOT NULL,
    odoo_field character varying NOT NULL,
    field_type character varying NULL,
    is_required boolean NULL,
    is_active boolean NULL,
    default_value character varying NULL,
    created_at timestamp without time zone NULL,
    updated_at timestamp without time zone NULL,
    CONSTRAINT odoo_mapping_pkey PRIMARY KEY (id)
);

-- Table: otp_verification
CREATE TABLE IF NOT EXISTS otp_verification (
    id integer NOT NULL DEFAULT nextval('otp_verification_id_seq'::regclass),
    phone character varying NOT NULL,
    otp_code character varying NOT NULL,
    is_verified boolean NULL,
    created_at timestamp without time zone NULL,
    expires_at timestamp without time zone NOT NULL,
    employee_id integer NULL,
    CONSTRAINT otp_verification_pkey PRIMARY KEY (id),
    CONSTRAINT otp_verification_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES employee(id)
);

-- Table: overtime_rule
CREATE TABLE IF NOT EXISTS overtime_rule (
    id integer NOT NULL DEFAULT nextval('overtime_rule_id_seq'::regclass),
    name character varying NOT NULL,
    description text NULL,
    apply_on_weekday boolean NULL,
    apply_on_weekend boolean NULL,
    apply_on_holiday boolean NULL,
    departments character varying NULL,
    daily_regular_hours double precision NULL,
    weekday_multiplier double precision NULL,
    weekend_multiplier double precision NULL,
    holiday_multiplier double precision NULL,
    night_shift_start_time time without time zone NULL,
    night_shift_end_time time without time zone NULL,
    night_shift_multiplier double precision NULL,
    max_daily_overtime double precision NULL,
    max_weekly_overtime double precision NULL,
    max_monthly_overtime double precision NULL,
    priority integer NULL,
    is_active boolean NULL,
    valid_from date NULL,
    valid_until date NULL,
    created_at timestamp without time zone NULL,
    updated_at timestamp without time zone NULL,
    CONSTRAINT overtime_rule_pkey PRIMARY KEY (id)
);

-- Table: shift
CREATE TABLE IF NOT EXISTS shift (
    id integer NOT NULL DEFAULT nextval('shift_id_seq'::regclass),
    name character varying NOT NULL,
    start_time time without time zone NOT NULL,
    end_time time without time zone NOT NULL,
    is_overnight boolean NULL,
    break_duration double precision NULL,
    grace_period_minutes integer NULL,
    is_active boolean NULL,
    color_code character varying NULL,
    created_at timestamp without time zone NULL,
    updated_at timestamp without time zone NULL,
    weekend_days jsonb NULL,
    CONSTRAINT shift_pkey PRIMARY KEY (id)
);

-- Table: shift_assignment
CREATE TABLE IF NOT EXISTS shift_assignment (
    id integer NOT NULL DEFAULT nextval('shift_assignment_id_seq'::regclass),
    employee_id integer NOT NULL,
    shift_id integer NOT NULL,
    start_date date NOT NULL,
    end_date date NULL,
    is_active boolean NULL,
    created_at timestamp without time zone NULL,
    updated_at timestamp without time zone NULL,
    CONSTRAINT shift_assignment_pkey PRIMARY KEY (id),
    CONSTRAINT shift_assignment_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES employee(id),
    CONSTRAINT shift_assignment_shift_id_fkey FOREIGN KEY (shift_id) REFERENCES shift(id)
);

-- Table: system_config
CREATE TABLE IF NOT EXISTS system_config (
    id integer NOT NULL DEFAULT nextval('system_config_id_seq'::regclass),
    system_name character varying NULL,
    weekend_days json NULL,
    default_work_hours double precision NULL,
    timezone character varying NULL,
    date_format character varying NULL,
    time_format character varying NULL,
    created_at timestamp without time zone NULL,
    updated_at timestamp without time zone NULL,
    openai_api_key character varying NULL,
    ai_assistant_enabled boolean NOT NULL DEFAULT false,
    ai_model character varying NOT NULL DEFAULT 'gpt-4o'::character varying,
    minimum_break_duration integer NULL DEFAULT 15,
    maximum_break_duration integer NULL DEFAULT 300,
    default_shift_id integer NULL,
    ai_enabled boolean NULL DEFAULT false,
    ai_provider character varying NULL DEFAULT 'openai'::character varying,
    ai_api_key character varying NULL,
    enable_employee_assistant boolean NULL DEFAULT false,
    enable_report_insights boolean NULL DEFAULT false,
    enable_anomaly_detection boolean NULL DEFAULT false,
    enable_predictive_scheduling boolean NULL DEFAULT false,
    max_tokens integer NULL DEFAULT 1000,
    temperature double precision NULL DEFAULT 0.7,
    prompt_template text NULL,
    ai_total_queries integer NULL DEFAULT 0,
    ai_monthly_tokens integer NULL DEFAULT 0,
    ai_success_rate double precision NULL DEFAULT 0.0,
    required_approvals integer NULL DEFAULT 2,
    CONSTRAINT system_config_pkey PRIMARY KEY (id),
    CONSTRAINT system_config_default_shift_id_fkey FOREIGN KEY (default_shift_id) REFERENCES shift(id)
);

-- Table: user
CREATE TABLE IF NOT EXISTS user (
    id integer NOT NULL DEFAULT nextval('user_id_seq'::regclass),
    username character varying NOT NULL,
    email character varying NOT NULL,
    password_hash character varying NULL,
    is_admin boolean NULL,
    is_active boolean NULL,
    odoo_id integer NULL,
    created_at timestamp without time zone NULL,
    last_login timestamp without time zone NULL,
    force_password_change boolean NULL,
    role character varying NULL DEFAULT 'employee'::character varying,
    department character varying NULL,
    CONSTRAINT user_pkey PRIMARY KEY (id),
    CONSTRAINT user_username_key UNIQUE (username),
    CONSTRAINT user_email_key UNIQUE (email)
);

-- Table: bonus_question
CREATE TABLE IF NOT EXISTS bonus_question (
    id integer NOT NULL DEFAULT nextval('bonus_question_id_seq'::regclass),
    department character varying NOT NULL,
    question_text character varying NOT NULL,
    min_value integer NOT NULL DEFAULT 1,
    max_value integer NOT NULL DEFAULT 10,
    default_value integer NOT NULL DEFAULT 5,
    weight double precision NOT NULL DEFAULT 1.0,
    is_active boolean NOT NULL DEFAULT true,
    created_by integer NULL,
    created_at timestamp without time zone NULL DEFAULT NOW(),
    updated_at timestamp without time zone NULL DEFAULT NOW(),
    CONSTRAINT bonus_question_pkey PRIMARY KEY (id),
    CONSTRAINT bonus_question_created_by_fkey FOREIGN KEY (created_by) REFERENCES "user"(id)
);

-- Table: bonus_evaluation_period
CREATE TABLE IF NOT EXISTS bonus_evaluation_period (
    id integer NOT NULL DEFAULT nextval('bonus_evaluation_period_id_seq'::regclass),
    name character varying NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    status character varying NOT NULL DEFAULT 'open',
    created_by integer NULL,
    created_at timestamp without time zone NULL DEFAULT NOW(),
    CONSTRAINT bonus_evaluation_period_pkey PRIMARY KEY (id),
    CONSTRAINT bonus_evaluation_period_created_by_fkey FOREIGN KEY (created_by) REFERENCES "user"(id)
);

-- Table: bonus_submission
CREATE TABLE IF NOT EXISTS bonus_submission (
    id integer NOT NULL DEFAULT nextval('bonus_submission_id_seq'::regclass),
    period_id integer NOT NULL,
    department character varying NOT NULL,
    status character varying NOT NULL DEFAULT 'draft',
    submitted_by integer NULL,
    submitted_at timestamp without time zone NULL,
    reviewed_by integer NULL,
    reviewed_at timestamp without time zone NULL,
    notes text NULL,
    created_at timestamp without time zone NULL DEFAULT NOW(),
    updated_at timestamp without time zone NULL DEFAULT NOW(),
    approval_level integer NOT NULL DEFAULT 0,
    approvers jsonb NOT NULL DEFAULT '[]'::jsonb,
    supervisor_id integer NULL,
    CONSTRAINT bonus_submission_pkey PRIMARY KEY (id),
    CONSTRAINT bonus_submission_period_id_fkey FOREIGN KEY (period_id) REFERENCES bonus_evaluation_period(id),
    CONSTRAINT bonus_submission_submitted_by_fkey FOREIGN KEY (submitted_by) REFERENCES "user"(id),
    CONSTRAINT bonus_submission_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES "user"(id),
    CONSTRAINT bonus_submission_supervisor_id_fkey FOREIGN KEY (supervisor_id) REFERENCES employee(id)
);

-- Table: bonus_evaluation
CREATE TABLE IF NOT EXISTS bonus_evaluation (
    id integer NOT NULL DEFAULT nextval('bonus_evaluation_id_seq'::regclass),
    submission_id integer NOT NULL,
    employee_id integer NOT NULL,
    question_id integer NOT NULL,
    value integer NOT NULL,
    original_value integer NULL,
    notes text NULL,
    created_at timestamp without time zone NULL DEFAULT NOW(),
    updated_at timestamp without time zone NULL DEFAULT NOW(),
    CONSTRAINT bonus_evaluation_pkey PRIMARY KEY (id),
    CONSTRAINT bonus_evaluation_submission_id_fkey FOREIGN KEY (submission_id) REFERENCES bonus_submission(id),
    CONSTRAINT bonus_evaluation_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES employee(id),
    CONSTRAINT bonus_evaluation_question_id_fkey FOREIGN KEY (question_id) REFERENCES bonus_question(id)
);

-- Table: bonus_audit_log
CREATE TABLE IF NOT EXISTS bonus_audit_log (
    id integer NOT NULL DEFAULT nextval('bonus_audit_log_id_seq'::regclass),
    submission_id integer NULL,
    employee_id integer NULL,
    question_id integer NULL,
    action character varying NOT NULL,
    old_value integer NULL,
    new_value integer NULL,
    notes text NULL,
    user_id integer NULL,
    timestamp timestamp without time zone NULL DEFAULT NOW(),
    CONSTRAINT bonus_audit_log_pkey PRIMARY KEY (id),
    CONSTRAINT bonus_audit_log_submission_id_fkey FOREIGN KEY (submission_id) REFERENCES bonus_submission(id),
    CONSTRAINT bonus_audit_log_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES employee(id),
    CONSTRAINT bonus_audit_log_question_id_fkey FOREIGN KEY (question_id) REFERENCES bonus_question(id),
    CONSTRAINT bonus_audit_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES "user"(id)
);

-- Indexes for table: user
CREATE INDEX ix_user_role ON public."user" USING btree (role);

-- Note: This schema is for reference only and includes all tables and sequences.
-- If you want to recreate the database, run the sequences first, then the tables in dependency order.