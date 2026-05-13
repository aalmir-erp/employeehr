"""Dedupe attendance records and enforce one record per employee date

Revision ID: 20260512_attendance_dedupe
Revises: 035c401d7d70
Create Date: 2026-05-12 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '20260512_attendance_dedupe'
down_revision = '035c401d7d70'
branch_labels = None
depends_on = None


CONSTRAINT_NAME = 'uq_attendance_record_employee_date'


def upgrade():
    # Build the duplicate map once and reuse it.  This avoids ranking the full
    # attendance_record table twice, which made the migration look stuck on
    # larger databases.
    op.execute("""
        CREATE TEMP TABLE attendance_record_duplicate_map ON COMMIT DROP AS
        WITH duplicate_keys AS (
            SELECT employee_id, date
            FROM attendance_record
            GROUP BY employee_id, date
            HAVING COUNT(*) > 1
        ), ranked_records AS (
            SELECT
                record.id,
                FIRST_VALUE(record.id) OVER (
                    PARTITION BY record.employee_id, record.date
                    ORDER BY
                        CASE WHEN record.check_in IS NOT NULL THEN 0 ELSE 1 END,
                        CASE WHEN record.check_out IS NOT NULL THEN 0 ELSE 1 END,
                        CASE WHEN record.status <> 'absent' THEN 0 ELSE 1 END,
                        COALESCE(record.updated_at, record.created_at) DESC NULLS LAST,
                        record.id DESC
                ) AS keeper_id,
                ROW_NUMBER() OVER (
                    PARTITION BY record.employee_id, record.date
                    ORDER BY
                        CASE WHEN record.check_in IS NOT NULL THEN 0 ELSE 1 END,
                        CASE WHEN record.check_out IS NOT NULL THEN 0 ELSE 1 END,
                        CASE WHEN record.status <> 'absent' THEN 0 ELSE 1 END,
                        COALESCE(record.updated_at, record.created_at) DESC NULLS LAST,
                        record.id DESC
                ) AS row_num
            FROM attendance_record AS record
            JOIN duplicate_keys
                ON duplicate_keys.employee_id = record.employee_id
                AND duplicate_keys.date = record.date
        )
        SELECT id, keeper_id
        FROM ranked_records
        WHERE row_num > 1;
    """)

    op.execute("""
        UPDATE attendance_log AS log
        SET attendance_record_id = duplicate_map.keeper_id
        FROM attendance_record_duplicate_map AS duplicate_map
        WHERE log.attendance_record_id = duplicate_map.id;
    """)

    op.execute("""
        DELETE FROM attendance_record AS record
        USING attendance_record_duplicate_map AS duplicate_map
        WHERE record.id = duplicate_map.id;
    """)

    # Repair historical records created by the old incomplete-punch logic.
    # OUT-only days were previously saved as missing_out with both summary
    # timestamps empty, even though the raw attendance_log row still contained
    # the checkout punch.  Use per-record indexed lookups instead of grouping
    # the whole attendance_log table.
    op.execute("""
        UPDATE attendance_record AS record
        SET
            check_out = (
                SELECT MAX(log.timestamp)
                FROM attendance_log AS log
                WHERE log.employee_id = record.employee_id
                    AND log.timestamp >= record.date::timestamp
                    AND log.timestamp < record.date::timestamp + INTERVAL '1 day'
                    AND log.log_type IN ('OUT', 'check_out')
            ),
            status = 'missing_in',
            updated_at = CURRENT_TIMESTAMP
        WHERE record.check_in IS NULL
            AND record.check_out IS NULL
            AND record.status IN ('missing_out', 'missing', 'pending')
            AND EXISTS (
                SELECT 1
                FROM attendance_log AS out_log
                WHERE out_log.employee_id = record.employee_id
                    AND out_log.timestamp >= record.date::timestamp
                    AND out_log.timestamp < record.date::timestamp + INTERVAL '1 day'
                    AND out_log.log_type IN ('OUT', 'check_out')
            )
            AND NOT EXISTS (
                SELECT 1
                FROM attendance_log AS in_log
                WHERE in_log.employee_id = record.employee_id
                    AND in_log.timestamp >= record.date::timestamp
                    AND in_log.timestamp < record.date::timestamp + INTERVAL '1 day'
                    AND in_log.log_type IN ('IN', 'check_in')
            );
    """)

    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = '{CONSTRAINT_NAME}'
                    AND conrelid = 'attendance_record'::regclass
            ) THEN
                ALTER TABLE attendance_record
                ADD CONSTRAINT {CONSTRAINT_NAME}
                UNIQUE (employee_id, date);
            END IF;
        END $$;
    """)


def downgrade():
    op.execute(f"""
        ALTER TABLE attendance_record
        DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME};
    """)
