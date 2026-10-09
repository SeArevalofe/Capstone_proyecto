from sqlalchemy import text

from app.database.connection import engine


def get_vacation_balance(employee_id: str) -> dict:

    query = text("""
        SELECT
            available_days,
            used_days,
            pending_days
        FROM vacation_balances
        WHERE employee_id = :employee_id
    """)

    with engine.connect() as connection:

        row = connection.execute(
            query,
            {
                "employee_id": employee_id
            }
        ).mappings().first()

    if not row:
        return {
            "found": False,
            "message": "No se encontraron vacaciones."
        }

    return {
        "found": True,
        "available_days": row["available_days"],
        "used_days": row["used_days"],
        "pending_days": row["pending_days"],
    }


def get_employee_assets(employee_id: str) -> list:

    query = text("""
        SELECT
            asset_type,
            asset_name,
            serial_number,
            assigned_at
        FROM employee_assets
        WHERE employee_id = :employee_id
        AND active = 1
    """)

    with engine.connect() as connection:

        rows = connection.execute(
            query,
            {
                "employee_id": employee_id
            }
        ).mappings().all()

    return [
        {
            "type": row["asset_type"],
            "name": row["asset_name"],
            "serial_number": row["serial_number"],
            "assigned_at": row["assigned_at"],
        }
        for row in rows
    ]


def get_employee_services(employee_id: str) -> list:

    query = text("""
        SELECT
            service_name,
            status,
            assigned_at
        FROM employee_services
        WHERE employee_id = :employee_id
        AND status = 'ACTIVE'
    """)

    with engine.connect() as connection:

        rows = connection.execute(
            query,
            {
                "employee_id": employee_id
            }
        ).mappings().all()

    return [
        {
            "service": row["service_name"],
            "status": row["status"],
            "assigned_at": row["assigned_at"],
        }
        for row in rows
    ]