"""Define explicit versions for persisted contracts and validation rules.

The pipeline reads these constants when writing records and evaluating draft
quality so downstream systems can interpret outputs safely. Centralizing these
values makes migrations predictable and keeps version bumps deliberate.
"""

# Bump when persisted JSON shape or PipelineResult fields change.
PIPELINE_SCHEMA_VERSION = "1.0.0"

# Bump when rules in shared/validators.py change (banned phrases, word limits, etc.).
VALIDATION_RULE_VERSION = "1.0.0"
