#!/bin/bash
#
# Upload what publish/build.sh produced to the shared conda channel.
#
# Run by .github/workflows/publish.yml on a vMAJ.MIN.PATCH tag, which holds
# the OIDC token the channel authenticates against -- there is no API key
# here, and running this locally will fail for that reason. Tag a release
# instead; tag.yml does the tagging from VERSION.yaml when a PR to main
# merges.
set -euo pipefail

for file in /tmp/ecoscope-workflows-custom/release/artifacts/**/*.conda; do
    rattler-build upload prefix -c ecoscope-workflows-custom "$file"
done
