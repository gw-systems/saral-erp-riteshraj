"""
Bigin sync utilities - Python port of your Google Apps Script (selected features).
File: integrations/bigin/bigin_sync.py
NOW INCLUDES: Notes fetching functionality
"""

import time
import json
import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import List, Dict, Optional, Set

import requests
from django.conf import settings
from django.utils import timezone as django_timezone

from .models import BiginAuthToken, BiginContact
from django.db import transaction

logger = logging.getLogger("integrations.bigin")

# -------------------------
# CONFIG (mirror of Apps Script)
# -------------------------
CONFIG = {
    # API
    "API_BASE_URL": getattr(settings, "BIGIN_API_BASE_URL", "https://www.zohoapis.com/bigin/v2"),
    "MODULE": "Contacts",
    "FIELDS_TO_DOWNLOAD": [
        "Account_Name", "Area_Requirement", "Bussiness_Type",
        "Created_By", "Created_Time", "Description", "Email", "Email_Opt_Out",
        "First_Name", "Full_Name", "Industry_Type", "Last_Activity_Time",
        "Last_Name","Reason", "Lead_Source",
        "Mailing_Country", "Mailing_State", "Mailing_Street",
        "Mobile", "Modified_By", "Modified_Time", "Owner", "Record_Creation_Source_ID__s",
        "Record_Image", "Status", "Status_of_Action", "Tag", "Title", "Type",
        "Unsubscribed_Mode", "Unsubscribed_Time", "Priority",
        "id", "Business_Model", "Locations"
    ],
    "PER_PAGE": 200,
    "TOKEN_REFRESH_BUFFER_SECONDS": 5 * 60,
    "AUTO_UPDATE_MIN_DATE": getattr(settings, "BIGIN_AUTO_UPDATE_MIN_DATE", "2025-05-01"),
    "RECORDS_PER_COQL_PAGE": 200,
}

# -------------------------
# Helper: Token management
# -------------------------
def _get_token_record() -> BiginAuthToken:
    token = BiginAuthToken.objects.first()
    if not token:
        raise RuntimeError("No BiginAuthToken record found — run OAuth flow first.")
    return token


def ensure_valid_token(force_refresh: bool = False) -> str:
    """
    Return a valid access token. Refresh using stored refresh_token if expired or forced.
    Uses BiginAuthToken model with encrypted token storage.
    """
    token_obj = _get_token_record()
    now = django_timezone.now()

    # if not expired and not forced, return decrypted access token
    if not token_obj.is_expired() and not force_refresh:
        return token_obj.get_decrypted_access_token()

    # refresh - use decrypted refresh token
    refresh_token = token_obj.get_decrypted_refresh_token()

    # Get client credentials from database settings (priority) or environment
    from integrations.bigin.utils.settings_helper import get_bigin_config
    bigin_config = get_bigin_config()

    client_id = bigin_config['client_id']
    client_secret = bigin_config['client_secret']
    redirect_uri = bigin_config['redirect_uri']

    if not client_id or not client_secret:
        raise RuntimeError("ZOHO_CLIENT_ID or ZOHO_CLIENT_SECRET missing in settings.")

    data = {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token"
    }
    # if user used redirect_uri-specific console, include it
    if redirect_uri:
        data["redirect_uri"] = redirect_uri

    token_url = bigin_config['token_url']
    logger.debug("Refreshing token using %s", token_url)
    resp = requests.post(token_url, data=data, timeout=15)
    try:
        resp.raise_for_status()
    except Exception:
        # include body for debugging
        logger.error("Failed to refresh token: status=%s body=%s", resp.status_code, resp.text)
        raise RuntimeError(f"Token refresh failed: {resp.text}")

    payload = resp.json()
    if "access_token" not in payload:
        logger.error("Unexpected token response: %s", payload)
        raise RuntimeError(f"Token refresh failed: {payload}")

    # Use set_tokens to encrypt and store the new access token
    # Keep the same refresh token (it doesn't change)
    new_access_token = payload["access_token"]
    token_obj.set_tokens(access_token=new_access_token, refresh_token=refresh_token)

    expires_in = payload.get("expires_in", 3600)
    token_obj.expires_at = django_timezone.now() + timedelta(seconds=expires_in)
    token_obj.save()

    logger.info("Token refreshed successfully.")
    return new_access_token


