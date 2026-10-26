#!/bin/bash

# =====================================================================
# 🛰️ PROJECT VIGIL // MULTI-TAB OPEN SOURCE AUTOMATED INSTALLER (AGPL-3.0-or-later)
# =====================================================================

echo "============================================================="
echo "🛰️  PROJECT VIGIL: Initializing Sovereign Installer Stack..."
echo "============================================================="

# 1. Update system packages and install prerequisites
echo "📦 Step 1: Verification of core dependencies..."
sudo apt update
sudo apt install -y python3 python3-pip python-is-python3 gnome-terminal psmisc

# 2. Establish uniform project directory inside the user's home folder
echo "📂 Step 2: Synchronizing project environment architecture..."
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/project-vigil"
mkdir -p "$TARGET_DIR"

if [ "$SOURCE_DIR" != "$TARGET_DIR" ]; then
    echo "📄 Copying project files from $SOURCE_DIR into $TARGET_DIR..."
    cp -r "$SOURCE_DIR"/. "$TARGET_DIR"/
    echo "✓ Project files copied to $TARGET_DIR"
else
    echo "✓ Already running from $TARGET_DIR — no copy needed"
fi

# 3. Create the unified out-of-the-box Launch Script
echo "🚀 Step 3: Generating Master Multitasking Boot Director..."
cat << 'EOF' > "$TARGET_DIR/launch_matrix.sh"
#!/bin/bash
# Project Vigil Master Execution Hook

TARGET_DIR="$HOME/project-vigil"
cd "$TARGET_DIR"

echo "🧹 Clearing port 8085 to prevent socket collision blocks..."
sudo fuser -k 8085/tcp 2>/dev/null

echo "🛰️  Deploying Project Vigil Environment Matrix..."

# Tab 1: Initialize main Python Hub Engine Backend
gnome-terminal --tab --title="VIGIL CORE" -- bash -c "python3 vigil_kernel.py; exec bash"

# Tab 2: Initialize Mock Hardware Network Broadcast Simulation Loop
if [ -f "test_device.sh" ]; then
    gnome-terminal --tab --title="DEVICE EMULATOR" -- bash -c "bash test_device.sh; exec bash"
fi

# Tab 3: Open Firefox sandbox directly to the local controller interface
echo "🌐 Initializing Firefox Interface Viewport..."
firefox --private-window http://127.0.0.1:8085 &

echo "============================================================="
echo "🪐 MATRIX ONLINE: Workspace deployed across operational tabs."
echo "============================================================="
EOF

# 4. Make all operations executable
chmod +x "$TARGET_DIR/launch_matrix.sh"

echo "============================================================="
echo "✓ INSTALLATION SECURED UNDER AGPL-3.0-or-later COMPLIANCE"
echo "============================================================="
echo "To fire up the entire smart ecosystem out of the box, run:"
echo "cd $TARGET_DIR && ./launch_matrix.sh"
echo "============================================================="

