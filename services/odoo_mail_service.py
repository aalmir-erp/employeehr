import logging
import os
import xmlrpc.client

logger = logging.getLogger(__name__)


def get_odoo_connection():
    """Return an authenticated Odoo XML-RPC object proxy."""
    url = os.environ.get("ODOO_URL", "").rstrip("/")
    db = os.environ.get("ODOO_DB", "")
    username = os.environ.get("ODOO_USERNAME", "")
    password = os.environ.get("ODOO_PASSWORD", "")

    if not all([url, db, username, password]):
        logger.error("Odoo mail connection settings are incomplete")
        return None, None, None, None

    try:
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        uid = common.authenticate(db, username, password, {})

        if not uid:
            logger.error("Odoo mail authentication failed")
            return None, None, None, None

        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        return models, db, uid, password

    except Exception as exc:
        logger.exception("Odoo mail connection unavailable: %s", exc)
        return None, None, None, None


def send_email_via_odoo(subject, body_html, email_to, email_cc=None, email_from=None):
    """Create and send an Odoo mail.mail record using ERP SMTP."""
    models, db, uid, password = get_odoo_connection()
    if not models:
        return {"success": False, "error": "Odoo connection unavailable"}

    values = {
        "subject": subject,
        "body_html": body_html,
        "email_to": email_to,
    }

    if email_cc:
        values["email_cc"] = email_cc

    if email_from:
        values["email_from"] = email_from

    try:
        mail_id = models.execute_kw(
            db,
            uid,
            password,
            "mail.mail",
            "create",
            [values],
        )

        models.execute_kw(
            db,
            uid,
            password,
            "mail.mail",
            "send",
            [[mail_id]],
        )

        return {"success": True, "mail_id": mail_id}

    except Exception as exc:
        logger.exception("Failed to send Odoo email: %s", exc)
        return {"success": False, "error": str(exc)}
