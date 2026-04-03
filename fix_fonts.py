import sys, os
utils_path = os.path.join(os.path.dirname(__file__), 'utils.py')

with open(utils_path, 'r') as f:
    content = f.read()

# Replace hardcoded Linux font with auto-detect
old_font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
mac_fonts = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]

# Find first available font
found_font = None
for font in mac_fonts:
    if os.path.exists(font):
        found_font = font
        break

if found_font:
    content = content.replace(old_font, found_font)
    with open(utils_path, 'w') as f:
        f.write(content)
    print(f"✅ Fixed font path: {found_font}")
else:
    print("⚠️ No macOS font found - using fallback")
    content = content.replace(old_font, "Arial")
    with open(utils_path, 'w') as f:
        f.write(content)
