from django.db.models import Max
from .models import ProjectCode, GstState
from supply.models import CityCode
import re

def get_next_sequence_number(series_type, year):
    """
    Get the next sequence number for a given series and year.
    Example: If last was WAAS-25-441, return 442

    Fixed: Now uses numeric comparison instead of string sorting to find
    the actual highest sequence number. This prevents gaps when project_id
    values are manually changed.
    """
    year_suffix = str(year)[-2:]  # Get last 2 digits of year

    # Find the highest sequence number for this series and year
    prefix = f"{series_type}-{year_suffix}-"

    # Get all project_ids with this prefix
    project_ids = ProjectCode.objects.filter(
        project_id__startswith=prefix
    ).values_list('project_id', flat=True)

    if not project_ids:
        return 1  # First project for this series/year

    # Extract numeric suffixes and find the true maximum
    max_num = 0
    for project_id in project_ids:
        # Extract sequence number from project_id like "WAAS-25-441"
        match = re.search(r'-(\d+)$', project_id)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num

    return max_num + 1


def get_next_state_code(state_code, series_type):
    """
    Get the next code for a state (e.g., MH001, MH002, etc.)
    For SAAS, use SA001, SA002, etc.
    For GW, use GW001, GW002, etc.

    Fixed: Now uses numeric comparison instead of string sorting to find
    the actual highest sequence number. This prevents gaps when codes are
    manually changed (e.g., MH005 -> MH010).
    """

    if series_type == 'SAAS':
        prefix = 'SA'
    elif series_type == 'GW':
        prefix = 'GW'
    else:
        prefix = state_code  # For WAAS, use state code

    # Get all codes with this prefix and series type
    projects = ProjectCode.objects.filter(
        code__startswith=prefix,
        series_type=series_type
    ).values_list('code', flat=True)

    if not projects:
        # No existing projects with this prefix
        return f"{prefix}001"

    # Extract numeric suffixes and find the true maximum
    max_num = 0
    for code in projects:
        # Extract number from code like "MH166" or "KA025"
        match = re.search(r'(\d+)$', code)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num

    # Generate next sequential number
    next_num = max_num + 1
    return f"{prefix}{next_num:03d}"


def generate_project_code_string(code, client_name, vendor_name, city):
    """
    Generate the full project code string.
    Example: "MH166 - (ABC Corp - XYZ Logistics (Mumbai))"
    """
    return f"{code} - ({client_name} - {vendor_name} ({city}))"


def get_next_temp_sequence():
    """
    Get next TEMP sequence number.
    Returns: Integer for TEMP-001, TEMP-002, etc.

    Fixed: Now uses numeric comparison instead of string sorting to find
    the actual highest sequence number. This prevents gaps when TEMP IDs
    are manually changed.
    """
    # Get all TEMP project IDs
    temp_ids = ProjectCode.objects.filter(
        project_id__startswith='TEMP-'
    ).values_list('project_id', flat=True)

    if not temp_ids:
        return 1  # First TEMP project

    # Extract numeric suffixes and find the true maximum
    max_num = 0
    for temp_id in temp_ids:
        # Extract number from TEMP-001, TEMP-002, etc.
        match = re.search(r'-(\d+)$', temp_id)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num

    return max_num + 1


def is_temp_project(project):
    """Check if project has temporary ID"""
    return project.project_id.startswith('TEMP-')


def validate_gst_state(state_code, series_type):
    """
    For WAAS series, ensure the state has GST registration.
    If state not found, defaults to MH (Maharashtra).
    Returns (is_valid, error_message, fallback_state_code)
    """
    if series_type != 'WAAS':
        return True, None, state_code
    
    try:
        gst_state = GstState.objects.get(state_code=state_code, is_active=True)
        if not gst_state.gst_number:
            # Default to MH if no GST number
            return True, f"⚠️ State {state_code} has no GST. Defaulting to MH series.", 'MH'
        return True, None, state_code
    except GstState.DoesNotExist:
        # Default to MH if state not found
        return True, f"⚠️ State {state_code} not in GST registry. Defaulting to MH series.", 'MH'


def get_city_code(city_name, state_code):
    """
    Get the 3-letter city code for a city.
    Returns city code or None if not found.
    """
    try:
        city = CityCode.objects.get(
            city_name__iexact=city_name,
            state_code=state_code,
            is_active=True
        )
        return city.city_code
    except CityCode.DoesNotExist:
        return None