# DropShelf
A temporary drag-and-drop shelf for your files.

## Status
**Active.** (Switched to native Debian packaging to resolve previous GTK4 drag-and-drop issues).

## What it does
DropShelf is a holding zone for files. Drag files onto the shelf to store them temporarily, then drop them wherever you need. Useful when moving files between folders or apps.

Features:
- Drag files from anywhere onto the shelf
- Drag files out to any folder or application
- Download images by dragging URLs from browser
- Pin files to keep them on the shelf
- Search and filter your files
- Batch mode (drag all files at once) or single mode (hold Ctrl)

## Installation

### Debian/Ubuntu
Download the latest `.deb` file from the [Releases Page](/releases).

```bash
sudo dpkg -i dropshelf_0.1.0_all.deb
```

### Dependencies
If you see missing dependency errors, run:
```bash
sudo apt install python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
```

## Usage
Launch from your application menu or run:
```bash
dropshelf
```

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| Ctrl + drag | Drag single file instead of all |
| Backspace | Delete selected file |
| Shift + Delete | Clear all files |
| Ctrl + F | Search |
| Ctrl + D | Lock mode (read-only) |
| Ctrl + Q | Quit |


## Why not Snap?
I initially tried packaging as a Snap, but GTK4 applications in Snap containers have drag-and-drop issues with system apps like Nautilus. This is a known platform limitation with Wayland security contexts. The `.deb` package works without these issues.

## Requirements
- Ubuntu 22.04+ or Debian 12+
- GTK4 and Libadwaita

## License
GPL-3.0. See [LICENSE](LICENSE) file.
```
