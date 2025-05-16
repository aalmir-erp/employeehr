# Database Backup and Restore Guide for MIR AMS

This document provides instructions for backing up and restoring your MIR AMS database.

## Backing Up Your Database

### Method 1: Using pg_dump (recommended)

```bash
# Export the full database with data
pg_dump -h $PGHOST -U $PGUSER -d $PGDATABASE -F c -f mir_ams_backup.dump

# Export only the schema (no data)
pg_dump -h $PGHOST -U $PGUSER -d $PGDATABASE --schema-only -f mir_ams_schema.sql

# Export only data (no schema)
pg_dump -h $PGHOST -U $PGUSER -d $PGDATABASE --data-only -f mir_ams_data.sql
```

### Method 2: Using SQL queries to extract data

If you need to extract specific data for reports, you can use the SQL queries:

```sql
-- Export all attendance records to CSV
COPY (
    SELECT 
        e.name as employee_name, 
        e.employee_code,
        ar.date,
        ar.check_in,
        ar.check_out,
        ar.status,
        ar.work_hours,
        ar.overtime_hours,
        s.name as shift_name
    FROM 
        attendance_record ar
    JOIN 
        employee e ON ar.employee_id = e.id
    LEFT JOIN 
        shift s ON ar.shift_id = s.id
    ORDER BY 
        ar.date DESC, e.name
) TO '/tmp/attendance_export.csv' WITH CSV HEADER;
```

## Restoring Your Database

### Method 1: Using pg_restore (for .dump files)

```bash
# Restore from a full backup dump file
pg_restore -h $PGHOST -U $PGUSER -d $PGDATABASE -c mir_ams_backup.dump
```

### Method 2: Using psql (for .sql files)

```bash
# Restore schema
psql -h $PGHOST -U $PGUSER -d $PGDATABASE -f mir_ams_schema.sql

# Restore data
psql -h $PGHOST -U $PGUSER -d $PGDATABASE -f mir_ams_data.sql

# Or restore from our full database_schema.sql (creates empty tables)
psql -h $PGHOST -U $PGUSER -d $PGDATABASE -f database_schema.sql
```

### Method 3: Using Flask migrations

If you're using the Flask migration system:

```bash
# Apply all migrations to update the database
flask db upgrade
```

## Migration Commands

To generate and apply migrations after model changes:

```bash
# Generate a migration after model changes
flask db migrate -m "Description of changes"

# Apply the migration
flask db upgrade

# Rollback one migration
flask db downgrade
```

## Applying Our Latest Migration

To apply our latest migration that enhances attendance import and deletion:

```bash
# From the project root directory
flask db upgrade head
```

This will apply the `c45e6bc23f9a_enhance_attendance_import_and_deletion.py` migration and add the necessary indexes for improved performance.