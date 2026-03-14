# Projects utils package
# Re-export common utility functions for backward compatibility
from .common import (
    get_next_sequence_number,
    get_next_state_code,
    generate_project_code_string,
    get_next_temp_sequence,
    is_temp_project,
    validate_gst_state,
    get_city_code
)

__all__ = [
    'get_next_sequence_number',
    'get_next_state_code',
    'generate_project_code_string',
    'get_next_temp_sequence',
    'is_temp_project',
    'validate_gst_state',
    'get_city_code',
    'settings_helper',
    'google_auth'
]
