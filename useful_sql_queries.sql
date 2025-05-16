-- Useful SQL Queries for MIR AMS
-- Generated on 2025-05-07

-- 1. Find employees with no attendance records in a date range
SELECT 
    e.id, e.name, e.employee_code, e.department, e.position
FROM 
    employee e
LEFT JOIN 
    attendance_record ar ON e.id = ar.employee_id AND ar.date BETWEEN '2025-03-01' AND '2025-03-31'
WHERE 
    ar.id IS NULL
    AND e.is_active = TRUE
ORDER BY 
    e.name;

-- 2. Find employees who were late (more than grace period) in a date range
SELECT 
    e.name, e.employee_code, e.department,
    ar.date, ar.check_in, s.name as shift_name,
    s.start_time as shift_start,
    (EXTRACT(EPOCH FROM (ar.check_in - (ar.date + s.start_time)))/60)::INTEGER as minutes_late
FROM 
    attendance_record ar
JOIN 
    employee e ON ar.employee_id = e.id
JOIN 
    shift s ON ar.shift_id = s.id
WHERE 
    ar.date BETWEEN '2025-03-01' AND '2025-03-31'
    AND ar.check_in > (ar.date + s.start_time + (s.grace_period_minutes * INTERVAL '1 minute'))
ORDER BY 
    ar.date, minutes_late DESC;

-- 3. Calculate overtime hours by employee and month
SELECT 
    e.name, e.employee_code, e.department,
    DATE_TRUNC('month', ar.date) as month,
    SUM(ar.overtime_hours) as total_overtime_hours
FROM 
    attendance_record ar
JOIN 
    employee e ON ar.employee_id = e.id
WHERE 
    ar.date BETWEEN '2025-01-01' AND '2025-12-31'
    AND ar.status = 'present'
GROUP BY 
    e.id, e.name, e.employee_code, e.department, DATE_TRUNC('month', ar.date)
ORDER BY 
    month, total_overtime_hours DESC;

-- 4. Find duplicate attendance log entries
SELECT 
    employee_id, timestamp::date as log_date, log_type, COUNT(*) as count
FROM 
    attendance_log
GROUP BY 
    employee_id, log_date, log_type
HAVING 
    COUNT(*) > 1
ORDER BY 
    log_date DESC, count DESC;

-- 5. Attendance summary by department for a specific month
SELECT 
    e.department,
    COUNT(DISTINCT e.id) as total_employees,
    SUM(CASE WHEN ar.status = 'present' THEN 1 ELSE 0 END) as present_days,
    SUM(CASE WHEN ar.status = 'absent' THEN 1 ELSE 0 END) as absent_days,
    SUM(CASE WHEN ar.status = 'late' THEN 1 ELSE 0 END) as late_days,
    SUM(CASE WHEN ar.status = 'half-day' THEN 1 ELSE 0 END) as half_days,
    SUM(ar.work_hours) as total_work_hours,
    SUM(ar.overtime_hours) as total_overtime_hours
FROM 
    attendance_record ar
JOIN 
    employee e ON ar.employee_id = e.id
WHERE 
    ar.date BETWEEN '2025-03-01' AND '2025-03-31'
GROUP BY 
    e.department
ORDER BY 
    total_employees DESC;

-- 6. Find employees with attendance anomalies (missing check-ins or check-outs)
SELECT 
    e.name, e.employee_code, ar.date,
    CASE 
        WHEN ar.check_in IS NULL THEN 'Missing check-in'
        WHEN ar.check_out IS NULL THEN 'Missing check-out'
    END as anomaly_type
FROM 
    attendance_record ar
JOIN 
    employee e ON ar.employee_id = e.id
WHERE 
    ar.date BETWEEN '2025-03-01' AND '2025-03-31'
    AND (ar.check_in IS NULL OR ar.check_out IS NULL)
    AND ar.status != 'absent'
ORDER BY 
    ar.date DESC, e.name;

-- 7. Working hours by employee for a specific month
SELECT 
    e.name, e.employee_code, e.department,
    COUNT(ar.id) as days_worked,
    SUM(ar.work_hours) as total_hours,
    ROUND(AVG(ar.work_hours), 2) as avg_hours_per_day,
    SUM(ar.overtime_hours) as overtime_hours
FROM 
    attendance_record ar
JOIN 
    employee e ON ar.employee_id = e.id
WHERE 
    ar.date BETWEEN '2025-03-01' AND '2025-03-31'
    AND ar.status IN ('present', 'late', 'half-day')
GROUP BY 
    e.id, e.name, e.employee_code, e.department
ORDER BY 
    total_hours DESC;

-- 8. Find devices with connectivity issues (no recent pings)
SELECT 
    id, name, device_id, device_type, ip_address,
    last_ping, 
    CURRENT_TIMESTAMP - last_ping as time_since_last_ping
FROM 
    attendance_device
WHERE 
    is_active = TRUE
    AND (last_ping IS NULL OR last_ping < CURRENT_TIMESTAMP - INTERVAL '24 hours')
ORDER BY 
    last_ping NULLS FIRST;

-- 9. Compare employee attendance vs. shift assignments
SELECT 
    e.name, e.employee_code,
    s.name as assigned_shift,
    s.start_time as assigned_start,
    s.end_time as assigned_end,
    COUNT(ar.id) as total_days,
    ROUND(AVG(EXTRACT(HOUR FROM ar.check_in) + EXTRACT(MINUTE FROM ar.check_in)/60), 2) as avg_check_in_time,
    ROUND(AVG(EXTRACT(HOUR FROM ar.check_out) + EXTRACT(MINUTE FROM ar.check_out)/60), 2) as avg_check_out_time
FROM 
    employee e
JOIN 
    shift_assignment sa ON e.id = sa.employee_id
JOIN 
    shift s ON sa.shift_id = s.id
LEFT JOIN 
    attendance_record ar ON e.id = ar.employee_id AND 
    ar.date BETWEEN sa.start_date AND COALESCE(sa.end_date, CURRENT_DATE)
WHERE 
    sa.is_active = TRUE
    AND ar.date BETWEEN '2025-03-01' AND '2025-03-31'
GROUP BY 
    e.id, e.name, e.employee_code, s.id, s.name, s.start_time, s.end_time
ORDER BY 
    e.name;

-- 10. Find and clean up duplicate attendance records
WITH duplicates AS (
    SELECT 
        employee_id, date, 
        ROW_NUMBER() OVER (PARTITION BY employee_id, date ORDER BY created_at DESC) as row_num
    FROM 
        attendance_record
)
-- This query finds the duplicates (don't delete without verification!)
SELECT 
    ar.id, e.name, e.employee_code, ar.date, ar.check_in, ar.check_out,
    ar.created_at, ar.updated_at
FROM 
    duplicates d
JOIN 
    attendance_record ar ON d.employee_id = ar.employee_id AND d.date = ar.date
JOIN 
    employee e ON ar.employee_id = e.id
WHERE 
    d.row_num > 1
ORDER BY 
    e.name, ar.date;