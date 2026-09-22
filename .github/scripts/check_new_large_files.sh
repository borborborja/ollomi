#!/usr/bin/env bash
set -euo pipefail

base_ref=${1:?"Usage: check_new_large_files.sh <base-ref> [max-bytes]"}
max_bytes=${2:-20971520}

if ! git cat-file -e "${base_ref}^{commit}" 2>/dev/null; then
  echo "Base ${base_ref} is unavailable locally; skipping the new-file size check."
  exit 0
fi

failed=0
while IFS= read -r -d '' path; do
  size=$(git cat-file -s "HEAD:${path}")
  if (( size > max_bytes )); then
    printf 'Refusing %s: %s bytes exceeds the %s-byte repository limit.\n' \
      "$path" "$size" "$max_bytes" >&2
    failed=1
  fi
done < <(git diff --name-only -z --diff-filter=ACMR "$base_ref" HEAD)

if (( failed )); then
  echo "Use a release asset or a model download instead of committing large binaries." >&2
  exit 1
fi

echo "No new repository file exceeds ${max_bytes} bytes."
