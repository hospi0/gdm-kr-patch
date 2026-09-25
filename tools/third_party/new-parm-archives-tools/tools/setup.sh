#!/usr/bin/env bash
# Fetch + adapt + build the Java translation tools INSIDE this repo.
#
# Upstream tools target the original Grandia, not Digital Museum. We clone upstream into
# tools/vendor/ (gitignored), apply our Digital-Museum diffs from tools/patches/, then build.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$ROOT/tools/vendor"
PATCHES="$ROOT/tools/patches"
REPO_URL="https://github.com/TrekkiesUnite118/GrandiaTranslation.git"
CLONE_DIR="$VENDOR/GrandiaTranslation"

mkdir -p "$VENDOR"

if [ ! -d "$CLONE_DIR/.git" ]; then
  echo ">> Cloning upstream GrandiaTranslation tools..."
  git clone --depth 1 "$REPO_URL" "$CLONE_DIR"
else
  echo ">> Upstream already cloned; leaving as-is (delete tools/vendor to re-fetch)."
fi

# Apply our Digital Museum adaptation diffs, if any.
if compgen -G "$PATCHES/*.patch" > /dev/null; then
  echo ">> Applying Digital Museum patches from tools/patches/ ..."
  for p in "$PATCHES"/*.patch; do
    echo "   - $(basename "$p")"
    git -C "$CLONE_DIR" apply --check "$p" 2>/dev/null \
      && git -C "$CLONE_DIR" apply "$p" \
      || echo "     (already applied or needs rework: $(basename "$p"))"
  done
else
  echo ">> No patches in tools/patches/ yet (expected until DM adaptations are written)."
fi

echo ">> Building with Maven..."
# The Maven project lives in a subdirectory (GrandiaTranslationTools/), not the repo root.
POM_DIR="$(dirname "$(find "$CLONE_DIR" -maxdepth 2 -name pom.xml | head -1)")"
if [ -n "$POM_DIR" ] && [ -f "$POM_DIR/pom.xml" ]; then
  echo "   pom.xml: $POM_DIR/pom.xml"
  ( cd "$POM_DIR" && mvn -q -DskipTests package )
  echo ">> Build complete. Java classes under $POM_DIR/target/"
else
  echo "!! No pom.xml found under $CLONE_DIR; inspect layout before building." >&2
  exit 1
fi
