"""
Adobe Sign Custom Exceptions
"""


class AdobeSignException(Exception):
    """Base exception for Adobe Sign operations"""
    pass


class AdobeAuthError(AdobeSignException):
    """Exception raised for authentication errors"""
    pass


class AdobeDocumentError(AdobeSignException):
    """Exception raised for document upload/management errors"""
    pass


class AdobeAgreementError(AdobeSignException):
    """Exception raised for agreement creation/management errors"""
    pass


class AdobeConfigurationError(AdobeSignException):
    """Exception raised for configuration errors"""
    pass
