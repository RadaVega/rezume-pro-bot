!/usr/bin/env python3
"""
debug_vk.py — Patches main.py webhook to log every raw VK payload to vk_debug.log
Run: python3 debug_vk.py
Then send a PDF file and an HH link to the bot in VK.
Then: cat vk_debug.log
"""
import re

with open("main.py") as f:
    src = f.read()

LOG_INJECTION = '''
    # ── DEBUG: log every raw payload ──────────────────────────────────────────
    import json as _json
    try:
        with open("vk_debug.log", "a") as _f:
            _f.write("\\n=== " + __import__("datetime").datetime.now().isoformat() + " ===\\n")
            _f.write(_json.dumps(data, ensure_ascii=False, indent=2))
            _f.write("\\n")
    except Exception as _e:
        logger.error("debug log error: %s", _e)
    # ── END DEBUG ──────────────────────────────────────────────────────────────
'''

# Inject right after "data = request.json or {}" in the webhook function
src = src.replace(
    "    data = request.json or {}\n\n    # VK confirmation handshake",
    "    data = request.json or {}" + LOG_INJECTION + "\n    # VK confirmation handshake"
)

with open("main.py", "w") as f:
    f.write(src)

print("✅ Debug logging added to main.py")
print("📋 Now run: ./restart.sh")
print("📋 Then send a PDF file to the VK bot, then an HH link")
print("📋 Then run: cat vk_debug.log")