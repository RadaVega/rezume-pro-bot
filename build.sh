#!/bin/bash
set -e
pip install --target /home/runner/workspace/.pkgs -r requirements.txt
.pkgs/bin/python3 -c "import requests, flask; print('OK')" 2>/dev/null || python3 -c "
import sys
sys.path.insert(0, '/home/runner/workspace/.pkgs')
import requests, flask, gigachat
print('OK')
"
