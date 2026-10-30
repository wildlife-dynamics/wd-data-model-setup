"""Patch the wt-compiler installed in the pixi `compile` environment.

`pixi install` / `pixi update` recreates the environment and reverts this, so it
runs before every compile. It is idempotent.

The patch: wt_compiler/spec.py declares `type PartialKwargs = ...` (PEP 695).
`ecoscope-platform` and `ecoscope-workflows-ext-ste` pin pydantic <2.9, which
cannot build a core schema for a PEP 695 alias, so importing `wt_compiler.spec`
raises:

    PydanticSchemaGenerationError: Unable to generate pydantic-core schema for
    PartialKwargs

Downgrading the alias to a plain assignment fixes it. A wt-compiler release that
drops the pydantic <2.9 pin makes this unnecessary.

Not patched here: save-the-elephants' `dev/recompile.sh` also relaxes the rattler
solve to `ChannelPriority.Disabled`, so pydeck 0.9.2 can resolve from conda-forge
against the prefix.dev channels. That patch does not apply to this wt-compiler
build — its solve call is `await solve(sources=..., ...)` (rattler 0.22+ renamed
`channels` to `sources`) and may not accept a `channel_priority` argument at all.
If a compile ever fails to resolve pydeck, that is the lever to reach for, but it
needs writing against the installed rattler rather than copied across.

Usage:
    python3 dev/patch-compile-env.py [site-packages-dir ...]

Exits non-zero if wt_compiler cannot be found, or if the patch did not take, so a
failure is visible rather than silently skipped.
"""

from __future__ import annotations

import pathlib
import sys

PEP695_ALIAS = "type PartialKwargs = "


def find_wt_compiler(hint: str | None) -> list[pathlib.Path]:
    """Locate every installed wt_compiler package.

    `.pixi/envs/compile/lib/` holds both `python3.1` (a symlink) and the real
    `python3.12`, so a `python3.*` glob is ambiguous. Collect every match and
    deduplicate by resolved path, rather than betting on the first one.
    """
    candidates: list[pathlib.Path] = []

    if hint:
        # The hint may arrive as several space-separated paths if a caller passed
        # an unquoted shell glob; take every one that exists.
        for part in hint.split():
            candidates.append(pathlib.Path(part) / "wt_compiler")

    candidates.extend(
        pathlib.Path(".pixi/envs").glob("*/lib/python3.*/site-packages/wt_compiler")
    )

    found: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()
    for candidate in candidates:
        if not (candidate / "spec.py").is_file():
            continue
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        found.append(candidate)

    if not found:
        searched = "\n  ".join(str(c) for c in candidates) or "(nothing)"
        sys.exit(
            "could not find an installed wt_compiler. Searched:\n  "
            + searched
            + "\nIs the pixi 'compile' environment installed?"
        )

    return found


def patch_spec(pkg: pathlib.Path) -> None:
    path = pkg / "spec.py"
    text = path.read_text()

    if PEP695_ALIAS in text:
        path.write_text(text.replace(PEP695_ALIAS, "PartialKwargs = "))
        print(f"patched {path}: PEP 695 alias -> plain assignment")
        text = path.read_text()
    else:
        print(f"ok {path}: no PEP 695 alias")

    if PEP695_ALIAS in text:
        sys.exit(f"patch did not take: {PEP695_ALIAS!r} still present in {path}")


def main() -> None:
    hint = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    for pkg in find_wt_compiler(hint):
        print(f"patching wt_compiler at {pkg}")
        patch_spec(pkg)


if __name__ == "__main__":
    main()
