#!/bin/bash
#
# Compile the workflow.
#
#   ./dev/recompile.sh --install
#   ./dev/recompile.sh --no-install
#
# Normally invoked through pixi, which already supplies the flag:
#
#   pixi run -e compile compile        # --install
#   pixi run -e compile recompile      # --no-install
#
# Run from the repository root. spec.yaml lives at the root and the compiled
# package lands beside it, which is what Ecoscope Desktop expects when a template
# is added from a GitHub URL -- it clones the repo and looks for spec.yaml at the
# top level.
set -euo pipefail

# Deduplicate flags, so an extra --install passed on the pixi command line on top
# of the one baked into the task does not reach wt-compiler twice.
flags=()
for flag in "$@"; do
  # This script used to take a workflow name, back when the spec lived in
  # workflows/<name>/. It does not any more, and a stray name would otherwise be
  # forwarded to wt-compiler, which rejects it with "unrecognized arguments".
  if [[ "$flag" != -* ]]; then
    cat >&2 <<EOF
unexpected argument '${flag}'.

  There is one workflow and spec.yaml is at the repository root, so no workflow
  name is needed:

    pixi run -e compile compile      # build and install
    pixi run -e compile recompile    # build only

EOF
    exit 2
  fi
  for seen in ${flags[@]+"${flags[@]}"}; do
    [ "$seen" = "$flag" ] && continue 2
  done
  flags+=("$flag")
done

if [ ! -f spec.yaml ]; then
  echo "no spec.yaml in $(pwd) -- run this from the repository root" >&2
  exit 1
fi

pixi_run="pixi run --manifest-path pixi.toml -e compile"

# Materialise the compile environment and (re)initialize the dot executable so
# wt-compiler can render graph.png. pixi skips post-link scripts by default, which
# is what would otherwise leave graphviz uninitialised.
$pixi_run dot -c

# Ask the environment's own interpreter where its site-packages is, rather than
# guessing the python version in the path. patch-compile-env.py falls back to
# searching .pixi/envs and exits non-zero if it finds nothing, so a missed patch
# fails the build instead of silently letting the compile blow up later.
site_packages=$($pixi_run python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])' | tail -1)
echo "compile env site-packages: ${site_packages}"
$pixi_run python dev/patch-compile-env.py "$site_packages"

# Channel repodata is cached, so a package published minutes ago can be invisible
# to the solver. Clearing the cache fixes that -- and also throws away every
# downloaded package, which costs ~90 MiB of re-downloads.
#
# So it is OPT-IN. The local file:// channel this repo resolves its task package
# from is not cached, so a normal iteration does not need it:
#
#     pixi run -e compile compile                  # no clean, fast, works offline-ish
#     CLEAN_CACHE=1 pixi run -e compile compile    # after publishing to a remote channel
#
if [ "${CLEAN_CACHE:-}" = "1" ]; then
  echo "clearing the pixi cache so newly published packages resolve"
  pixi clean cache --yes
else
  echo "keeping the pixi cache (CLEAN_CACHE=1 to clear it)"
fi

echo "compiling spec.yaml with flags '--clobber ${flags[*]-}'"

$pixi_run \
  wt-compiler compile \
    --spec spec.yaml \
    --pkg-name-prefix=ecoscope-workflows \
    --results-env-var=ECOSCOPE_WORKFLOWS_RESULTS \
    --clobber \
    ${flags[@]+"${flags[@]}"}

# The compiled workflow's pixi.lock is what Ecoscope Desktop installs from, using
# its own bundled pixi -- currently 0.64.0, which reads lock-file format v6 at
# most. pixi 0.68.0 started writing v7. A v7 lock is not an error there: it is
# silently discarded and the whole environment is re-solved from scratch, which
# needs the full repodata from repo.prefix.dev and conda-forge and falls over on
# any filtered or slow connection. Fail here, where it is cheap to see.
MAX_LOCKFILE_VERSION=${MAX_LOCKFILE_VERSION:-6}

for lock in ecoscope-workflows-*-workflow/pixi.lock; do
  [ -f "$lock" ] || continue
  version=$(awk -F': *' '/^version:/ {print $2; exit}' "$lock")
  if [ "${version:-0}" -gt "$MAX_LOCKFILE_VERSION" ]; then
    cat >&2 <<EOF

$lock is lock-file version ${version}; Ecoscope Desktop reads ${MAX_LOCKFILE_VERSION} at most.

  Written by $(pixi --version). Downgrade to a pixi that writes v${MAX_LOCKFILE_VERSION}
  and regenerate:

    pixi self-update --version 0.67.0
    rm $lock && (cd $(dirname "$lock") && pixi lock)

EOF
    exit 1
  fi
  echo "$lock: lock-file version ${version}"
done