# -------------------------
# API helpers
# -------------------------
def _headers_for(token: str) -> Dict[str, str]:
    return {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}


def _get(url: str, token: str, params: Optional[Dict] = None) -> requests.Response:
    logger.debug("GET %s params=%s", url, params)
    return requests.get(url, headers=_headers_for(token), params=params, timeout=30)


def _post(url: str, token: str, json_data: Dict) -> requests.Response:
    logger.debug("POST %s json=%s", url, json_data)
    return requests.post(url, headers=_headers_for(token), json=json_data, timeout=30)


def _put(url: str, token: str, json_data: Dict) -> requests.Response:
    logger.debug("PUT %s json=%s", url, json_data)
    return requests.put(url, headers=_headers_for(token), json=json_data, timeout=30)


def _delete(url: str, token: str) -> requests.Response:
    logger.debug("DELETE %s", url)
    return requests.delete(url, headers=_headers_for(token), timeout=30)


# -------------------------
# NEW: Notes fetching functionality
# -------------------------
def fetch_contact_notes(contact_id: str) -> str:
    """
    Fetch notes for a specific contact and return formatted string.
    Mirrors the Google Apps Script fetchContactNotes function.
    
    Returns:
        Formatted string with notes like:
        "[2025-12-17 10:56 by Shaila jadhav]
        Note content here
        
        ---
        
        [2025-12-17 12:58 by T Manjunath]
        Another note"
    """
    access_token = ensure_valid_token()
    base = CONFIG["API_BASE_URL"].rstrip("/")
    module = CONFIG["MODULE"]
    
    url = f"{base}/{module}/{contact_id}/Notes"
    params = {"fields": "Note_Content,Owner,Created_Time,id"}
    
    try:
        resp = _get(url, access_token, params=params)
        
        # Handle no notes
        if resp.status_code == 204:
            return "[No Notes Found]"
        
        # Handle deleted record
        if resp.status_code == 400 and "invalid id" in resp.text.lower():
            logger.warning(f"Contact ID {contact_id} not found in Bigin (likely deleted).")
            return "[Record Deleted in Bigin]"
        
        # Handle other errors
        if resp.status_code != 200:
            logger.error(f"API Error fetching notes for ID {contact_id}. Code: {resp.status_code}, Response: {resp.text}")
            return f"[API Error Code: {resp.status_code}]"
        
        data = resp.json()
        notes = data.get("data", [])
        
        if not notes:
            return "[No Notes Found]"
        
        # Sort by Created_Time descending (newest first)
        notes.sort(key=lambda x: x.get("Created_Time", ""), reverse=True)
        
        # Format notes
        formatted_notes = []
        for note in notes:
            created_time = note.get("Created_Time", "")
            owner_name = note.get("Owner", {}).get("name", "Unknown User") if isinstance(note.get("Owner"), dict) else "Unknown User"
            content = note.get("Note_Content", "")
            
            # Format timestamp
            if created_time:
                try:
                    dt = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    formatted_time = created_time
            else:
                formatted_time = "Unknown Date"
            
            formatted_notes.append(f"[{formatted_time} by {owner_name}]\n{content}")
        
        return "\n\n---\n\n".join(formatted_notes)
        
    except Exception as e:
        logger.error(f"Exception in fetch_contact_notes for ID {contact_id}: {e}")
        return f"[Script Error: {str(e)}]"


