import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.conf import settings
from urllib.parse import urljoin

from .token_manager import get_valid_token

logger = logging.getLogger(__name__)

ZOHO_API_BASE = getattr(settings, "ZOHO_API_BASE", "https://www.zohoapis.com")
BIGIN_BASE = getattr(settings, "BIGIN_API_BASE", "https://bigin.zoho.com/api/v1/")
BIGIN_COQL_URL = getattr(settings, "BIGIN_COQL_URL", "https://www.zohoapis.com/bigin/v2/coql")
DEFAULT_PER_PAGE = 200

# Phase 1: Connection pooling with retry strategy
_session = None

def _get_session():
    """
    Get or create HTTP session with connection pooling.
    Phase 1: Connection pooling
    Phase 3: Enhanced retry with exponential backoff
    """
    global _session
    if _session is None:
        _session = requests.Session()
        # Phase 3: Enhanced retry strategy
        retry_strategy = Retry(
            total=5,  # Increased retries
            backoff_factor=2,  # Exponential: 0, 2, 4, 8, 16 seconds
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"],  # Support all CRUD operations
            respect_retry_after_header=True  # Respect API rate limit headers
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=15,  # Increased pool
            pool_maxsize=30
        )
        _session.mount("https://", adapter)
        _session.mount("http://", adapter)
    return _session

def _headers():
    token = get_valid_token()
    return {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type": "application/json"
    }

