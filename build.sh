#!/bin/bash
set -e
echo "📦 Installing dependencies to .pkgs/..."

# Install packages to .pkgs directory
pip install --target /home/runner/workspace/.pkgs -r requirements.txt

# Verify installation using system Python with .pkgs in path
python3 -c "
import sys
sys.path.insert(0, '/home/runner/workspace/.pkgs')
import requests, flask, gigachat, vk_api
print('✅ All core packages OK')
"

echo "✅ Build complete"
