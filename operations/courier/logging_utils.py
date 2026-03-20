"""
Logging utilities for structured logging throughout the courier application.

Provides consistent logging patterns for migrations, operations, and general use.
Integrates with Django's logging system for production-ready monitoring.
"""
import logging
from typing import Optional, Dict, Any


# Module-level loggers
migration_logger = logging.getLogger('courier.migrations')
operation_logger = logging.getLogger('courier.operations')
cache_logger = logging.getLogger('courier.cache')


class MigrationLogger:
    """
    Structured logging for Django migrations.
    
    Provides consistent format for success, warning, and error messages
    during migration execution. Logs include structured metadata for monitoring.
    """
    
    def __init__(self, logger=None):
        self.logger = logger or migration_logger
    
    def success(self, operation: str, details: Optional[Dict[str, Any]] = None):
        """
        Log a successful migration operation.
        
        Args:
            operation: Description of the operation
            details: Additional context dictionary
        """
        extra = {"status": "success", "operation": operation}
        if details:
            extra.update(details)
        self.logger.info(f"[SUCCESS] {operation}", extra=extra)
    
    def warning(self, operation: str, reason: str, details: Optional[Dict[str, Any]] = None):
        """
        Log a warning during migration (non-fatal issue).
        
        Args:
            operation: Description of the operation
            reason: Why the warning occurred
            details: Additional context dictionary
        """
        extra = {"status": "warning", "operation": operation, "reason": reason}
        if details:
            extra.update(details)
        self.logger.warning(f"[WARNING] {operation}: {reason}", extra=extra)
    
    def error(self, operation: str, error: Exception, details: Optional[Dict[str, Any]] = None):
        """
        Log an error during migration.
        
        Args:
            operation: Description of the operation
            error: The exception that occurred
            details: Additional context dictionary
        """
        extra = {"status": "error", "operation": operation, "error_type": type(error).__name__}
        if details:
            extra.update(details)
        self.logger.error(f"[ERROR] {operation}: {str(error)}", exc_info=True, extra=extra)
    
    def info(self, message: str, details: Optional[Dict[str, Any]] = None):
        """
        Log an informational message.
        
        Args:
            message: The message to log
            details: Additional context dictionary
        """
        extra = details or {}
        self.logger.info(message, extra=extra)


class OperationLogger:
    """
    Structured logging for general operations (cache, API, etc.).
    
    Similar to MigrationLogger but for runtime operations.
    """
    
    def __init__(self, logger=None):
        self.logger = logger or operation_logger
    
    def success(self, operation: str, details: Optional[Dict[str, Any]] = None):
        """Log successful operation."""
        extra = {"status": "success", "operation": operation}
        if details:
            extra.update(details)
        self.logger.info(f"[SUCCESS] {operation}", extra=extra)
    
    def warning(self, operation: str, reason: str, details: Optional[Dict[str, Any]] = None):
        """Log operation warning."""
        extra = {"status": "warning", "operation": operation, "reason": reason}
        if details:
            extra.update(details)
        self.logger.warning(f"[WARNING] {operation}: {reason}", extra=extra)
    
    def error(self, operation: str, error: Exception, details: Optional[Dict[str, Any]] = None):
        """Log operation error."""
        extra = {"status": "error", "operation": operation, "error_type": type(error).__name__}
        if details:
            extra.update(details)
        self.logger.error(f"[ERROR] {operation}: {str(error)}", exc_info=True, extra=extra)
    
    def info(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Log informational message."""
        extra = details or {}
        self.logger.info(message, extra=extra)


# Convenience functions for quick logging
def log_migration_success(operation: str, **kwargs):
    """Quick success log for migrations."""
    MigrationLogger().success(operation, kwargs if kwargs else None)


def log_migration_warning(operation: str, reason: str, **kwargs):
    """Quick warning log for migrations."""
    MigrationLogger().warning(operation, reason, kwargs if kwargs else None)


def log_migration_error(operation: str, error: Exception, **kwargs):
    """Quick error log for migrations."""
    MigrationLogger().error(operation, error, kwargs if kwargs else None)


def log_cache_operation(operation: str, **kwargs):
    """Quick cache operation log."""
    cache_logger.info(operation, extra=kwargs if kwargs else {})
