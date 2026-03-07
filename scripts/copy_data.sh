#!/usr/bin/env bash
# Copy historical CSVs into this repo's data/raw/ directory.
#
# Usage:
#   DATA_SRC=/path/to/your/csvs bash scripts/copy_data.sh
#
# If DATA_SRC is not set, you will be prompted for the path.

set -e

DST="./data/raw"

if [ -z "$DATA_SRC" ]; then
    echo "DATA_SRC not set."
    echo "Enter the path to the directory containing your CSV files:"
    read -r DATA_SRC
fi

SRC="${DATA_SRC%/}"   # strip trailing slash

if [ ! -d "$SRC" ]; then
    echo "ERROR: Source directory not found: $SRC"
    echo "Set DATA_SRC to the directory that contains MNQ_15m.csv etc."
    exit 1
fi

mkdir -p "$DST"

FILES=(
    "MNQ_1m.csv"  "MNQ_5m.csv"  "MNQ_15m.csv"
    "MES_1m.csv"  "MES_5m.csv"  "MES_15m.csv"
    "MGC_1m.csv"  "MGC_5m.csv"  "MGC_15m.csv"
)

echo "Copying CSV files from: $SRC"
echo "Destination: $DST"
echo ""

found=0
for f in "${FILES[@]}"; do
    src_file="$SRC/$f"
    dst_file="$DST/$f"
    if [ -f "$src_file" ]; then
        cp "$src_file" "$dst_file"
        size=$(du -sh "$dst_file" | cut -f1)
        echo "  [OK] $f ($size)"
        found=$((found + 1))
    else
        echo "  [MISSING] $f -- not found in $SRC"
    fi
done

echo ""
echo "Copied $found / ${#FILES[@]} files."
echo "Run 'make verify-data' to confirm integrity."
