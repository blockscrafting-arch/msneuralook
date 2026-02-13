#!/bin/sh
# Remove PDF files older than KEEP_PDF_DAYS. Run from project root (e.g. via cron).
# Env: PDF_STORAGE_PATH (default ./shared/pdf_storage), KEEP_PDF_DAYS (default 30).
# With Docker volume: run inside a container or mount volume and set PDF_STORAGE_PATH to the host path.

set -e
PDF_DIR="${PDF_STORAGE_PATH:-./shared/pdf_storage}"
KEEP_DAYS="${KEEP_PDF_DAYS:-30}"

if [ ! -d "$PDF_DIR" ]; then
  echo "PDF directory not found: $PDF_DIR" >&2
  exit 1
fi

COUNT=$(find "$PDF_DIR" -maxdepth 1 -type f \( -name "*.pdf" -o -name "*_*.pdf" \) -mtime +"$KEEP_DAYS" -print -delete | wc -l)
echo "Cleaned $COUNT PDF(s) older than $KEEP_DAYS days in $PDF_DIR"
