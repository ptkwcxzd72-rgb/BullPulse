#!/usr/bin/env bash
# Daily price files are kept in a GitHub Release (tag "price-store"), not in git: they are
# rewritten every night as dividends re-base total-return prices, and in git every rewrite stays
# in the history forever. Release files are free and replacing one doesn't grow the repository.
#
#   scripts/price_store.sh pull                 # data/prices and data/prices_archive from the release
#   scripts/price_store.sh push [prices|prices_archive ...]   # upload them (default: prices)
#
# Each push also keeps the version it replaces as <name>.prev.tar.gz, so one bad night can be
# undone. A push is refused when the folder has far fewer files than the universe (a failed
# download must never replace the store). Needs GH_TOKEN (the workflow's token).
set -euo pipefail
TAG=price-store
REPO="${GITHUB_REPOSITORY:-ptkwcxzd72-rgb/BullPulse}"
WORK="${RUNNER_TEMP:-/tmp}/price-store"
mkdir -p "$WORK"

universe_size() {
  # stocks with a provider ticker, plus the two benchmarks
  python3 - <<'E'
import csv, glob
print(sum(1 for f in glob.glob("universe/*.csv") for r in csv.DictReader(open(f)) if r.get("provider_ticker")) + 2)
E
}

case "${1:-}" in
  pull)
    for a in prices prices_archive; do
      if gh release download "$TAG" -R "$REPO" --pattern "$a.tar.gz" --dir "$WORK" --clobber 2>/dev/null; then
        rm -rf "data/$a"
        mkdir -p data
        tar -xzf "$WORK/$a.tar.gz" -C data
        echo "Price store: data/$a has $(ls "data/$a" | wc -l) files"
      elif [[ -d "data/$a" ]]; then
        echo "::warning::Price store: no $a.tar.gz in the release; using the files in the checkout"
      else
        echo "::error::Price store: no $a.tar.gz in the release and no data/$a"
        exit 1
      fi
    done
    ;;
  push)
    shift
    [[ $# -gt 0 ]] || set -- prices
    gh release view "$TAG" -R "$REPO" >/dev/null 2>&1 ||
      gh release create "$TAG" -R "$REPO" --title "Price store" --latest=false \
        --notes "Daily price files for the nightly jobs (scripts/price_store.sh). Not a software release."
    need=$(universe_size)
    for a in "$@"; do
      n=$(ls "data/$a" 2>/dev/null | wc -l)
      if (( n * 10 < need * 9 )); then
        echo "::error::Price store: data/$a has $n files for $need stocks; not uploaded"
        exit 1
      fi
      tar -czf "$WORK/$a.new.tar.gz" -C data "$a"
      if [[ -f "$WORK/$a.tar.gz" ]]; then
        cp "$WORK/$a.tar.gz" "$WORK/$a.prev.tar.gz"
        gh release upload "$TAG" -R "$REPO" "$WORK/$a.prev.tar.gz" --clobber
      fi
      mv "$WORK/$a.new.tar.gz" "$WORK/$a.tar.gz"
      gh release upload "$TAG" -R "$REPO" "$WORK/$a.tar.gz" --clobber
      echo "Price store: uploaded data/$a ($n files, $(du -h "$WORK/$a.tar.gz" | cut -f1))"
    done
    ;;
  *)
    echo "usage: $0 pull | push [prices|prices_archive ...]" >&2
    exit 2
    ;;
esac
