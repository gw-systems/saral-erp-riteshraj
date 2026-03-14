"""
Input validation schemas for Cloud Tasks worker payloads
Uses Pydantic for strict type checking and validation
"""
from typing import Optional, List, Annotated
from pydantic import BaseModel, Field, field_validator, ValidationError, conint, constr
from datetime import datetime


class BaseSyncPayload(BaseModel):
    """Base payload validation for sync operations"""

    class ConfigDict:
        # Don't allow extra fields not defined in the schema
        extra = 'forbid'
        # Use enum values instead of names
        use_enum_values = True


class BiginSyncPayload(BaseSyncPayload):
    """Payload validation for Bigin sync operations"""
    modules: Optional[List[str]] = Field(
        default=None,
        description="List of Bigin modules to sync (e.g., ['Contacts', 'Pipelines'])"
    )
    run_full: bool = Field(
        default=False,
        description="If True, run full sync. If False, incremental."
    )
    triggered_by_user: Optional[str] = Field(
        default=None,
        description="Username of the user who triggered the sync"
    )

    @field_validator('modules')
    @classmethod
    def validate_modules(cls, v):
        if v is not None:
            valid_modules = {'Contacts', 'Pipelines', 'Accounts', 'Products', 'Notes'}
            invalid = set(v) - valid_modules
            if invalid:
                raise ValueError(f"Invalid modules: {invalid}. Valid: {valid_modules}")
        return v


class GmailLeadsSyncPayload(BaseSyncPayload):
    """Payload validation for Gmail Leads sync"""
    token_id: Annotated[int, Field(gt=0, description="Gmail Leads token ID")]
    force_full: bool = Field(
        default=False,
        description="Force full sync instead of incremental"
    )
    triggered_by_user: Optional[str] = Field(
        default=None,
        description="Username of the user who triggered the sync"
    )

    @field_validator('token_id')
    @classmethod
    def validate_token_id(cls, v):
        if v <= 0:
            raise ValueError("token_id must be positive")
        return v


class GoogleAdsSyncPayload(BaseSyncPayload):
    """Payload validation for Google Ads sync"""
    token_id: Annotated[int, Field(gt=0, description="Google Ads token ID")]
    sync_yesterday: bool = Field(default=True, description="Sync yesterday's data")
    sync_current_month_search_terms: bool = Field(
        default=True,
        description="Sync current month search terms"
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Start date for historical sync in YYYY-MM-DD format"
    )
    triggered_by_user: Optional[str] = Field(
        default=None,
        description="Username of the user who triggered the sync"
    )

    @field_validator('start_date')
    @classmethod
    def validate_start_date(cls, v):
        if v is not None:
            try:
                datetime.strptime(v, '%Y-%m-%d')
            except ValueError:
                raise ValueError("start_date must be in YYYY-MM-DD format")
        return v


class TallySyncPayload(BaseSyncPayload):
    """Payload validation for Tally sync"""

    class ConfigDict:
        extra = 'ignore'  # Allow extra fields (full_sync, scheduled_job_id, etc.)
        use_enum_values = True

    company_id: Optional[Annotated[int, Field(gt=0)]] = Field(
        default=None,
        description="Specific company ID to sync, or None for all"
    )
    sync_type: Annotated[str, Field(pattern=r'^(companies|ledgers|vouchers|all)$')] = Field(
        default='all',
        description="Type of data to sync"
    )
    from_date: Optional[str] = Field(
        default=None,
        description="Start date in YYYYMMDD format"
    )
    to_date: Optional[str] = Field(
        default=None,
        description="End date in YYYYMMDD format"
    )
    full_sync: bool = Field(
        default=False,
        description="If True, fetch full history instead of incremental"
    )
    triggered_by_user: Optional[str] = Field(
        default=None,
        description="Username of the user who triggered the sync"
    )

    @field_validator('from_date', 'to_date')
    @classmethod
    def validate_date_format(cls, v):
        if v is not None:
            try:
                datetime.strptime(v, '%Y%m%d')
            except ValueError:
                raise ValueError("Date must be in YYYYMMDD format")
        return v

    @field_validator('to_date')
    @classmethod
    def validate_date_range(cls, v, info):
        if v and info.data.get('from_date'):
            from_date = datetime.strptime(info.data['from_date'], '%Y%m%d')
            to_date = datetime.strptime(v, '%Y%m%d')
            if to_date < from_date:
                raise ValueError("to_date must be >= from_date")
        return v


class CallyzerSyncPayload(BaseSyncPayload):
    """Payload validation for Callyzer sync"""
    token_id: Annotated[int, Field(gt=0, description="Callyzer token ID")]
    days_back: Annotated[int, Field(ge=1, le=365)] = Field(
        default=150,
        description="Number of days to sync (1-365)"
    )
    triggered_by_user: Optional[str] = Field(
        default=None,
        description="Username of the user who triggered the sync"
    )


class GmailSyncPayload(BaseSyncPayload):
    """Payload validation for Gmail app sync"""
    token_id: Annotated[int, Field(gt=0, description="Gmail token ID")]
    label: Annotated[str, Field(min_length=1, max_length=100)] = Field(
        default='INBOX',
        description="Gmail label to sync"
    )
    max_results: Annotated[int, Field(ge=1, le=500)] = Field(
        default=100,
        description="Maximum emails to sync (1-500)"
    )


def validate_payload(payload_class: type[BaseModel], data: dict) -> BaseModel:
    """
    Validate payload data using Pydantic model

    Args:
        payload_class: Pydantic model class to use for validation
        data: Dictionary with payload data

    Returns:
        Validated Pydantic model instance

    Raises:
        ValidationError: If data doesn't match schema
    """
    # Let ValidationError propagate directly — workers catch it as 400
    return payload_class(**data)


# Mapping of integration to payload validator
PAYLOAD_VALIDATORS = {
    'bigin': BiginSyncPayload,
    'gmail_leads': GmailLeadsSyncPayload,
    'google_ads': GoogleAdsSyncPayload,
    'tallysync': TallySyncPayload,
    'callyzer': CallyzerSyncPayload,
    'gmail': GmailSyncPayload,
}
