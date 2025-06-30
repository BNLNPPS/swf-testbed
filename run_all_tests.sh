#!/bin/bash
set -e

# Print a single 100-character line of '*' between two blank lines as the first output
printf "\n%100s\n\n" | tr ' ' '*'

# Get the directory of the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Autodiscover all swf-* repos in the parent directory
REPO_PARENT="$(dirname "$SCRIPT_DIR")"
REPOS=()
while IFS= read -r -d '' dir; do
    REPOS+=("$(basename "$dir")")
done < <(find "$REPO_PARENT" -maxdepth 1 -type d -name 'swf-*' -print0 | sort -z)

for repo in "${REPOS[@]}"; do
    REPO_PATH="$REPO_PARENT/$repo"
    TEST_SCRIPT="$REPO_PATH/run_tests.sh"
    echo "--- Running tests for $repo ---"
    if [ -x "$TEST_SCRIPT" ]; then
        # Prevent recursion: for swf-testbed, run tests directly instead of calling run_tests.sh
        if [ "$repo" == "swf-testbed" ] && [ "$SCRIPT_DIR" == "$REPO_PATH" ]; then
            echo "Running swf-testbed tests directly to prevent recursion..."
            if [ -d "$REPO_PATH/tests" ] && [ "$(ls -A "$REPO_PATH/tests" 2>/dev/null)" ]; then
                (cd "$REPO_PATH" && pytest tests)
            else
                echo "[SKIP] No tests/ directory found in swf-testbed. Skipping."
            fi
        else
            (cd "$REPO_PATH" && ./run_tests.sh)
        fi
    else
        echo "[SKIP] No test runner found for $repo. Skipping."
    fi
    echo "--- Finished $repo ---"
done

echo "--- All tests completed successfully ---"