def fetch_module_list(module_name, per_page=DEFAULT_PER_PAGE, modified_since=None):
    """
    Fetch list of records for a given module using list endpoint with pagination.
    Returns generator of raw record dicts.

    Phase 2 Optimization: Server-side filtering with modified_since parameter.

    Args:
        module_name: Module to fetch (Contacts, Pipelines, etc.)
        per_page: Records per page (default 200)
        modified_since: datetime object - only fetch records modified after this time
    """
    # Capitalize module name for API (Zoho uses capitalized)
    api_module = module_name.capitalize()

    # Define fields to fetch for each module
    FIELDS_MAP = {
        'Contacts': 'id,Owner,Account_Name,Title,Full_Name,First_Name,Last_Name,Email,Mobile,Description,Type,Lead_Source,Status_of_Action,Locations,Bussiness_Type,Industry_Type,Status,Area_Requirement,Business_Model,Reason,Created_By,Created_Time,Modified_By,Modified_Time,Last_Activity_Time',
        'Pipelines': 'Deal_Name,Stage,Owner,Account_Name,Contact_Name,Conversion_Date,Converted_Area,Created_Time,Modified_Time',
        'Accounts': 'Account_Name,Email,Phone,Owner,Industry,Website,Created_Time,Modified_Time',
        'Products': 'Product_Name,Product_Code,Unit_Price,Owner,Created_Time,Modified_Time',
        'Notes': 'Note_Title,Note_Content,Parent_Id,Owner,Created_Time,Modified_Time',
    }

    # Get fields for this module (or use 'all' as fallback)
    fields = FIELDS_MAP.get(api_module, 'all')

    page_token = None
    is_first_request = True

    while True:
        url = urljoin(BIGIN_BASE, api_module)

        # Build params
        if page_token:
            params = {
                "page_token": page_token,
                "per_page": per_page,
                "fields": fields
            }
        else:
            params = {
                "per_page": per_page,
                "fields": fields
            }

        # Phase 2: Add server-side filtering for incremental syncs
        if modified_since and not page_token:  # Only on first request
            # Format: YYYY-MM-DDTHH:MM:SS+00:00
            modified_time_str = modified_since.strftime("%Y-%m-%dT%H:%M:%S+00:00")
            params["criteria"] = f"(Modified_Time:greater_than:{modified_time_str})"
            logger.info(f"[API Filter] Fetching {api_module} modified after {modified_time_str}")

        logger.debug(f"Fetching {api_module} - params: {params}")

        try:
            session = _get_session()
            resp = session.get(url, headers=_headers(), params=params, timeout=30)

            # Log response for debugging
            logger.debug(f"Response status: {resp.status_code}")

            # Check for empty response
            if not resp.text:
                logger.warning(f"Empty response for {api_module}")
                break

            # Check status code
            if resp.status_code == 204:  # No content
                logger.info(f"No records found for {api_module}")
                break

            if resp.status_code == 404:
                logger.error(f"Module {api_module} not found.")
                raise ValueError(f"Invalid module: {api_module}")

            if resp.status_code == 400:
                # Check if it's the pagination limit error
                try:
                    error_data = resp.json()
                    if error_data.get("code") == "DISCRETE_PAGINATION_LIMIT_EXCEEDED":
                        logger.warning(f"Hit 2000 record limit for {api_module}, cannot fetch more without page_token from previous response")
                        # Unfortunately, we can't continue without a page_token from the last successful response
                        # This is a Zoho API limitation - page_token must be obtained from the info of the last successful page
                        logger.info(f"Synced 2000 records for {api_module} - incremental syncs will handle new records")
                        break
                except:
                    pass
                logger.error(f"Bigin API error {resp.status_code} for {api_module}: {resp.text}")
                resp.raise_for_status()

            if resp.status_code != 200:
                logger.error(f"Bigin API error {resp.status_code} for {api_module}: {resp.text}")
                resp.raise_for_status()

            # Parse JSON
            try:
                data = resp.json()
            except ValueError as e:
                logger.error(f"Failed to parse JSON for {api_module}. Response: {resp.text[:200]}")
                raise

            # Extract records (different modules may use different keys)
            records = data.get("data") or []

            if not records:
                logger.info(f"No more records for {api_module}")
                break

            logger.info(f"Fetched {len(records)} records from {api_module} (page_token: {bool(page_token)})")

            for r in records:
                yield r

            # Check for more pages
            info = data.get("info", {})
            more = info.get("more_records")

            if not more:
                logger.info(f"No more pages for {api_module}")
                break

            # Get next page token (Zoho Bigin uses cursor-based pagination)
            next_token = info.get("next_page_token")
            if next_token:
                page_token = next_token
                logger.debug(f"Got next_page_token for {api_module}")
            else:
                # No more pages if no next_page_token
                logger.info(f"No next_page_token, ending pagination for {api_module}")
                break

            # Phase 3: Adaptive sleep based on API response
            # Check for rate limit headers
            if 'X-RateLimit-Remaining' in resp.headers:
                remaining = int(resp.headers.get('X-RateLimit-Remaining', 100))
                if remaining < 10:
                    time.sleep(0.5)  # Slow down when approaching limit
                elif remaining < 30:
                    time.sleep(0.1)  # Moderate when getting close
                # else: no sleep when quota is healthy
            # else: no default sleep — Zoho Bigin doesn't require it

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {api_module}: {str(e)}")
            raise


def fetch_single_record(module_name, record_id):
    url = urljoin(BIGIN_BASE, f"{module_name}/{record_id}")
    resp = requests.get(url, headers=_headers(), timeout=20)
    resp.raise_for_status()
    return resp.json()

# Helper to normalize Modified_Time and Created_Time fields to python datetime strings or None
def _extract_times(record):
    created = record.get("Created_Time") or record.get("created_time") or record.get("createdAt")
    modified = record.get("Modified_Time") or record.get("modified_time") or record.get("updatedAt")
    return created, modified


def fetch_module_list_with_fields(module_name, fields=None, per_page=DEFAULT_PER_PAGE):
    """
    Fetch module records with specific fields.
    Some modules (like Deals) might need explicit fields parameter.
    """
    page = 1
    while True:
        url = urljoin(BIGIN_BASE, f"{module_name}")
        params = {"page": page, "per_page": per_page}
        
        # Add fields if provided
        if fields:
            params["fields"] = ",".join(fields) if isinstance(fields, list) else fields
        
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        
        if resp.status_code != 200:
            logger.error("Bigin API list error %s for %s: %s", resp.status_code, module_name, resp.text)
            resp.raise_for_status()
        
        data = resp.json()
        records = data.get("data") or []
        
        if not records:
            break
        
        for r in records:
            yield r
        
        # Check for more pages
        info = data.get("info", {})
        if not info.get("more_records"):
            break
        
        page += 1
        time.sleep(0.2)


