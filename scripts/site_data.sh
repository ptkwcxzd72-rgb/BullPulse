#!/usr/bin/env bash
# The website's generated files (site/data, site/feeds, the per-stock pages in site/stock and
# site/sitemap.xml, about 35 MB rewritten every night) live
# on its own branch, site-data, as a single commit with no history. Keeping it off main stops the
# repository growing by megabytes a night; every publish replaces the previous one.
#
#   scripts/site_data.sh pull                      # unpack the published data into site/
#   scripts/site_data.sh push [--only PATH...]     # publish the generated files
#
# With --only, the published copy is kept and just the listed paths (relative to site/) are
# replaced: the monthly validation uses this to add panel.json and validation.json without
# touching the nightly files. Without it, everything comes from site/ except the validation
# files, which are kept from the published copy (they are only rebuilt monthly).
set -euo pipefail
BRANCH=site-data
KEEP=(data/panel.json data/validation.json data/valhist.json data/learning.json data/eventstudy.json data/live.json)

fetch() { git fetch -q --depth=1 origin "$BRANCH" 2>/dev/null; }

case "${1:-}" in
pull)
  mkdir -p site
  if fetch; then git archive FETCH_HEAD | tar -x -C site; echo "Unpacked $BRANCH into site/"; else echo "::warning::No $BRANCH branch yet"; fi
  ;;
push)
  shift
  tmp=$(mktemp -d)
  published=$(mktemp -d)
  if fetch; then git archive FETCH_HEAD | tar -x -C "$published"; fi
  if [[ "${1:-}" == "--only" ]]; then
    shift
    cp -a "$published/." "$tmp/"
    for p in "$@"; do mkdir -p "$tmp/$(dirname "$p")"; rm -rf "${tmp:?}/$p"; cp -a "site/$p" "$tmp/$p"; done
  else
    for d in data feeds stock; do
      [[ -d "site/$d" ]] && { mkdir -p "$tmp/$d"; cp -a "site/$d/." "$tmp/$d/"; }
    done
    [[ -f site/sitemap.xml ]] && cp -a site/sitemap.xml "$tmp/"
    for p in "${KEEP[@]}"; do [[ -e "$published/$p" ]] && cp -a "$published/$p" "$tmp/$p"; done
  fi
  export GIT_INDEX_FILE
  GIT_INDEX_FILE=$(mktemp -u)
  git --work-tree="$tmp" add -A -f .
  tree=$(git write-tree)
  commit=$(git commit-tree "$tree" -m "Website data $(date -u +%FT%TZ)")
  git push -q -f origin "$commit:refs/heads/$BRANCH"
  rm -rf "$tmp" "$published" "$GIT_INDEX_FILE"
  echo "Published $(git ls-tree -r --name-only "$commit" | wc -l) files to $BRANCH"
  ;;
*) echo "usage: $0 pull | push [--only PATH...]" >&2; exit 2 ;;
esac
