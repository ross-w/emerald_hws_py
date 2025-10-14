#!/bin/bash

# Script to manually run pre-commit hooks
# Useful for checking all files or when hooks are bypassed

set -e

echo "Running pre-commit hooks..."

if [ "$1" = "--all-files" ]; then
    echo "Running on all files in the repository..."
    pre-commit run --all-files
else
    echo "Running on staged files..."
    pre-commit run
fi

echo "Pre-commit hooks completed successfully!"