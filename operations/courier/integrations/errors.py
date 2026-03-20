"""Domain-specific errors for Shipdaak integration."""


class ShipdaakIntegrationError(Exception):
    """Base class for Shipdaak integration failures."""


class AuthError(ShipdaakIntegrationError):
    """Authentication or authorization failure."""


class ValidationError(ShipdaakIntegrationError):
    """Invalid request data or upstream validation failure."""


class InsufficientBalance(ShipdaakIntegrationError):
    """Wallet balance/credit is insufficient for booking."""


class WarehouseNotSynced(ShipdaakIntegrationError):
    """Warehouse sync IDs are missing/unavailable."""


class UpstreamError(ShipdaakIntegrationError):
    """Unhandled upstream provider error."""
