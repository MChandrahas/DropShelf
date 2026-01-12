#!/bin/bash

# 1. Prepare Directory Structure
mkdir -p build/DEBIAN
mkdir -p build/usr/bin
mkdir -p build/usr/share/applications
mkdir -p build/usr/share/pixmaps  # [ADDED] Create pixmaps folder

# 2. Copy Files
cp control build/DEBIAN/
cp dropshelf build/usr/bin/
cp dropshelf.desktop build/usr/share/applications/
cp icon.png build/usr/share/pixmaps/dropshelf.png  # [ADDED] Install and rename icon

# 3. Set Permissions
chmod 755 build/DEBIAN/control
chmod 755 build/usr/bin/dropshelf

# 4. Build Package
dpkg-deb --build build dropshelf_1.0_all.deb

# 5. Cleanup
rm -rf build

echo "Build Complete: dropshelf_1.0_all.deb"
