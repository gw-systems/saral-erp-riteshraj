"""
Courier package mounted under ``operations.courier``.

The original app used ``courier.*`` imports throughout the codebase and in
management commands. We keep a package alias here so the moved app behaves like
one native ERP app without requiring a duplicate top-level package on disk.
"""

import sys


sys.modules.setdefault("courier", sys.modules[__name__])