# =============================================================================
# CREATE, UPDATE, DELETE OPERATIONS
# =============================================================================

def create_bigin_record(module_name, record_data):
    """
    Create a new record in Bigin.

    Args:
        module_name: Module to create record in (Contacts, Accounts, Deals, Products)
        record_data: Dictionary containing record fields

    Returns:
        dict: Created record data including ID

    Raises:
        requests.HTTPError: If API request fails

    Example:
        record = create_bigin_record('Contacts', {
            'First_Name': 'John',
            'Last_Name': 'Doe',
            'Email': 'john@example.com',
            'Mobile': '+919876543210'
        })
    """
    url = urljoin(BIGIN_BASE, module_name)
    payload = {"data": [record_data]}

    session = _get_session()
    resp = session.post(url, headers=_headers(), json=payload, timeout=30)

    if resp.status_code not in [200, 201]:
        logger.error(f"Bigin API create error {resp.status_code} for {module_name}: {resp.text}")
        resp.raise_for_status()

    data = resp.json()

    if data.get("data") and len(data["data"]) > 0:
        created_record = data["data"][0]
        if created_record.get("code") == "SUCCESS":
            logger.info(f"Successfully created {module_name} record with ID: {created_record.get('details', {}).get('id')}")
            return created_record.get("details", {})
        else:
            error_msg = created_record.get("message", "Unknown error")
            logger.error(f"Failed to create {module_name} record: {error_msg}")
            raise ValueError(f"Record creation failed: {error_msg}")

    raise ValueError("Unexpected API response format")


def update_bigin_record(module_name, record_id, update_data):
    """
    Update an existing record in Bigin.

    Args:
        module_name: Module containing the record
        record_id: Bigin ID of the record to update
        update_data: Dictionary containing fields to update

    Returns:
        dict: Updated record details

    Raises:
        requests.HTTPError: If API request fails

    Example:
        update_bigin_record('Contacts', '4876876000000123456', {
            'Mobile': '+919876543211',
            'Status': ['Hot']
        })
    """
    url = urljoin(BIGIN_BASE, f"{module_name}/{record_id}")
    payload = {"data": [update_data]}

    session = _get_session()
    resp = session.put(url, headers=_headers(), json=payload, timeout=30)

    if resp.status_code != 200:
        logger.error(f"Bigin API update error {resp.status_code} for {module_name}/{record_id}: {resp.text}")
        resp.raise_for_status()

    data = resp.json()

    if data.get("data") and len(data["data"]) > 0:
        updated_record = data["data"][0]
        if updated_record.get("code") == "SUCCESS":
            logger.info(f"Successfully updated {module_name} record ID: {record_id}")
            return updated_record.get("details", {})
        else:
            error_msg = updated_record.get("message", "Unknown error")
            logger.error(f"Failed to update {module_name} record: {error_msg}")
            raise ValueError(f"Record update failed: {error_msg}")

    raise ValueError("Unexpected API response format")


def delete_bigin_record(module_name, record_id):
    """
    Delete a record from Bigin.

    Args:
        module_name: Module containing the record
        record_id: Bigin ID of the record to delete

    Returns:
        bool: True if deletion was successful

    Raises:
        requests.HTTPError: If API request fails

    Example:
        delete_bigin_record('Contacts', '4876876000000123456')
    """
    url = urljoin(BIGIN_BASE, f"{module_name}/{record_id}")

    session = _get_session()
    resp = session.delete(url, headers=_headers(), timeout=30)

    if resp.status_code != 200:
        logger.error(f"Bigin API delete error {resp.status_code} for {module_name}/{record_id}: {resp.text}")
        resp.raise_for_status()

    data = resp.json()

    if data.get("data") and len(data["data"]) > 0:
        deleted_record = data["data"][0]
        if deleted_record.get("code") == "SUCCESS":
            logger.info(f"Successfully deleted {module_name} record ID: {record_id}")
            return True
        else:
            error_msg = deleted_record.get("message", "Unknown error")
            logger.error(f"Failed to delete {module_name} record: {error_msg}")
            raise ValueError(f"Record deletion failed: {error_msg}")

    raise ValueError("Unexpected API response format")


