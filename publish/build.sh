#!/bin/bash
#
# Build the task package into a local channel that spec.yaml resolves from.
#   pixi run build-release
set -euo pipefail

RECIPES=("release/ecoscope-workflows-ext-wdmodel")

project_root=$(pwd)/src/ecoscope-workflows-ext-wdmodel
HATCH_VCS_VERSION=$(cd "$project_root" && hatch version)
export HATCH_VCS_VERSION

# An empty version reaches rattler-build as version: '' and fails deep inside
# recipe rendering with "malformed version string". Catch it here, where the
# cause is legible.
if [ -z "${HATCH_VCS_VERSION}" ]; then
  cat >&2 <<EOF

hatch could not determine a version for the task package.

  Check [project] version in src/ecoscope-workflows-ext-wdmodel/pyproject.toml.
  If it declares dynamic = ["version"], it also needs a [tool.hatch.version]
  block -- and hatch-vcs needs a git repository with at least one tag.

EOF
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
