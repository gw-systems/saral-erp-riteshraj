class CourierError(Exception):
    """Base exception for all courier module errors."""
    def __init__(self, message, code="COURIER_ERROR", details=None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

class PincodeNotFoundError(CourierError):
    """Raised when a pincode is not found in the master database."""
    def __init__(self, pincode):
        super().__init__(
            f"Pincode {pincode} not found in database.",
            code="PINCODE_NOT_FOUND",
            details={"pincode": pincode}
        )

class InvalidWeightError(CourierError):
    """Raised when weight is invalid (negative or zero)."""
    def __init__(self, weight):
        super().__init__(
            f"Invalid weight: {weight}. Weight must be greater than 0.",
            code="INVALID_WEIGHT",
            details={"weight": weight}
        )

class InvalidDimensionsError(CourierError):
    """Raised when dimensions are invalid."""
    def __init__(self, length, width, height):
        super().__init__(
            f"Invalid dimensions: {length}x{width}x{height}. All dimensions must be greater than 0.",
            code="INVALID_DIMENSIONS",
            details={"length": length, "width": width, "height": height}
        )

class NoRatesAvailableError(CourierError):
    """Raised when no carriers are found for a route."""
    def __init__(self, source, dest, mode):
        super().__init__(
            f"No carriers available for route {source} -> {dest} ({mode}).",
            code="NO_RATES_AVAILABLE",
            details={"source": source, "destination": dest, "mode": mode}
        )

class UnsupportedRouteError(CourierError):
    """Raised when a specific route is known to be serviceable but not by specific carriers."""
    pass
