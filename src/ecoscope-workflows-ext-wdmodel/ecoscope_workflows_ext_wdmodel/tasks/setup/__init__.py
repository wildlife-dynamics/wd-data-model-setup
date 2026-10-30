# One registered task. `apply_data_model` with dry_run=True is the plan, so a
# separate plan task would only duplicate every field on the form.
#
# Both templates use it: the setup template binds the copy arguments off, the
# copy template binds the standard-model ones off. There was briefly a
# `set_optional_er_connection` here, to make the source connection optional on
# a single combined form; that approach is dead and the reasons are recorded
# in spec.yaml.
from ._apply import apply_data_model

__all__ = ["apply_data_model"]
