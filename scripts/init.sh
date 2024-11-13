#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "Initializing application..."

# Create the /data/tmp directory on the volume
mkdir -p /data/tmp

echo "Directory /data/tmp created successfully."

# Optional: Check available disk space
df -h

echo "Initialization complete."
