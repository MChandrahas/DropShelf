#!/usr/bin/env python3
import sys
import os
import json
import gi
import warnings
import urllib.request
import base64
from urllib.parse import urlparse, unquote

warnings.filterwarnings("ignore")

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
        
        if path.endswith(".csv"):
            self.icon_name = "x-office-spreadsheet-symbolic"
        elif path.endswith(".txt"):
            self.icon_name = "text-x-generic"
        elif any(path.lower().endswith(ext) for ext in ['.jpg', '.png', '.jpeg', '.gif', '.webp']):
            self.icon_name = "image-x-generic"

# --- MAIN WINDOW ---
class DropShelfWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="DropShelf")
        self.set_default_size(500, 400)
        self.app = app 
        
        self.ctrl_pressed = False
        self.locked = False # Default state
        
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        key_controller.connect("key-released", self.on_key_released)
        self.add_controller(key_controller)
        
        self.connect("close-request", self.on_close_request)
        
        self.state_file = os.path.join(os.getcwd(), "state.json")
        self.cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "dropshelf")
        os.makedirs(self.cache_dir, exist_ok=True)

        self.store = Gio.ListStore(item_type=FileItem)
        self.settings = {
            "download_images": True,
            "csv_mode": False
        } 

        self.toolbar_view = Adw.ToolbarView()
        self.set_content(self.toolbar_view)

        self.header_bar = Adw.HeaderBar()
        self.toolbar_view.add_top_bar(self.header_bar)
        
        self.menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        self.menu_btn.add_css_class("flat")
        self.header_bar.pack_start(self.menu_btn)
        self.setup_menu_popover()

        self.scrolled_window = Gtk.ScrolledWindow()
        self.toolbar_view.set_content(self.scrolled_window)
        
        self.status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.status_bar.add_css_class("toolbar")
        self.status_label = Gtk.Label(label="Batch Mode (Drag All)")
        self.status_label.set_hexpand(True)
        self.status_label.set_margin_top(8)
        self.status_label.set_margin_bottom(8)
        self.status_bar.append(self.status_label)
        self.toolbar_view.add_bottom_bar(self.status_bar)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.on_factory_setup)
        factory.connect("bind", self.on_factory_bind)

        self.selection_model = Gtk.SingleSelection(model=self.store)
        self.list_view = Gtk.ListView(model=self.selection_model, factory=factory)
        
        # ADDED: Double-click to preview/open
        self.list_view.connect("activate", self.on_list_item_activated)
        
        self.scrolled_window.set_child(self.list_view)

        self.setup_universal_drop_target()
        self.load_state()

    # --- CORE HELPERS ---
    def get_selected_item(self):
        return self.selection_model.get_selected_item()

    def remove_item_by_index(self, index):
        # 1. LOCK CHECK: If locked, refuse to delete
        if self.locked:
            print("Action blocked: Shelf is Locked.")
            return

        if index >= self.store.get_n_items():
            return

        item = self.store.get_item(index)
        path = item.path

        # 2. Remove from List
        self.store.remove(index)
        self.save_state()

        # 3. Delete from Disk (if it's a cached file)
        if path.startswith(self.cache_dir):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    print(f"Deleted cache file: {path}")
            except Exception as e:
                print(f"Failed to delete file {path}: {e}")

    def toggle_lock_mode(self):
        self.locked = not self.locked
        
        if self.locked:
            self.status_label.set_label("Locked (Read-Only)")
            self.status_label.add_css_class("error") 
            self.header_bar.add_css_class("locked-header") # Optional visual cue
        else:
            self.update_status_ui() 
            self.status_label.remove_css_class("error")
            self.header_bar.remove_css_class("locked-header")

    def preview_selected(self):
        item = self.get_selected_item()
        if item:
            try:
                # Opens with default OS app (Image Viewer, Text Editor, etc.)
                launcher = Gtk.FileLauncher.new(Gio.File.new_for_path(item.path))
                launcher.launch(self, None, None)
            except Exception as e:
                print(f"Failed to launch: {e}")

    def on_list_item_activated(self, list_view, position):
        # Handle double-click
        self.preview_selected()

    # --- CLIPBOARD ---
    def paste_from_clipboard(self):
        if self.locked: return
        clipboard = self.get_display().get_clipboard()
        clipboard.read_texture_async(None, self.on_paste_image)
        clipboard.read_text_async(None, self.on_paste_text)

    def on_paste_image(self, clipboard, result):
        try:
            texture = clipboard.read_texture_finish(result)
            if texture:
                save_path = self.get_unique_path("pasted_image.png")
                texture.save_to_png(save_path)
                self.add_file_path_to_store(save_path)
                self.save_state()
        except Exception:
            pass 

    def on_paste_text(self, clipboard, result):
        try:
            text = clipboard.read_text_finish(result)
            if text:
                self.on_universal_drop(None, text, 0, 0)
        except Exception:
            pass

    # --- MENU & UI ---
    def setup_menu_popover(self):
        popover = Gtk.Popover()
        menu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        menu_box.set_margin_top(12)
        menu_box.set_margin_bottom(12)
        menu_box.set_margin_start(12)
        menu_box.set_margin_end(12)
        popover.set_child(menu_box)

        btn_prefs = Gtk.Button(label="Preferences")
        btn_prefs.add_css_class("flat")
        btn_prefs.set_halign(Gtk.Align.FILL)
        btn_prefs.connect("clicked", self.on_prefs_clicked)
        btn_prefs.connect("clicked", lambda x: popover.popdown()) 
        menu_box.append(btn_prefs)

        btn_shortcuts = Gtk.Button(label="Keyboard Shortcuts")
        btn_shortcuts.add_css_class("flat")
        btn_shortcuts.set_halign(Gtk.Align.FILL)
        btn_shortcuts.connect("clicked", lambda x: self.show_shortcuts_window())
        btn_shortcuts.connect("clicked", lambda x: popover.popdown())
        menu_box.append(btn_shortcuts)

        menu_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        btn_quit = Gtk.Button(label="Quit")
        btn_quit.add_css_class("destructive-action") 
        btn_quit.set_halign(Gtk.Align.FILL)
        btn_quit.connect("clicked", lambda x: self.app.quit())
        menu_box.append(btn_quit)

        self.menu_btn.set_popover(popover)

    def on_prefs_clicked(self, btn):
        prefs_window = Adw.PreferencesWindow(transient_for=self)
        prefs_window.set_default_size(500, 400)
        prefs_window.set_search_enabled(True) 
        
        # Pass main key controller so Ctrl+Q works here too
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        prefs_window.add_controller(key_controller)

        page_general = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")
        prefs_window.add(page_general)

        group_behavior = Adw.PreferencesGroup(title="Behavior")
        page_general.add(group_behavior)

        row_csv = Adw.SwitchRow(title="Collect text as CSV")
        row_csv.set_subtitle("Append text/links to a single list")
        row_csv.set_active(self.settings.get("csv_mode", False))
        row_csv.connect("notify::active", self.on_csv_switch_changed)
        group_behavior.add(row_csv)

        row_dl = Adw.SwitchRow(title="Download images from URLs")
        row_dl.set_subtitle("Automatically save images")
        row_dl.set_active(self.settings.get("download_images", True))
        row_dl.connect("notify::active", self.on_dl_switch_changed)
        group_behavior.add(row_dl)

        group_gen = Adw.PreferencesGroup(title="Application")
        page_general.add(group_gen)

        row_shortcuts = Adw.ActionRow(title="Keyboard Shortcuts")
        row_shortcuts.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row_shortcuts.set_activatable(True)
        row_shortcuts.connect("activated", lambda row: self.show_shortcuts_window())
        group_gen.add(row_shortcuts)

        prefs_window.present()

    def on_dl_switch_changed(self, row, param):
        self.settings["download_images"] = row.get_active()
        self.save_state()

    def on_csv_switch_changed(self, row, param):
        self.settings["csv_mode"] = row.get_active()
        self.save_state()

    def show_shortcuts_window(self):
        win = Adw.Window(transient_for=self, title="Shortcuts")
        win.set_default_size(500, 400)
        win.set_modal(True)
        
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        win.add_controller(key_controller)
        
        toolbar_view = Adw.ToolbarView()
        win.set_content(toolbar_view)
        
        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)
        
        scroll = Gtk.ScrolledWindow()
        toolbar_view.set_content(scroll)
        
        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        scroll.set_child(clamp)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(12)
        box.set_margin_end(12)
        clamp.set_child(box)

        group_mouse = Adw.PreferencesGroup(title="Mouse Interactions")
        box.append(group_mouse)
        self.add_manual_row(group_mouse, "Drag Single File", "Ctrl + Drag")
        self.add_manual_row(group_mouse, "Batch Drag (All Files)", "Drag")
        self.add_manual_row(group_mouse, "Open/Preview File", "Double Click")

        group_kb = Adw.PreferencesGroup(title="Keyboard Shortcuts")
        box.append(group_kb)
        
        self.add_manual_row(group_kb, "Paste from Clipboard", "Ctrl + V")
        self.add_manual_row(group_kb, "Preview Selected Item", "Ctrl + P")
        self.add_manual_row(group_kb, "Toggle Lock Mode", "Ctrl + D")
        self.add_manual_row(group_kb, "Show Shortcuts", "Ctrl + ?")
        self.add_manual_row(group_kb, "Delete Selected Item", "Backspace")
        self.add_manual_row(group_kb, "Clear All Items", "Shift + Delete")
        self.add_manual_row(group_kb, "Quit Application", "Ctrl + Q")
        
        win.present()

    def add_manual_row(self, group, title, keystring):
        row = Adw.ActionRow(title=title)
        lbl = Gtk.Label(label=keystring)
        lbl.set_valign(Gtk.Align.CENTER)
        lbl.add_css_class("dim-label")
        row.add_suffix(lbl)
        group.add(row)

    # --- KEYBOARD LOGIC ---
    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_q and (state & Gdk.ModifierType.CONTROL_MASK):
            self.app.quit()
            return True
        if keyval == Gdk.KEY_question and (state & Gdk.ModifierType.CONTROL_MASK):
            self.show_shortcuts_window()
            return True
        if keyval == Gdk.KEY_d and (state & Gdk.ModifierType.CONTROL_MASK):
            self.toggle_lock_mode()
            return True
        if keyval == Gdk.KEY_p and (state & Gdk.ModifierType.CONTROL_MASK):
            self.preview_selected()
            return True
        if keyval == Gdk.KEY_v and (state & Gdk.ModifierType.CONTROL_MASK):
            self.paste_from_clipboard()
            return True

        # DELETE / BACKSPACE
        is_delete = (keyval == Gdk.KEY_Delete)
        is_backspace = (keyval == Gdk.KEY_BackSpace)
        is_shift = (state & Gdk.ModifierType.SHIFT_MASK)

        # 1. DELETE SELECTED (Backspace OR Delete-no-shift)
        if (is_backspace) or (is_delete and not is_shift):
            # Get selected POSITION directly from selection model
            selected_pos = self.selection_model.get_selected()
            if selected_pos != Gtk.INVALID_LIST_POSITION:
                self.remove_item_by_index(selected_pos)
            return True

        # 2. CLEAR ALL (Shift + Delete)
        if is_delete and is_shift:
            if self.locked: return True
            # Iterate reverse to safely remove
            n = self.store.get_n_items()
            for i in range(n - 1, -1, -1):
                 self.remove_item_by_index(i)
            self.save_state()
            return True

        if keyval in [Gdk.KEY_Control_L, Gdk.KEY_Control_R]:
            self.ctrl_pressed = True
            self.update_status_ui()
        
        return False
    
    def on_key_released(self, controller, keyval, keycode, state):
        if keyval in [Gdk.KEY_Control_L, Gdk.KEY_Control_R]:
            self.ctrl_pressed = False
            self.update_status_ui()

    def update_status_ui(self):
        if self.locked: return 
        if self.ctrl_pressed:
            self.status_label.set_label("Single Mode (Drag One)")
            self.status_label.add_css_class("error") 
        else:
            self.status_label.set_label("Batch Mode (Drag All)")
            self.status_label.remove_css_class("error")

    # --- UNIVERSAL DRAG & DROP LOGIC ---
    def setup_universal_drop_target(self):
        target = Gtk.DropTarget.new(str, Gdk.DragAction.COPY)
        target.connect("drop", self.on_universal_drop)
        self.toolbar_view.add_controller(target)

    def on_universal_drop(self, target, value, x, y):
        if self.locked: return False
        if not value: return False
        
        uris = value.splitlines()
        changes_made = False
        
        for uri in uris:
            uri = uri.strip().replace('\x00', '')
            if not uri: continue

            if uri.startswith("data:image"):
                if self.settings.get("download_images", True):
                    self.save_base64_image(uri)
                continue

            if uri.startswith("http"):
                if self.settings.get("csv_mode", False):
                    self.append_to_csv(uri)
                
                clean_uri = uri.lower().split('?')[0]
                is_image = any(clean_uri.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp'])
                
                if is_image and self.settings.get("download_images", True):
                    self.download_image(uri)
                elif not self.settings.get("csv_mode", False):
                    self.save_text_content(uri, "saved_link.txt")
                continue

            path = None
            if uri.startswith("file://"):
                try:
                    gfile = Gio.File.new_for_uri(uri)
                    path = gfile.get_path()
                except: pass
            elif uri.startswith("/"):
                path = uri
            
            if path and os.path.exists(path):
                 self.add_file_path_to_store(path)
                 changes_made = True
            else:
                 if self.settings.get("csv_mode", False):
                     self.append_to_csv(uri)
                 else:
                     self.save_text_content(uri, "dragged_text.txt")

        if changes_made:
            self.save_state()
        return True

    def append_to_csv(self, text):
        csv_path = os.path.join(self.cache_dir, "collected.csv")
        try:
            with open(csv_path, "a") as f:
                clean_text = text.replace("\n", " ").replace("\r", "")
                f.write(f'"{clean_text}"\n')
            self.add_file_path_to_store(csv_path)
            self.save_state()
            if not self.status_label.get_label() == "Downloading...":
                 self.status_label.set_label("Added to CSV")
                 GLib.timeout_add(1500, lambda: self.update_status_ui() or False)
        except Exception: pass

    def save_text_content(self, content, default_name):
        save_path = self.get_unique_path(default_name)
        try:
            with open(save_path, "w") as f:
                f.write(content)
            self.add_file_path_to_store(save_path)
            self.save_state()
        except Exception: pass

    def add_file_path_to_store(self, path):
        for i in range(self.store.get_n_items()):
            if self.store.get_item(i).path == path:
                return 
        self.store.append(FileItem(path))

    def save_base64_image(self, uri):
        try:
            header, encoded = uri.split(",", 1)
            ext = ".png"
            if "jpeg" in header: ext = ".jpg"
            if "webp" in header: ext = ".webp"
            save_path = self.get_unique_path("dropped_image" + ext)
            with open(save_path, "wb") as f:
                f.write(base64.b64decode(encoded))
            self.add_file_path_to_store(save_path)
            self.save_state()
        except Exception: pass

    def download_image(self, url):
        try:
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path)
            if not filename or len(filename) < 3 or "." not in filename:
                filename = "downloaded_image.jpg"
            else:
                filename = unquote(filename)
            save_path = self.get_unique_path(filename)
            self.status_label.set_label("Downloading...")
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            def dl_worker():
                try:
                    with urllib.request.urlopen(req) as response, open(save_path, 'wb') as out_file:
                        out_file.write(response.read())
                    GLib.idle_add(self.on_download_success, save_path)
                except Exception:
                    if not self.settings.get("csv_mode", False):
                        GLib.idle_add(self.save_text_content, url, "saved_link.txt")
                    GLib.idle_add(self.update_status_ui)
            import threading
            threading.Thread(target=dl_worker, daemon=True).start()
        except Exception:
            if not self.settings.get("csv_mode", False):
                self.save_text_content(url, "saved_link.txt")

    def get_unique_path(self, filename):
        save_path = os.path.join(self.cache_dir, filename)
        base, ext = os.path.splitext(save_path)
        counter = 1
        while os.path.exists(save_path):
            save_path = f"{base}_{counter}{ext}"
            counter += 1
        return save_path

    def on_download_success(self, save_path):
        self.add_file_path_to_store(save_path)
        self.save_state()
        self.status_label.set_label("Downloaded!")
        GLib.timeout_add(2000, lambda: self.update_status_ui() or False)

    # --- DRAG OUT ---
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

    def on_close_request(self, window):
        self.set_visible(False)
        return True

    def load_state(self):
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            items = data.get("items", [])
            for item_data in items:
                path = item_data.get('path')
                if path and os.path.exists(path):
                    self.store.append(FileItem(path))
            self.settings = data.get("settings", {"download_images": True, "csv_mode": False})
        except Exception: pass

    def save_state(self):
        items_data = []
        for i in range(self.store.get_n_items()):
            item = self.store.get_item(i)
            items_data.append({"path": item.path, "filename": item.filename})
        data = {"items": items_data, "settings": self.settings}
        try:
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception: pass

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
        if self.locked: return
        # Safe callback for the Trash button
        position = list_item.get_position()
        if position != Gtk.INVALID_LIST_POSITION:
            self.remove_item_by_index(position)

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
