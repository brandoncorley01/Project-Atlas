# Shared dev server ports for Project Atlas
# Use 8012 — 8011 accumulates zombie listeners and stale connections on Windows.
$script:AtlasApiPort = 8012
$script:AtlasWebPort = 3000
$script:AtlasLegacyApiPorts = @(8011, 8010, 8000, 8002)
