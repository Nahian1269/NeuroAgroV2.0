"""
Small Supabase REST bridge used to mirror local Flask records into Supabase.

The app still uses SQLAlchemy for its local runtime state. When Supabase
credentials are present, important records are also inserted into matching
Supabase tables so sensor and recommendation history is available remotely.
"""

import os
from datetime import date, datetime
from time import time
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv


load_dotenv()


def is_configured():
    url, key = get_supabase_settings()
    return bool(url and key)


def get_supabase_settings():
    if os.environ.get("SUPABASE_SYNC_ENABLED", "true").lower() in {"0", "false", "no", "off"}:
        return None, None

    url = os.environ.get("SUPABASE_URL") or os.environ.get("VITE_SUPABASE_URL")
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_PUBLISHABLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("VITE_SUPABASE_PUBLISHABLE_KEY")
    )
    return url, key


def supabase_headers(prefer="return=minimal"):
    _, supabase_key = get_supabase_settings()
    return {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def insert_record(table, payload, logger=None):
    """Insert one record into Supabase. Failures are logged but non-fatal."""
    supabase_url, supabase_key = get_supabase_settings()
    if not supabase_url or not supabase_key:
        return {"enabled": False}

    base_endpoint = f"{supabase_url.rstrip('/')}/rest/v1/{table}"
    use_upsert = payload.get("local_id") is not None
    endpoint = f"{base_endpoint}?on_conflict=local_id" if use_upsert else base_endpoint
    headers = supabase_headers("resolution=merge-duplicates,return=minimal" if use_upsert else "return=minimal")

    try:
        response = requests.post(endpoint, headers=headers, json=_json_safe(payload), timeout=8)
        if response.status_code == 400 and use_upsert:
            fallback = requests.post(
                base_endpoint,
                headers=supabase_headers("return=minimal"),
                json=_json_safe(payload),
                timeout=8
            )
            fallback.raise_for_status()
            if logger:
                logger.info("Supabase insert fallback used for %s; apply supabase_schema.sql indexes for upserts.", table)
            return {"enabled": True, "ok": True, "fallback": "insert"}
        response.raise_for_status()
        return {"enabled": True, "ok": True}
    except requests.RequestException as exc:
        if logger:
            logger.warning("Supabase insert failed for %s: %s", table, exc)
        return {"enabled": True, "ok": False, "error": str(exc)}


def delete_records(table, filters, logger=None):
    """Delete mirrored records from Supabase with simple equality filters."""
    supabase_url, supabase_key = get_supabase_settings()
    if not supabase_url or not supabase_key:
        return {"enabled": False}

    query = urlencode({field: f"eq.{value}" for field, value in filters.items()})
    endpoint = f"{supabase_url.rstrip('/')}/rest/v1/{table}?{query}"

    try:
        response = requests.delete(endpoint, headers=supabase_headers(), timeout=8)
        response.raise_for_status()
        return {"enabled": True, "ok": True}
    except requests.RequestException as exc:
        if logger:
            logger.warning("Supabase delete failed for %s: %s", table, exc)
        return {"enabled": True, "ok": False, "error": str(exc)}


def check_write_access():
    probe_id = -int(time() * 1000)
    payload = {
        "local_id": probe_id,
        "user_id": probe_id,
        "notification_type": "connectivity_probe",
        "title": "Connectivity Probe",
        "message": "Temporary NuroAgro Supabase write probe",
        "triggered_by": "system",
    }
    insert_result = insert_record("notifications", payload)
    delete_result = delete_records("notifications", {"local_id": probe_id})
    return {
        "ok": bool(insert_result.get("ok") and delete_result.get("ok")),
        "insert": insert_result,
        "delete": delete_result,
    }


def check_connection(tables=None, include_write=False):
    """Check Supabase REST reachability and whether expected tables exist."""
    supabase_url, supabase_key = get_supabase_settings()
    if not supabase_url or not supabase_key:
        return {"configured": False, "ok": False, "read_ok": False, "write_ok": False, "tables": {}}

    table_results = {}
    for table in tables or ["users", "sensor_readings", "projects"]:
        endpoint = f"{supabase_url.rstrip('/')}/rest/v1/{table}?select=id,local_id&limit=1"
        try:
            response = requests.get(endpoint, headers=supabase_headers(), timeout=8)
            table_results[table] = {
                "ok": response.status_code < 400,
                "status_code": response.status_code,
            }
        except requests.RequestException as exc:
            table_results[table] = {"ok": False, "error": str(exc)}

    read_ok = all(item.get("ok") for item in table_results.values())
    write_result = check_write_access() if include_write and read_ok else {"ok": False}

    return {
        "configured": True,
        "ok": bool(read_ok and (write_result.get("ok") if include_write else True)),
        "read_ok": read_ok,
        "write_ok": bool(write_result.get("ok")),
        "write_check": write_result if include_write else None,
        "tables": table_results,
    }


def model_payload(model, fields):
    return {field: getattr(model, field) for field in fields}