# -------------------------
# Core: download all contacts and save to DB
# -------------------------
def download_bigin_contacts(start_date: Optional[datetime] = None, save_raw: bool = True) -> List[BiginContact]:
    """
    Full download of Contacts with BULK operations for performance.
    Processes records in batches of 200 for efficient DB operations.
    """
    access_token = ensure_valid_token()
    base = CONFIG["API_BASE_URL"].rstrip("/")
    module = CONFIG["MODULE"]
    fields = CONFIG["FIELDS_TO_DOWNLOAD"]
    per_page = CONFIG["PER_PAGE"]

    fields_param = ",".join(list(dict.fromkeys(fields + ["id", "Created_Time", "Modified_Time"])))

    page_token = None
    page_count = 0
    total_processed = 0

    while True:
        # Re-validate token every 10 pages to handle long-running syncs
        if page_count > 0 and page_count % 10 == 0:
            access_token = ensure_valid_token()

        url = f"{base}/{module}"
        params = {
            "fields": fields_param,
            "per_page": per_page,
            "sort_by": "Created_Time",
            "sort_order": "desc"
        }
        if page_token:
            params["page_token"] = page_token

        resp = _get(url, access_token, params=params)
        
        if resp.status_code == 204:
            logger.info("No content returned for contacts page.")
            break

        if resp.status_code >= 400:
            logger.error("Fetch contacts error: %s", resp.text)
            raise RuntimeError(f"Failed to fetch contacts: {resp.status_code} {resp.text}")

        data = resp.json()
        records = data.get("data", [])
        if not records:
            break

        # Filter by start_date if provided
        if start_date:
            records = [r for r in records if _created_time_ge(r.get("Created_Time"), start_date)]

        # Bulk save records
        saved_count = _bulk_save_contacts(records, save_raw=save_raw)
        total_processed += saved_count
        page_count += 1
        
        # Log progress every 10 pages (2000 records)
        if page_count % 10 == 0:
            logger.info(f"Processed {total_processed} contacts ({page_count} pages)...")

        # Page continuation
        info = data.get("info", {})
        if info.get("more_records") and info.get("next_page_token"):
            page_token = info["next_page_token"]
            time.sleep(0.3)
        else:
            break

    logger.info(f"✅ Downloaded {total_processed} contacts from Bigin in {page_count} pages.")
    return BiginContact.objects.all()[:total_processed]


@transaction.atomic
def _bulk_save_contacts(records: list, save_raw: bool = True) -> int:
    """
    Bulk save/update contacts using update_or_create in a single transaction.
    Much faster than one-by-one saves.
    
    Returns: Number of records processed
    """
    from django.db import IntegrityError
    
    # Extract all bigin_ids from this batch
    bigin_ids = [str(r.get("id")) for r in records]
    
    # Get existing records in one query
    existing_records = {
        obj.bigin_id: obj 
        for obj in BiginContact.objects.filter(bigin_id__in=bigin_ids, module='Contacts')
    }
    
    to_create = []
    to_update = []
    
    for record in records:
        rec_id = str(record.get("id"))
        contact_data = _extract_contact_data(record, save_raw)
        
        if rec_id in existing_records:
            # Update existing
            obj = existing_records[rec_id]
            for key, value in contact_data.items():
                setattr(obj, key, value)
            to_update.append(obj)
        else:
            # Create new
            to_create.append(BiginContact(
                bigin_id=rec_id,
                module='Contacts',
                **contact_data
            ))
    
    # Bulk create new records
    if to_create:
        try:
            BiginContact.objects.bulk_create(to_create, batch_size=200)
        except IntegrityError:
            # Fallback to one-by-one if there are conflicts
            for obj in to_create:
                try:
                    obj.save()
                except IntegrityError:
                    pass
    

    # Bulk update existing records
    if to_update:
        BiginContact.objects.bulk_update(
            to_update,
            fields=[
                'raw', 'created_time', 'modified_time', 'synced_at',
                'owner', 'account_name', 'full_name', 'email', 'mobile',
                'description', 'contact_type', 'lead_source', 'lead_stage',
                'locations', 'area_requirement', 'status', 'reason',
                'industry_type', 'business_type', 'business_model','notes', 'notes_fetched_at'
            ],
            batch_size=200
        )
    
    return len(records)