def bulk_create_bigin_records(module_name, records_list):
    """
    Create multiple records in Bigin (up to 100 per request).

    Args:
        module_name: Module to create records in
        records_list: List of record dictionaries

    Returns:
        list: List of created record details

    Example:
        records = bulk_create_bigin_records('Contacts', [
            {'First_Name': 'John', 'Last_Name': 'Doe', 'Email': 'john@example.com'},
            {'First_Name': 'Jane', 'Last_Name': 'Smith', 'Email': 'jane@example.com'}
        ])
    """
    if len(records_list) > 100:
        raise ValueError("Cannot create more than 100 records in a single request")

    url = urljoin(BIGIN_BASE, module_name)
    payload = {"data": records_list}

    session = _get_session()
    resp = session.post(url, headers=_headers(), json=payload, timeout=30)

    if resp.status_code not in [200, 201]:
        logger.error(f"Bigin API bulk create error {resp.status_code} for {module_name}: {resp.text}")
        resp.raise_for_status()

    data = resp.json()
    results = []

    if data.get("data"):
        for record in data["data"]:
            if record.get("code") == "SUCCESS":
                results.append(record.get("details", {}))
            else:
                logger.warning(f"Failed to create record: {record.get('message')}")

    logger.info(f"Bulk created {len(results)}/{len(records_list)} records in {module_name}")
    return results


def bulk_update_bigin_records(module_name, records_list):
    """
    Update multiple records in Bigin (up to 100 per request).
    Each record dict must include 'id' field.

    Args:
        module_name: Module containing the records
        records_list: List of record dictionaries with 'id' and fields to update

    Returns:
        list: List of updated record details

    Example:
        records = bulk_update_bigin_records('Contacts', [
            {'id': '123456', 'Status': ['Hot']},
            {'id': '789012', 'Status': ['Warm']}
        ])
    """
    if len(records_list) > 100:
        raise ValueError("Cannot update more than 100 records in a single request")

    # Validate all records have ID
    for record in records_list:
        if 'id' not in record:
            raise ValueError("All records must have 'id' field for bulk update")

    url = urljoin(BIGIN_BASE, module_name)
    payload = {"data": records_list}

    session = _get_session()
    resp = session.put(url, headers=_headers(), json=payload, timeout=30)

    if resp.status_code != 200:
        logger.error(f"Bigin API bulk update error {resp.status_code} for {module_name}: {resp.text}")
        resp.raise_for_status()

    data = resp.json()
    results = []

    if data.get("data"):
        for record in data["data"]:
            if record.get("code") == "SUCCESS":
                results.append(record.get("details", {}))
            else:
                logger.warning(f"Failed to update record: {record.get('message')}")

    logger.info(f"Bulk updated {len(results)}/{len(records_list)} records in {module_name}")
    return results


# =============================================================================
# COQL-BASED INCREMENTAL SYNC (saves ~98% of API calls vs full REST pagination)
# =============================================================================

