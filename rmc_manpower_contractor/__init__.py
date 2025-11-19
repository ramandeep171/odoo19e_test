# -*- coding: utf-8 -*-
"""Top-level module initialization."""

from importlib.util import find_spec
import warnings

_ODOO_AVAILABLE = find_spec("odoo") is not None

if _ODOO_AVAILABLE:  # pragma: no cover - exercised within Odoo runtime
    from . import models  # noqa: F401  (imported for side-effects)
    from . import wizards  # noqa: F401
    from . import controllers  # noqa: F401
    from . import reports  # noqa: F401
else:  # pragma: no cover - executed only in lightweight test envs
    warnings.warn(
        "Odoo framework not available; skipping rmc_manpower_contractor submodule imports.",
        RuntimeWarning,
        stacklevel=1,
    )
