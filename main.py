import sys
import os
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio, Gdk, GObject, GLib

# --- DATA MODEL ---
class FileItem(GObject.Object):
    __gtype_name__ = 'FileItem'
    
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.filename = os.path.basename(path)
        self.icon_name = "text-x-generic"

# --- MAIN WINDOW ---
class DropShelfWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="DropShelf")
        self.set_default_size(500, 400)

        self.store = Gio.ListStore(item_type=FileItem)

        self.toolbar_view = Adw.ToolbarView()
        self.set_content(self.toolbar_view)

        self.header_bar = Adw.HeaderBar()
        self.toolbar_view.add_top_bar(self.header_bar)

        self.scrolled_window = Gtk.ScrolledWindow()
        self.toolbar_view.set_content(self.scrolled_window)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.on_factory_setup)
        factory.connect("bind", self.on_factory_bind)

        selection_model = Gtk.NoSelection(model=self.store)
        self.list_view = Gtk.ListView(model=selection_model, factory=factory)
        self.scrolled_window.set_child(self.list_view)

        self.setup_drop_target()

    # --- ROW CREATION ---
    def on_factory_setup(self, factory, list_item):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        icon = Gtk.Image()
        icon.set_pixel_size(32)
        
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        label.set_ellipsize(3)

        delete_btn = Gtk.Button(icon_name="user-trash-symbolic")
        delete_btn.add_css_class("flat")
        delete_btn.connect("clicked", self.on_delete_clicked, list_item)

        box.append(icon)
        box.append(label)
        box.append(delete_btn)
        
        list_item.set_child(box)
        
        # Configure Drag Source
        drag_source = Gtk.DragSource()
        
        # FIX: STRICTLY allow only COPY. 
        # This forces the file manager to duplicate the file, not move it.
        drag_source.set_actions(Gdk.DragAction.COPY)
        
        drag_source.connect("prepare", self.on_drag_prepare, list_item)
        box.add_controller(drag_source)

        list_item.widgets = (icon, label)

    def on_factory_bind(self, factory, list_item):
        icon, label = list_item.widgets
        file_item = list_item.get_item()
        icon.set_from_icon_name(file_item.icon_name)
        label.set_label(file_item.filename)

    # --- DRAG SOURCE (Dragging OUT) ---
    def on_drag_prepare(self, source, x, y, list_item):
        file_item = list_item.get_item()
        gfile = Gio.File.new_for_path(file_item.path)
        
        # THE FIX: Manually build a "text/uri-list"
        # This is the universal format Linux file managers understand.
        # It looks like: file:///home/user/file.txt\r\n
        
        uri = gfile.get_uri()
        uri_string = f"{uri}\r\n" # Must end with new line
        
        # Create a GLib.Bytes object
        bytes_data = GLib.Bytes.new(uri_string.encode('utf-8'))
        
        print(f"DEBUG: Dragging URI -> {uri}")
        
        # Hand this raw text data to the OS
        return Gdk.ContentProvider.new_for_bytes("text/uri-list", bytes_data)

    # --- DELETE ---
    def on_delete_clicked(self, btn, list_item):
        position = list_item.get_position()
        if position != Gtk.INVALID_LIST_POSITION:
            self.store.remove(position)

    # --- DROP TARGET (Dragging IN) ---
    def setup_drop_target(self):
        target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        target.connect("drop", self.on_file_drop)
        self.toolbar_view.add_controller(target)

    def on_file_drop(self, target, file_list, x, y):
        files = file_list.get_files()
        for file_obj in files:
            path = file_obj.get_path()
            if path:
                new_item = FileItem(path)
                self.store.append(new_item)
        return True

class DropShelfApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.dropshelf.app',
                         flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = DropShelfWindow(self)
        win.present()

if __name__ == '__main__':
    app = DropShelfApp()
    app.run(sys.argv)
