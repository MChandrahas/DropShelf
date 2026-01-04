# This Snap project is on hold because of the GTK4 limitations (chack the branch "refactor-cleanup" for updated code)

The Drag-and-Drop fails when I try to drop the files from shelf to Nautilus. 
(please keep an eye for the fix of Drag-and-Drop compatibility for GTK4 on the snapcraft forum.)

## The Problem

### Snap Sandboxing
Snap apps run in a confined environment with limited access to the host system.

### Portal Limitations
GTK4 uses XDG Desktop Portals for DnD, but the portal support for drag-and-drop between sandboxed apps and native file managers is incomplete.

### Wayland/X11 Differences
DnD behavior varies between display servers.
