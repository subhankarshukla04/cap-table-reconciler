"""Cap Table Reconciler — package init.

Importing `src` triggers registration of all built-in rule modules so the
rule-pack registry is populated for both baseline (v2026.1.0) and
expansion (v2026.2.0) packs.
"""

from . import checklist  # noqa: F401  registers baseline rules
from . import rules_v2026_2  # noqa: F401  registers v2026.2.0 expansion rules
from . import rules_v2026_3  # noqa: F401  registers v2026.3.0 expansion rules
from . import rules_v2026_4  # noqa: F401  registers v2026.4.0 expansion rules
from . import rules_v2026_5  # noqa: F401  registers v2026.5.0 expansion rules
from . import rules_v2026_6  # noqa: F401  registers v2026.6.0 expansion rules
