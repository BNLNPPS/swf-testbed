#!/bin/bash
# Make sure this script has execute permissions: chmod +x my_script.sh

echo "Running on $(hostname)"
echo "Start time: $(date)"

if [ $# -ne 1 ]; then
    echo "[ERROR] Usage: $0 '<stf_json>'"
    exit 1
fi

STF_JSON="$1"

echo "[INFO] Received STF JSON:"
echo "$STF_JSON"

# Check jq
if ! command -v jq &>/dev/null; then
    echo "[ERROR] jq is not installed!"
    exit 1
fi

# Extract fields from the actual message format sent by the processing agent
RUN_ID=$(echo "$STF_JSON" | jq -r '.run_id')
FILENAME=$(echo "$STF_JSON" | jq -r '.filename')
STATE=$(echo "$STF_JSON" | jq -r '.state')
SUBSTATE=$(echo "$STF_JSON" | jq -r '.substate')

echo "[INFO] Processing Agent Dataset Metadata:"
echo "  Run ID:    $RUN_ID"
echo "  Filename:  $FILENAME"
echo "  State:     $STATE"
echo "  Substate:  $SUBSTATE"

# This is dataset-based processing - one job processes entire run
echo "[INFO] Starting dataset-based STF processing for run $RUN_ID..."

# In a real implementation, one would:
# 1. List the dataset contents via Rucio API
# 2. Download/access the STF files in the dataset
# 3. Process all files in the run
echo "[INFO] Simulating dataset processing (all STF files in run)..."
sleep 3

# Create output file with processing results
cat > myout.txt <<EOF
STF Dataset Processing Results
==============================
Processing completed at: $(date)
Hostname: $(hostname)

Dataset Processing Details:
  Run ID:           $RUN_ID
  Dataset Filename: $FILENAME
  Processing State: $STATE
  Processing Stage: $SUBSTATE

Processing Mode: Dataset-based (entire run processed as one job)
Processing Status: SUCCESS
Output Files Generated: myout.txt

Notes:
- This job processes all STF files collected for run $RUN_ID
- Files were gathered by the processing agent during data_ready messages
- Dataset was closed at end_run and submitted as single PanDA job

Full JSON Input:
$STF_JSON
EOF

echo "[INFO] Dataset processing completed successfully"
echo "[INFO] Output written to myout.txt"
echo "Done at: $(date)"

# Show what we created
echo "[INFO] Output file contents:"
cat myout.txt
