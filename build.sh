#!/usr/bin/env sh
# Render build step. There is no bundler — this just assembles the PUBLIC
# directory so that only the dashboard itself is served.
#
# Why not publish the repo root? The Render URL is public. The repo also holds
# the strategy brief, the internal how-to notes and the collection scripts,
# none of which should be downloadable by anyone with the link. Only the three
# things the page actually fetches get copied.
set -eu

rm -rf public
mkdir -p public

cp index.html public/
cp -r assets public/
cp -r data   public/

# GitHub Pages runs Jekyll over the output unless told not to, which silently
# drops files and folders beginning with "_" or ".". Nothing here should be
# transformed — it is already the finished site.
touch public/.nojekyll

# Keep the board out of search results. It is an internal board on a public
# URL, so obscurity is the only access control there is — do not make it
# searchable on top of that.
cat > public/robots.txt <<'ROBOTS'
User-agent: *
Disallow: /
ROBOTS

# Drop the working CSVs that the weekly browser-capture leaves in the snapshot
# folders; the JSON is what the board reads.
find public/data -name '*.csv' -delete 2>/dev/null || true

echo "built public/ →"
echo "  $(find public -type f | wc -l) files"
echo "  snapshots: $(ls public/data/snapshots | tr '\n' ' ')"