def _extract_contact_data(record: dict, save_raw: bool = True) -> dict:
    """
    Extract contact data from raw Bigin record.
    Separated for reusability in bulk operations.
    """
    # Helper functions
    def get_owner_name(owner_data):
        if isinstance(owner_data, dict):
            return owner_data.get("name")
        return None
    
    def get_account_name(account_data):
        if isinstance(account_data, dict):
            return account_data.get("name")
        return None
    
    def join_array(value):
        """Parse JSON array strings and join into comma-separated string"""
        if isinstance(value, list):
            return ", ".join(str(v) for v in value if v)
        elif isinstance(value, str):
            # Try to parse JSON array string like '["3PL","Warehouse"]'
            if value.startswith('[') and value.endswith(']'):
                try:
                    import json
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return ", ".join(str(v) for v in parsed if v)
                except:
                    pass
            # Try to parse Python list string like "['3PL','Warehouse']"
            if value.startswith('[') and value.endswith(']'):
                try:
                    import ast
                    parsed = ast.literal_eval(value)
                    if isinstance(parsed, list):
                        return ", ".join(str(v) for v in parsed if v)
                except:
                    pass
        return value
    
    def extract_first_value(value):
        """Extract first value from array for single-value fields"""
        if isinstance(value, list) and value:
            return str(value[0])
        elif isinstance(value, str):
            # Try to parse JSON array
            if value.startswith('[') and value.endswith(']'):
                try:
                    import json
                    parsed = json.loads(value)
                    if isinstance(parsed, list) and parsed:
                        return str(parsed[0])
                except:
                    pass
            # Try to parse Python list
            if value.startswith('[') and value.endswith(']'):
                try:
                    import ast
                    parsed = ast.literal_eval(value)
                    if isinstance(parsed, list) and parsed:
                        return str(parsed[0])
                except:
                    pass
        return value
    
    return {
        'full_name': record.get("Full_Name"),
        'email': record.get("Email"),
        'mobile': record.get("Mobile"),
        'owner': get_owner_name(record.get("Owner")),
        'account_name': get_account_name(record.get("Account_Name")),
        'description': record.get("Description"),
        'contact_type': extract_first_value(record.get("Type")),  # Extract first value only
        'lead_source': record.get("Lead_Source"),
        'lead_stage': join_array(record.get("Status_of_Action")),  # Keep as comma-separated
        'status': join_array(record.get("Status")),  # Keep as comma-separated
        'reason': record.get("Reason"),
        'locations': record.get("Locations"),
        'area_requirement': record.get("Area_Requirement"),
        'industry_type': record.get("Industry_Type"),
        'business_type': extract_first_value(record.get("Bussiness_Type")),  # Extract first value only
        'business_model': record.get("Business_Model"),  # Keep as string, not datetime
        'created_time': _parse_dt(record.get("Created_Time")),
        'modified_time': _parse_dt(record.get("Modified_Time")),
        'raw': json.dumps(record, default=str) if save_raw else None
    }


def _created_time_ge(created_time_str: str, dt: datetime) -> bool:
    if not created_time_str:
        return False
    try:
        parsed = datetime.fromisoformat(created_time_str.replace("Z", "+00:00"))
        return parsed >= dt.replace(tzinfo=parsed.tzinfo)
    except Exception:
        return False


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
        except Exception:
            return None


