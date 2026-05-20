import logging
import os
import xmlrpc.client

from models import OdooConfig

logger = logging.getLogger(__name__)

# Optional in-code defaults for local/UAT when shell exports are not used.
# Replace with your ERP values if you prefer code-based setup.
DEFAULT_ODOO_URL = ""
DEFAULT_ODOO_DB = ""
DEFAULT_ODOO_USERNAME = ""
DEFAULT_ODOO_PASSWORD = ""


def _get_odoo_credentials():
    """Resolve Odoo credentials from env, then DB config, then code defaults."""
    env_url = os.environ.get("ODOO_URL", "").strip().rstrip("/")
    env_db = os.environ.get("ODOO_DB", "").strip()
    env_username = os.environ.get("ODOO_USERNAME", "").strip()
    env_password = os.environ.get("ODOO_PASSWORD", "").strip()

    if all([env_url, env_db, env_username, env_password]):
        return env_url, env_db, env_username, env_password

    config = OdooConfig.query.first()
    if config and config.url and config.database and config.username and config.api_key:
        return (
            config.url.strip().rstrip("/"),
            config.database.strip(),
            config.username.strip(),
            config.api_key.strip(),
        )

    return (
        DEFAULT_ODOO_URL.strip().rstrip("/"),
        DEFAULT_ODOO_DB.strip(),
        DEFAULT_ODOO_USERNAME.strip(),
        DEFAULT_ODOO_PASSWORD.strip(),
    )


def get_odoo_connection():
    """Return an authenticated Odoo XML-RPC object proxy."""
    url, db, username, password = _get_odoo_credentials()

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
