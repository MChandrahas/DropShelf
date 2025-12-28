import sys
import os
import json
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
        self.app = app # Save app reference for shortcuts
        
        # KEYBOARD TRACKER
        self.ctrl_pressed = False
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        key_controller.connect("key-released", self.on_key_released)
        self.add_controller(key_controller)
        
        self.connect("close-request", self.on_close_request)
        
        self.state_file = os.path.join(os.getcwd(), "state.json")
        self.store = Gio.ListStore(item_type=FileItem)

        self.toolbar_view = Adw.ToolbarView()
        self.set_content(self.toolbar_view)

        # HEADER
        self.header_bar = Adw.HeaderBar()
        self.toolbar_view.add_top_bar(self.header_bar)
        
        # PREFERENCES BUTTON (Search Icon)
        self.prefs_btn = Gtk.Button(icon_name="system-search-symbolic")
        self.prefs_btn.add_css_class("flat")
        self.prefs_btn.set_tooltip_text("Settings & Shortcuts")
        self.prefs_btn.connect("clicked", self.on_prefs_clicked)
        self.header_bar.pack_start(self.prefs_btn)
        
        # QUIT BUTTON
        quit_btn = Gtk.Button(icon_name="application-exit-symbolic")
        quit_btn.add_css_class("flat")
        quit_btn.connect("clicked", lambda x: app.quit())
        self.header_bar.pack_end(quit_btn)

        self.scrolled_window = Gtk.ScrolledWindow()
        self.toolbar_view.set_content(self.scrolled_window)
        
        # STATUS BAR
        self.status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.status_bar.add_css_class("toolbar")
        self.status_label = Gtk.Label(label="Batch Mode (Drag All)")
        self.status_label.set_hexpand(True)
        self.status_label.set_margin_top(8)
        self.status_label.set_margin_bottom(8)
        self.status_bar.append(self.status_label)
        self.toolbar_view.add_bottom_bar(self.status_bar)

        # LIST VIEW
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.on_factory_setup)
        factory.connect("bind", self.on_factory_bind)

        selection_model = Gtk.NoSelection(model=self.store)
        self.list_view = Gtk.ListView(model=selection_model, factory=factory)
        self.scrolled_window.set_child(self.list_view)

        self.setup_drop_target()
        self.load_state()

    # --- PREFERENCES LOGIC ---
    def on_prefs_clicked(self, btn):
        prefs_window = Adw.PreferencesWindow(transient_for=self)
        prefs_window.set_default_size(500, 600)
        prefs_window.set_search_enabled(True) # ENABLE THE SEARCH BAR

        # PAGE 1: GENERAL
        page_general = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")
        prefs_window.add(page_general)

        # Group: Behavior
        group_behavior = Adw.PreferencesGroup(title="Behavior")
        page_general.add(group_behavior)

        # Switch: Always Keep Items
        row_keep = Adw.SwitchRow(title="Always keep items when dragging out")
        row_keep.set_subtitle("This option also disables the Alt shortcut")
        group_behavior.add(row_keep)

        # Switch: Download Images
        row_dl = Adw.SwitchRow(title="Download images from URLs")
        row_dl.set_subtitle("Automatically save images from dropped links")
        row_dl.set_active(True) # Default On
        group_behavior.add(row_dl)

        # Group: Shortcuts
        group_shortcuts = Adw.PreferencesGroup(title="Shortcuts")
        page_general.add(group_shortcuts)

        # Action: Show Shortcuts
        row_shortcuts = Adw.ActionRow(title="Keyboard Shortcuts")
        row_shortcuts.set_subtitle("View all available shortcuts")
        row_shortcuts.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row_shortcuts.set_activatable(True)
        row_shortcuts.connect("activated", self.show_shortcuts_window)
        group_shortcuts.add(row_shortcuts)

        prefs_window.present()

    def show_shortcuts_window(self, *args):
        shortcuts = Gtk.ShortcutsWindow(transient_for=self, modal=True)
        
        section = Gtk.ShortcutsSection()
        section.set_visible(True)
        shortcuts.set_child(section)
        
        group = Gtk.ShortcutsGroup(title="General")
        section.add_group(group)
        
        # Define the shortcuts to display
        self.add_shortcut_row(group, "<Ctrl>Drag", "Drag Single File")
        self.add_shortcut_row(group, "Drag", "Batch Drag (All Files)")
        self.add_shortcut_row(group, "<Ctrl>Q", "Quit Application")
        
        shortcuts.present()

    def add_shortcut_row(self, group, accelerator, title):
        shortcut = Gtk.ShortcutsShortcut(accelerator=accelerator, title=title)
        group.add_shortcut(shortcut)

    # --- KEYBOARD LOGIC ---
    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval in [Gdk.KEY_Control_L, Gdk.KEY_Control_R]:
            self.ctrl_pressed = True
            self.update_status_ui()
    
    def on_key_released(self, controller, keyval, keycode, state):
        if keyval in [Gdk.KEY_Control_L, Gdk.KEY_Control_R]:
            self.ctrl_pressed = False
            self.update_status_ui()

    def update_status_ui(self):
        if self.ctrl_pressed:
            self.status_label.set_label("Single Mode (Drag One)")
            self.status_label.add_css_class("error") 
        else:
            self.status_label.set_label("Batch Mode (Drag All)")
            self.status_label.remove_css_class("error")

    # --- DRAG & DROP LOGIC ---
    def on_drag_prepare(self, source, x, y, list_item):
        current_file_item = list_item.get_item()
        uri_list = []
        if self.ctrl_pressed:
            gfile = Gio.File.new_for_path(current_file_item.path)
            uri_list.append(gfile.get_uri())
        else:
            for i in range(self.store.get_n_items()):
                item = self.store.get_item(i)
                gfile = Gio.File.new_for_path(item.path)
                uri_list.append(gfile.get_uri())
        
        uri_string = "\r\n".join(uri_list) + "\r\n"
        bytes_data = GLib.Bytes.new(uri_string.encode('utf-8'))
        return Gdk.ContentProvider.new_for_bytes("text/uri-list", bytes_data)

    def setup_drop_target(self):
        target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        target.connect("drop", self.on_file_drop)
        self.toolbar_view.add_controller(target)

    def on_file_drop(self, target, file_list, x, y):
        files = file_list.get_files()
        existing_paths = set()
        for i in range(self.store.get_n_items()):
            existing_paths.add(self.store.get_item(i).path)
        
        changes_made = False
        for file_obj in files:
            path = file_obj.get_path()
            if path and path not in existing_paths:
                new_item = FileItem(path)
                self.store.append(new_item)
                existing_paths.add(path)
                changes_made = True
        
        if changes_made:
            self.save_state()
        return True

    # --- BOILERPLATE & FACTORY ---
    def on_close_request(self, window):
        self.set_visible(False)
        return True

    def load_state(self):
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            for item_data in data:
                path = item_data.get('path')
                if path and os.path.exists(path):
                    self.store.append(FileItem(path))
        except Exception:
            pass

    def save_state(self):
        data = []
        for i in range(self.store.get_n_items()):
            item = self.store.get_item(i)
            data.append({"path": item.path, "filename": item.filename})
        try:
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

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
        
        drag_source = Gtk.DragSource()
        drag_source.set_actions(Gdk.DragAction.COPY)
        drag_source.connect("prepare", self.on_drag_prepare, list_item)
        box.add_controller(drag_source)

        list_item.widgets = (icon, label)

    def on_factory_bind(self, factory, list_item):
        icon, label = list_item.widgets
        file_item = list_item.get_item()
        icon.set_from_icon_name(file_item.icon_name)
        label.set_label(file_item.filename)

    def on_delete_clicked(self, btn, list_item):
        position = list_item.get_position()
        if position != Gtk.INVALID_LIST_POSITION:
            self.store.remove(position)
            self.save_state()

class DropShelfApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.dropshelf.app', flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = DropShelfWindow(self)
            win.present()
        else:
            if win.is_visible():
                win.set_visible(False)
            else:
                win.set_visible(True)
                win.present()

if __name__ == '__main__':
    app = DropShelfApp()
    app.run(sys.argv)
