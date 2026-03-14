"""
SyncLogHandler — Python logging handler that writes log records to SyncLog.

Usage in any sync function:

    from integrations.sync_logger import SyncLogHandler

    with SyncLogHandler(batch_log, integration='callyzer', sync_type='callyzer') as handler:
        # All logger.debug / logger.info / logger.warning / logger.error calls
        # from any logger in this thread are now captured in SyncLog.
        do_sync()

This requires NO changes to existing logger calls. Every logger.debug(),
logger.info(), etc. in the sync code will automatically appear in the
frontend log panel.

Level mapping:
  logging.DEBUG    → SyncLog level 'DEBUG'
  logging.INFO     → SyncLog level 'INFO'
  logging.WARNING  → SyncLog level 'WARNING'
  logging.ERROR    → SyncLog level 'ERROR'
  logging.CRITICAL → SyncLog level 'CRITICAL'
"""

import logging
import threading

logger = logging.getLogger(__name__)

# Map Python log levels → SyncLog level strings
_LEVEL_MAP = {
    logging.DEBUG: 'DEBUG',
    logging.INFO: 'INFO',
    logging.WARNING: 'WARNING',
    logging.ERROR: 'ERROR',
    logging.CRITICAL: 'CRITICAL',
}

# Thread-local storage so nested syncs in different threads don't interfere
_thread_local = threading.local()


class SyncLogHandler(logging.Handler):
    """
    A logging.Handler that writes log records to the SyncLog model.

    Only captures records from the thread that created the handler,
    so concurrent syncs in separate threads work correctly.

    Parameters
    ----------
    batch_log : SyncLog instance (log_kind='batch')
        The parent batch log entry to attach operation logs to.
    integration : str
        Integration name (e.g. 'callyzer', 'bigin', 'google_ads').
    sync_type : str
        Sync type string stored in operation log rows.
    min_level : int
        Minimum Python logging level to capture (default: logging.DEBUG).
    loggers : list[str] | None
        Specific logger names to attach to. If None, attaches to root logger.
        Example: ['integrations.callyzer', 'integrations.bigin']
    """

    def __init__(self, batch_log, integration, sync_type,
                 min_level=logging.DEBUG, loggers=None):
        super().__init__(level=min_level)
        self.batch_log = batch_log
        self.integration = integration
        self.sync_type = sync_type
        self.owner_thread = threading.current_thread().ident
        self._loggers = loggers  # list of logger names to attach to
        self._attached = []      # actual logger objects we attached to

    # ── Context manager support ──────────────────────────────────────────────

    def __enter__(self):
        self._attach()
        return self

    def __exit__(self, *args):
        self._detach()

    # ── Attach / detach ──────────────────────────────────────────────────────

    def _attach(self):
        if self._loggers:
            targets = [logging.getLogger(name) for name in self._loggers]
        else:
            targets = [logging.getLogger()]  # root logger

        for log in targets:
            log.addHandler(self)
            self._attached.append(log)

    def _detach(self):
        for log in self._attached:
            log.removeHandler(self)
        self._attached.clear()

    # ── Core emit ────────────────────────────────────────────────────────────

    def emit(self, record: logging.LogRecord):
        # Only process records from the owning thread
        if threading.current_thread().ident != self.owner_thread:
            return

        try:
            from integrations.models import SyncLog

            level = _LEVEL_MAP.get(record.levelno, 'INFO')
            operation = record.name.split('.')[-1]  # last part of logger name

            if record.exc_info:
                # Include traceback in message
                import traceback
                tb = ''.join(traceback.format_exception(*record.exc_info))
                message = f"{record.getMessage()}\n{tb}"
            else:
                message = record.getMessage()

            SyncLog.objects.create(
                integration=self.integration,
                sync_type=self.sync_type,
                log_kind='operation',
                batch=self.batch_log,
                level=level,
                operation=operation,
                message=message,
            )
        except Exception:
            # Never let logging errors crash the sync
            pass