# -------------------------
# Notes, Updates, Delete
# -------------------------
def add_note_to_record(record_id: str, content: str) -> None:
    access_token = ensure_valid_token()
    url = f"{CONFIG['API_BASE_URL'].rstrip('/')}/{CONFIG['MODULE']}/{record_id}/Notes"
    payload = {"data": [{"Note_Content": content}]}
    resp = _post(url, access_token, json_data=payload)
    if resp.status_code < 200 or resp.status_code >= 300:
        logger.error("add_note failed: %s", resp.text)
        raise RuntimeError(f"Failed to add note to {record_id}: {resp.status_code} {resp.text}")


def update_bigin_record(record_id: str, update_payload: dict) -> dict:
    access_token = ensure_valid_token()
    url = f"{CONFIG['API_BASE_URL'].rstrip('/')}/{CONFIG['MODULE']}/{record_id}"
    payload = {"data": [update_payload]}
    resp = _put(url, access_token, json_data=payload)
    if resp.status_code < 200 or resp.status_code >= 300:
        logger.error("update_bigin_record failed: %s", resp.text)
        raise RuntimeError(f"Failed to update {record_id}: {resp.status_code} {resp.text}")
    return resp.json()


def delete_bigin_record(record_id: str) -> None:
    access_token = ensure_valid_token()
    url = f"{CONFIG['API_BASE_URL'].rstrip('/')}/{CONFIG['MODULE']}/{record_id}"
    resp = _delete(url, access_token)
    if resp.status_code < 200 or resp.status_code >= 300:
        logger.error("delete_bigin_record failed: %s", resp.text)
        raise RuntimeError(f"Failed to delete {record_id}: {resp.status_code} {resp.text}")


# -------------------------
# Fetch users (map full_name -> id)
# -------------------------
def fetch_bigin_users() -> Dict[str, str]:
    access_token = ensure_valid_token()
    user_map = {}
    page = 1
    while True:
        url = f"{CONFIG['API_BASE_URL'].rstrip('/')}/users"
        params = {"type": "AllUsers", "page": page, "per_page": 200}
        resp = _get(url, access_token, params=params)
        if resp.status_code != 200:
            logger.error("fetch_bigin_users failed: %s", resp.text)
            return user_map
        data = resp.json()
        users = data.get("users", []) or []
        for u in users:
            if u.get("full_name") and u.get("id"):
                user_map[u["full_name"].strip().lower()] = str(u["id"])
        info = data.get("info", {})
        if info.get("more_records"):
            page += 1
            continue
        break
    return user_map


# -------------------------
# COQL helper: fetch all ids (to find records not in Bigin)
# -------------------------
def fetch_all_bigin_ids(min_created: Optional[datetime] = None, max_created: Optional[datetime] = None) -> Set[str]:
    access_token = ensure_valid_token()
    base = CONFIG["API_BASE_URL"].rstrip('/')
    module = CONFIG["MODULE"]
    min_cond = f"(Created_Time >= '{_format_coql_dt(min_created)}')" if min_created else None
    max_cond = f"(Created_Time <= '{_format_coql_dt(max_created)}')" if max_created else None
    criteria = " and ".join([c for c in [min_cond, max_cond] if c])
    select_base = f"select id from {module}" + (f" where {criteria}" if criteria else "")
    offset = 0
    page_limit = CONFIG["RECORDS_PER_COQL_PAGE"]
    ids = set()

    while True:
        q = f"{select_base} order by id asc offset {offset} limit {page_limit}"
        url = f"{base}/coql"
        payload = {"select_query": q}
        resp = _post(url, ensure_valid_token(), json_data=payload)
        if resp.status_code != 200:
            logger.error("COQL fetch failed: %s", resp.text)
            break
        data = resp.json()
        page_records = data.get("data", [])
        if not page_records:
            break
        for r in page_records:
            ids.add(str(r.get("id")))
        if len(page_records) < page_limit:
            break
        offset += len(page_records)
        time.sleep(0.2)
    return ids