# Fields to fetch per module for batch REST fetch
_INCREMENTAL_FIELDS = {
    'Contacts': (
        'id,Owner,Account_Name,Title,Full_Name,First_Name,Last_Name,Email,Mobile,'
        'Description,Type,Lead_Source,Status_of_Action,Locations,Bussiness_Type,'
        'Industry_Type,Status,Area_Requirement,Business_Model,Reason,'
        'Created_Time,Modified_Time,Last_Activity_Time'
    ),
    'Pipelines': 'id,Deal_Name,Stage,Owner,Account_Name,Contact_Name,Conversion_Date,Converted_Area,Created_Time,Modified_Time',
    'Accounts':  'id,Account_Name,Email,Phone,Owner,Industry,Website,Created_Time,Modified_Time',
    'Products':  'id,Product_Name,Product_Code,Unit_Price,Owner,Created_Time,Modified_Time',
}


def fetch_changed_ids_via_coql(module_name, since_datetime):
    """
    COQL step 1: get IDs of records changed since since_datetime.

    Uses Last_Activity_Time for Contacts (catches note additions, call logs, etc.
    that don't bump Modified_Time). Uses Modified_Time for all other modules.

    Returns list of bigin_id strings. Max 2000 (COQL offset limit).
    """
    api_module = module_name.capitalize()
    time_field = 'Last_Activity_Time' if api_module == 'Contacts' else 'Modified_Time'
    since_str = since_datetime.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    ids = []
    offset = 0
    limit = 200
    COQL_MAX_OFFSET = 2000  # Zoho hard limit

    while offset < COQL_MAX_OFFSET:
        coql_query = (
            f"select id from {api_module} "
            f"where ({time_field} >= '{since_str}') "
            f"order by {time_field} desc "
            f"limit {limit} offset {offset}"
        )

        try:
            session = _get_session()
            resp = session.post(
                BIGIN_COQL_URL,
                headers=_headers(),
                json={"select_query": coql_query},
                timeout=30
            )

            if resp.status_code == 204 or not resp.text:
                break

            if resp.status_code != 200:
                logger.error(f"[COQL] Error {resp.status_code} for {api_module}: {resp.text[:200]}")
                break

            data = resp.json()
            records = data.get("data", [])

            if not records:
                break

            for r in records:
                ids.append(str(r["id"]))

            logger.debug(f"[COQL] {api_module}: got {len(records)} IDs at offset {offset} (total: {len(ids)})")

            if len(records) < limit:
                break  # Last page

            offset += limit
            time.sleep(0.3)

        except requests.exceptions.RequestException as e:
            logger.error(f"[COQL] Request failed for {api_module}: {e}")
            break

    logger.info(f"[COQL] {api_module}: found {len(ids)} changed records since {since_str}")
    return ids


def fetch_records_by_ids(module_name, ids_list):
    """
    REST step 2: batch-fetch full records for the given IDs (up to 100 per request).

    This is the complement to fetch_changed_ids_via_coql — COQL gives you IDs
    cheaply, then this gives you complete nested objects (Owner.name etc.) that
    COQL cannot return properly.

    Returns generator of raw record dicts.
    """
    if not ids_list:
        return

    api_module = module_name.capitalize()
    fields_param = _INCREMENTAL_FIELDS.get(api_module, 'all')
    url = urljoin(BIGIN_BASE, api_module)
    BATCH_SIZE = 100

    for i in range(0, len(ids_list), BATCH_SIZE):
        batch = ids_list[i:i + BATCH_SIZE]

        try:
            session = _get_session()
            resp = session.get(
                url,
                headers=_headers(),
                params={'ids': ','.join(batch), 'fields': fields_param},
                timeout=30
            )

            if resp.status_code == 204:
                logger.debug(f"[Batch] {api_module}: no data for batch at index {i}")
                continue

            if resp.status_code != 200:
                logger.error(f"[Batch] {api_module} error {resp.status_code}: {resp.text[:200]}")
                continue

            data = resp.json()
            records = data.get("data", [])
            logger.debug(f"[Batch] {api_module}: fetched {len(records)} records (batch {i // BATCH_SIZE + 1})")

            for r in records:
                yield r

            if i + BATCH_SIZE < len(ids_list):
                time.sleep(0.3)

        except requests.exceptions.RequestException as e:
            logger.error(f"[Batch] Request failed for {api_module} batch at index {i}: {e}")
            continue