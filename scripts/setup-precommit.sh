#!/bin/bash

# Setup script for pre-commit hooks
# This script installs pre-commit and sets up the hooks for this repository

set -e

echo "Setting up pre-commit hooks..."

# Check if pre-commit is installed, install if not
if ! command -v pre-commit &> /dev/null; then
    echo "Installing pre-commit..."
    pip install pre-commit
fi

# Install the pre-commit hooks
echo "Installing pre-commit hooks..."
pre-commit install

echo "Pre-commit hooks installed successfully!"
echo ""
echo "The hooks will now run automatically before each commit:"
echo "  - Ruff formatter"
echo "  - Ruff linter"
echo ""
echo "To run hooks manually on all files:"
echo "  pre-commit run --all-files"
echo ""
echo "To update hooks to latest versions:"
echo "  pre-commit autoupdate"