def _format_coql_dt(d: Optional[datetime]) -> str:
    if not d: return ""
    # Zoho expects ISO with Z
    return d.astimezone(dt_timezone.utc).isoformat().replace("+00:00", "Z")



# # -------------------------
# # Auto-delete Recent Duplicates
# # -------------------------
# def auto_delete_recent_duplicates(window_minutes: int = 2, max_records: int = 500):
#     """
#     Similar behavior to Apps Script: fetch records created since last run (or last hour),
#     detect duplicates by Email / Full_Name / Mobile and delete duplicates keeping earliest/newest (your choice in script).
#     """
#     now = django_timezone.now()
#     cutoff = now - timedelta(minutes=window_minutes)
#     access_token = ensure_valid_token()
#     # We'll fetch recent records (ascending by Created_Time), then compare
#     fields = ["id", "Created_Time", "Email", "Full_Name", "Mobile"]
#     fields_param = ",".join(fields)
#     base = CONFIG["API_BASE_URL"].rstrip("/")
#     module = CONFIG["MODULE"]
#     per_page = 200

#     all_recent = []
#     page_token = None
#     while len(all_recent) < max_records:
#         params = {
#             "fields": fields_param,
#             "per_page": per_page,
#             "sort_by": "Created_Time",
#             "sort_order": "asc"
#         }
#         if page_token:
#             params["page_token"] = page_token
#         url = f"{base}/{module}"
#         resp = _get(url, access_token, params=params)
#         if resp.status_code != 200:
#             logger.error("auto_delete fetch error: %s", resp.text)
#             break
#         data = resp.json()
#         page_records = data.get("data", [])
#         # filter by cutoff
#         page_records = [r for r in page_records if _created_time_ge(r.get("Created_Time"), cutoff)]
#         all_recent.extend(page_records)
#         info = data.get("info", {})
#         if not info.get("more_records"):
#             break
#         page_token = info.get("next_page_token")
#         time.sleep(0.2)
#     logger.info("Found %d recent records to inspect for duplicates", len(all_recent))

#     processed = set()
#     deleted_count = 0
#     for i, a in enumerate(all_recent):
#         if a["id"] in processed:
#             continue
#         for b in all_recent[i+1:]:
#             if b["id"] in processed:
#                 continue
#             match_type = _check_records_duplicate(a, b)
#             if match_type:
#                 # choose master = earlier created (original script used created comparison)
#                 a_ct = _parse_dt(a.get("Created_Time"))
#                 b_ct = _parse_dt(b.get("Created_Time"))
#                 if a_ct and b_ct and a_ct < b_ct:
#                     master, duplicate = a, b
#                 else:
#                     master, duplicate = b, a
#                 try:
#                     delete_bigin_record(duplicate["id"])
#                     deleted_count += 1
#                     processed.add(duplicate["id"])
#                     logger.info("Deleted duplicate %s of master %s by %s", duplicate["id"], master["id"], match_type)
#                 except Exception as e:
#                     logger.error("Failed to delete duplicate %s: %s", duplicate["id"], e)
#         processed.add(a["id"])
#     logger.info("Auto-delete complete. Deleted %d duplicates.", deleted_count)


# def _check_records_duplicate(a: dict, b: dict) -> Optional[str]:
#     """
#     Return 'Email' / 'Full_Name' / 'Mobile' if duplicates match; else None.
#     Normalization similar to Apps Script.
#     """
#     def norm(v):
#         if not v: return None
#         return "".join(ch for ch in str(v).lower() if ch.isalnum())

#     if a.get("Email") and b.get("Email") and norm(a.get("Email")) == norm(b.get("Email")):
#         return "Email"
#     if a.get("Full_Name") and b.get("Full_Name") and norm(a.get("Full_Name")) == norm(b.get("Full_Name")):
#         return "Full_Name"
#     if a.get("Mobile") and b.get("Mobile") and norm(a.get("Mobile")) == norm(b.get("Mobile")):
#         return "Mobile"
#     return None