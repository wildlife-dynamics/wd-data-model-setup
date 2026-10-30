"""Make the package importable when the suite is run from the repository root.

`pixi run pytest` invokes pytest from the root, where the package lives two
directories down and is not installed into the default environment. pytest adds
the *test* directory to sys.path, not the package root above it, so the import
fails with ModuleNotFoundError before a single test runs.

Installing the package into the default env would also work, but it would mean
rebuilding it to test a one-line change. The tests are pure and offline; they
should run against the working tree.
"""

import pathlib
import sys

PKG_ROOT = pathlib.Path(__file__).resolve().parents[1]

if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))
