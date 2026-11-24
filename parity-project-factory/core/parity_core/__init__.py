"""Parity core: reusable, domain-independent engine for parity projects.

Generated projects vendor this package. Project-specific behaviour lives in
config/ and rules/, never in this package.
"""

__version__ = "1.0.0"

RESULT_TYPES = (
    "MISMATCH",
    "MISSING_IN_TARGET",
    "MISSING_IN_SOURCE",
    "DUPLICATE_KEY_SOURCE",
    "DUPLICATE_KEY_TARGET",
)
