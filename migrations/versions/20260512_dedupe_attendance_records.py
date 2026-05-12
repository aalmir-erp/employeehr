"""Dedupe attendance records and enforce one record per employee date

Revision ID: 20260512_dedupe_attendance_records
Revises: 035c401d7d70
Create Date: 2026-05-12 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '20260512_dedupe_attendance_records'
down_revision = '035c401d7d70'
branch_labels = None
depends_on = None


CONSTRAINT_NAME = 'uq_attendance_record_employee_date'


def upgrade():
    # Consolidate existing duplicate rows before adding the unique constraint.
    # Keep the row with the richest attendance data, prefer non-absent records,
    # then the most recently updated/newest row as a deterministic tie breaker.
    op.execute("""
        WITH ranked_records AS (
            SELECT
                id,
                FIRST_VALUE(id) OVER (
                    PARTITION BY employee_id, date
                    ORDER BY
                        CASE WHEN check_in IS NOT NULL THEN 0 ELSE 1 END,
                        CASE WHEN check_out IS NOT NULL THEN 0 ELSE 1 END,
                        CASE WHEN status <> 'absent' THEN 0 ELSE 1 END,
                        COALESCE(updated_at, created_at) DESC NULLS LAST,
                        id DESC
                ) AS keeper_id,
                ROW_NUMBER() OVER (
                    PARTITION BY employee_id, date
                    ORDER BY
                        CASE WHEN check_in IS NOT NULL THEN 0 ELSE 1 END,
                        CASE WHEN check_out IS NOT NULL THEN 0 ELSE 1 END,
                        CASE WHEN status <> 'absent' THEN 0 ELSE 1 END,
                        COALESCE(updated_at, created_at) DESC NULLS LAST,
                        id DESC
                ) AS row_num
            FROM attendance_record
        ), duplicate_records AS (
            SELECT id, keeper_id
            FROM ranked_records
            WHERE row_num > 1
        )
        UPDATE attendance_log AS log
        SET attendance_record_id = duplicate_records.keeper_id
        FROM duplicate_records
        WHERE log.attendance_record_id = duplicate_records.id;
    """)
    op.execute("""
        WITH ranked_records AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY employee_id, date
                    ORDER BY
                        CASE WHEN check_in IS NOT NULL THEN 0 ELSE 1 END,
                        CASE WHEN check_out IS NOT NULL THEN 0 ELSE 1 END,
                        CASE WHEN status <> 'absent' THEN 0 ELSE 1 END,
                        COALESCE(updated_at, created_at) DESC NULLS LAST,
                        id DESC
                ) AS row_num
            FROM attendance_record
        )
        DELETE FROM attendance_record
        WHERE id IN (
            SELECT id
            FROM ranked_records
            WHERE row_num > 1
        );
    """)

    # Repair historical records created by the old incomplete-punch logic.
    # OUT-only days were previously saved as missing_out with both summary
    # timestamps empty, even though the raw attendance_log row still contained
    # the checkout punch.
    op.execute("""
        WITH day_logs AS (
            SELECT
                employee_id,
                timestamp::date AS log_date,
                MIN(timestamp) FILTER (WHERE log_type IN ('IN', 'check_in')) AS first_in,
                MAX(timestamp) FILTER (WHERE log_type IN ('OUT', 'check_out')) AS last_out
            FROM attendance_log
            GROUP BY employee_id, timestamp::date
        )
        UPDATE attendance_record AS record
        SET
            check_out = day_logs.last_out,
            status = 'missing_in',
            updated_at = CURRENT_TIMESTAMP
        FROM day_logs
        WHERE record.employee_id = day_logs.employee_id
            AND record.date = day_logs.log_date
            AND record.check_in IS NULL
            AND record.check_out IS NULL
            AND day_logs.first_in IS NULL
            AND day_logs.last_out IS NOT NULL
            AND record.status IN ('missing_out', 'missing', 'pending');
    """)

    op.create_unique_constraint(
        CONSTRAINT_NAME,
        'attendance_record',
        ['employee_id', 'date']
    )


def downgrade():
    op.drop_constraint(CONSTRAINT_NAME, 'attendance_record', type_='unique')
