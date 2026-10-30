#!/bin/bash
#
# Build the task package into a local channel that spec.yaml resolves from.
#   pixi run build-release
set -euo pipefail

RECIPES=("release/ecoscope-workflows-ext-wdmodel")

project_root=$(pwd)/src/ecoscope-workflows-ext-wdmodel

# The version is the git tag, read from git rather than from `hatch version`.
#
# The other workflow repos call `hatch version`, and can, because their
# pyproject.toml sits at the repository root next to .git. Ours is two levels
# down in src/, and setuptools-scm -- which hatch-vcs wraps -- looks for .git
# in the project root only. It does not walk up, so it finds nothing, returns
# the fallback, and the build quietly becomes 0.0.0 even on a tagged checkout.
#
# Asking git directly has no such subtlety, and says plainly where the version
# comes from. The recipe passes it to the wheel build as
# SETUPTOOLS_SCM_PRETEND_VERSION, so both halves agree.
tag=$(git describe --tags --exact-match 2>/dev/null || true)   # on a release tag
if [ -z "${tag}" ]; then
  tag=$(git describe --tags --abbrev=0 2>/dev/null || true)    # local iteration
fi
if [ -n "${tag}" ]; then
  HATCH_VCS_VERSION="${tag#v}"
else
  # No tags at all: a fresh clone before the first release. Fall back to
  # hatch so a local build still produces something installable.
  HATCH_VCS_VERSION=$(cd "$project_root" && hatch version)
fi
export HATCH_VCS_VERSION

# An empty version reaches rattler-build as version: '' and fails deep inside
# recipe rendering with "malformed version string". Catch it here, where the
# cause is legible.
if [ -z "${HATCH_VCS_VERSION}" ]; then
  cat >&2 <<EOF

could not determine a version for the task package.

  The version is the git tag with its leading 'v' removed. A shallow clone
  has no tags -- CI checks out with fetch-depth: 0 for exactly this reason.

EOF
  exit 1
fi

# 0.0.0 is the fallback hatch-vcs uses when there is no tag at all. Fine
# locally; fatal in CI, because the channel already holds a 0.0.0 from the
# first publish and rejects the re-upload with an error that says nothing
# about tags.
if [ "${HATCH_VCS_VERSION}" = "0.0.0" ] && [ -n "${CI:-}" ]; then
  echo "refusing to build 0.0.0 in CI -- no tag was found on this checkout" >&2
  exit 1
fi
echo "HATCH_VCS_VERSION=${HATCH_VCS_VERSION}"

echo "Building recipes: ${RECIPES[*]}"

# NOT clearing the cache here. `pixi clean cache --yes` deletes the whole rattler
# package cache -- python, icu, tk, openssl, the lot -- so every build re-downloads
# ~90 MiB before it can even start. On a slow or unreliable connection that turns a
# retryable hiccup into a build that can never finish, because the next attempt
# starts from nothing again.
#
# The reason the line existed is that channel repodata is cached, so a package
# published minutes ago stays invisible. That does not apply here: the task package
# is resolved from a local file:// channel. dev/recompile.sh still clears the cache
# when it matters, and that is opt-in -- see CLEAN_CACHE there.

rm -rf /tmp/ecoscope-workflows-custom/release/artifacts
mkdir -p /tmp/ecoscope-workflows-custom/release/artifacts

for rec in "${RECIPES[@]}"; do
  recipe="$(pwd)/publish/recipes/${rec}.yaml"
  if [ ! -f "$recipe" ]; then
    echo "no recipe at $recipe" >&2
    echo "RECIPES entries are relative to publish/recipes/ and omit the .yaml" >&2
    exit 1
  fi
  echo "Building $rec"
  rattler-build build \
    --recipe "$(pwd)/publish/recipes/${rec}.yaml" \
    --output-dir /tmp/ecoscope-workflows-custom/release/artifacts \
    --channel https://prefix.dev/ecoscope-workflows \
    --channel conda-forge
done
