#!/usr/bin/env python3
import sys
import os
import shutil
import json
import warnings
import urllib.request
import base64
import threading
from urllib.parse import urlparse, unquote


import gi


import gi

# These must be called BEFORE importing Gtk, Adw, etc.
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Adw, Gio, Gdk, GObject, GLib, GdkPixbuf


warnings.filterwarnings("ignore")


warnings.filterwarnings("ignore")

# --- DATA MODEL ---
class FileItem(GObject.Object):
    __gtype_name__ = 'FileItem'
    
    def __init__(self, path, pinned=False):
        super().__init__()
        self.path = os.path.abspath(path)
        self.filename = os.path.basename(path)
        self.pinned = pinned
        
        try:
            f = Gio.File.new_for_path(self.path)
            info = f.query_info(Gio.FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE, Gio.FileQueryInfoFlags.NONE, None)
            content_type = info.get_content_type()
            self.gicon = Gio.content_type_get_icon(content_type)
        except:
            self.gicon = Gio.ThemedIcon.new("text-x-generic")





# --- MAIN WINDOW ---
class DropShelfWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="DropShelf")
        self.set_default_size(350, 400)
        self.app = app 
        
        self.ctrl_pressed = False
        self.locked = False
        self.search_query = ""
        self.icon_size = 56
        
        # LOGIC FLAGS
        self.is_dragging = False   
        self.is_self_drop = False  
        
        # KEYBOARD
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        key_controller.connect("key-released", self.on_key_released)
        self.add_controller(key_controller)
        
        self.connect("close-request", self.on_close_request)
        
        # STORAGE
        self.state_file = os.path.join(os.getcwd(), "state.json")
        self.cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "dropshelf")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        self.settings = {
            "download_images": True,
            "csv_mode": False,
            "opacity": 1.0
        }
        # LAYOUT
        self.toolbar_view = Adw.ToolbarView()
        self.set_content(self.toolbar_view)
        self.header_bar = Adw.HeaderBar()
        self.toolbar_view.add_top_bar(self.header_bar)
        
        # LEFT CONTROLS
        self.menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        self.menu_btn.add_css_class("flat")
        self.header_bar.pack_start(self.menu_btn) 
        self.setup_menu_popover()
        self.btn_search = Gtk.ToggleButton(icon_name="system-search-symbolic")
        self.btn_search.set_tooltip_text("Toggle Search (Ctrl+F)")
        self.btn_search.add_css_class("flat")
        self.btn_search.connect("toggled", self.on_search_toggled)
        self.header_bar.pack_start(self.btn_search)
        # SEARCH BAR
        self.search_bar = Gtk.SearchBar()
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Type to filter...")
        self.search_entry.connect("search-changed", self.on_search_changed)
        self.search_bar.set_child(self.search_entry)
        self.search_bar.connect_entry(self.search_entry)
        self.toolbar_view.add_top_bar(self.search_bar)
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
        self.store = Gio.ListStore(item_type=FileItem)
        self.filter = Gtk.CustomFilter.new(match_func=self.filter_func)
        self.filter_model = Gtk.FilterListModel(model=self.store, filter=self.filter)
        self.selection_model = Gtk.SingleSelection(model=self.filter_model)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.on_factory_setup)
        factory.connect("bind", self.on_factory_bind)
        self.list_view = Gtk.ListView(model=self.selection_model, factory=factory)
        self.list_view.connect("activate", self.on_list_item_activated) 
        self.scrolled_window.set_child(self.list_view)
        self.setup_universal_drop_target()
        self.load_state()
    # --- SEARCH ---
    def on_search_toggled(self, btn):
        if btn.get_active():
            self.search_bar.set_search_mode(True)
            self.search_entry.grab_focus()
        else:
            self.search_bar.set_search_mode(False)
    def on_search_changed(self, entry):
        self.search_query = entry.get_text().lower()
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
    def filter_func(self, item, user_data=None):
        if not self.search_query:
            return True
        return self.search_query in item.filename.lower()
    # --- FACTORY & UI LOGIC ---
    def on_factory_setup(self, factory, list_item):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(12)
        box.set_margin_end(12)
        
        icon_wrapper = Gtk.Box()
        icon_wrapper.set_size_request(self.icon_size, self.icon_size) 
        
        img_display = Gtk.Image()
        img_display.set_halign(Gtk.Align.FILL)
        img_display.set_valign(Gtk.Align.FILL)
        img_display.set_pixel_size(self.icon_size)
        
        icon_wrapper.append(img_display)
        
        label = Gtk.Label()
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        label.set_ellipsize(3)
        view_btn = Gtk.Button(icon_name="view-reveal-symbolic")
        view_btn.add_css_class("flat")
        view_btn.set_tooltip_text("Preview File")
        view_btn.set_visible(False) 
        view_btn.connect("clicked", self.on_view_clicked, list_item)
        pin_btn = Gtk.Button(icon_name="view-pin-symbolic")
        pin_btn.add_css_class("flat")
        pin_btn.set_tooltip_text("Pin Item")
        pin_btn.set_visible(False) 
        
        del_btn = Gtk.Button(icon_name="user-trash-symbolic")
        del_btn.add_css_class("flat")
        del_btn.connect("clicked", self.on_delete_clicked, list_item)
        box.append(icon_wrapper)
        box.append(label)
        box.append(view_btn) 
        box.append(pin_btn)
        box.append(del_btn)
        
        list_item.set_child(box)
        
        hover_ctrl = Gtk.EventControllerMotion()
        hover_ctrl.connect("enter", self.on_row_enter, list_item)
        hover_ctrl.connect("leave", self.on_row_leave, list_item)
        box.add_controller(hover_ctrl)
        drag_source = Gtk.DragSource()
        drag_source.set_actions(Gdk.DragAction.COPY)
        drag_source.connect("prepare", self.on_drag_prepare, list_item)
        drag_source.connect("drag-end", self.on_drag_end, list_item)
        box.add_controller(drag_source)
        list_item.widgets = (img_display, icon_wrapper, label, view_btn, pin_btn)
    def on_factory_bind(self, factory, list_item):
        img_display, icon_wrapper, label, view_btn, pin_btn = list_item.widgets
        item = list_item.get_item()
        
        label.set_label(item.filename)
        
        if item.pinned:
            pin_btn.add_css_class("red-icon") 
            pin_btn.set_visible(True) 
        else:
            pin_btn.remove_css_class("red-icon")
            pin_btn.set_visible(False) 
            
        try:
            pin_btn.disconnect_by_func(self.toggle_pin)
        except:
            pass
        pin_btn.connect("clicked", self.toggle_pin, item, pin_btn)
        # --- IMAGE THUMBNAIL LOGIC ---
        is_potential_image = any(item.filename.lower().endswith(x) for x in ['.jpg','.png','.jpeg','.webp'])
        loaded_as_image = False
        target_size = self.icon_size
        
        if is_potential_image and os.path.exists(item.path):
            try:
                # 1. Load original image
                pb = GdkPixbuf.Pixbuf.new_from_file(item.path)
                w, h = pb.get_width(), pb.get_height()
                
                # 2. Calculate scale to "Cover" the square
                scale = max(target_size / w, target_size / h)
                
                # 3. Calculate new dimensions, forcing AT LEAST target_size
                new_w = int(w * scale)
                new_h = int(h * scale)
                if new_w < target_size: new_w = target_size
                if new_h < target_size: new_h = target_size
                
                # 4. Scale the image
                pb_scaled = pb.scale_simple(new_w, new_h, GdkPixbuf.InterpType.BILINEAR)
                
                # 5. Center Crop (safely)
                real_w = pb_scaled.get_width()
                real_h = pb_scaled.get_height()
                
                x_off = (real_w - target_size) // 2
                y_off = (real_h - target_size) // 2
                
                if x_off < 0: x_off = 0
                if y_off < 0: y_off = 0
                if x_off + target_size > real_w: x_off = real_w - target_size
                if y_off + target_size > real_h: y_off = real_h - target_size
                
                cropped_pb = pb_scaled.new_subpixbuf(x_off, y_off, target_size, target_size)
                
                # 6. Set Texture
                texture = Gdk.Texture.new_for_pixbuf(cropped_pb)
                img_display.set_from_paintable(texture)
                
                # Apply Styles
                icon_wrapper.add_css_class("rounded-image")
                icon_wrapper.set_overflow(Gtk.Overflow.HIDDEN) 
                loaded_as_image = True
            except: 
                loaded_as_image = False
        
        if not loaded_as_image:
            img_display.set_from_gicon(item.gicon)
            icon_wrapper.remove_css_class("rounded-image")
            icon_wrapper.set_overflow(Gtk.Overflow.VISIBLE)
    def on_row_enter(self, controller, x, y, list_item):
        if self.locked:
            return
        img, wrapper, lbl, view_btn, pin_btn = list_item.widgets
        view_btn.set_visible(True)
        pin_btn.set_visible(True)
    def on_row_leave(self, controller, list_item):
        item = list_item.get_item()
        img, wrapper, lbl, view_btn, pin_btn = list_item.widgets
        view_btn.set_visible(False)
        if not item.pinned:
            pin_btn.set_visible(False)
    def on_view_clicked(self, btn, list_item):
        self.preview_selected_item_obj(list_item.get_item())
    # --- DRAG LOGIC ---
    def on_drag_prepare(self, source, x, y, list_item):
        self.is_dragging = True
        self.is_self_drop = False
        item = list_item.get_item()
        # print(f"[DRAG] Path: {item.path}")
        # print(f"[DRAG] Exists: {os.path.exists(item.path)}")
        
        item = list_item.get_item()
        if self.ctrl_pressed:
            gfile = Gio.File.new_for_path(item.path)
            content_files = Gdk.ContentProvider.new_for_value(Gdk.FileList.new_from_list([gfile]))
        else:
            n = self.filter_model.get_n_items()
            file_list = []
            for i in range(n):
                fi = self.filter_model.get_item(i)
                file_list.append(Gio.File.new_for_path(fi.path))
            content_files = Gdk.ContentProvider.new_for_value(Gdk.FileList.new_from_list(file_list))
        try:
            is_text = any(item.filename.endswith(x) for x in ['.txt', '.py', '.md', '.csv', '.json'])
            if is_text and not self.ctrl_pressed:
                with open(item.path, 'r') as f:
                    text_content = f.read(1024 * 1024)
                content_text = Gdk.ContentProvider.new_for_bytes("text/plain", GLib.Bytes.new(text_content.encode('utf-8')))
                return Gdk.ContentProvider.new_union([content_files, content_text])
        except:
            pass
        return content_files
    def on_drag_end(self, source, drag, delete_data, list_item):
        self.is_dragging = False
        
        if self.is_self_drop:
            self.is_self_drop = False
            return 




        if self.locked:
            return
        
        if self.ctrl_pressed:
            item = list_item.get_item()
            if item and not item.pinned:
                self.remove_item_from_store(item)
        else:
            n = self.filter_model.get_n_items()
            items_to_remove = []
            for i in range(n):
                fi = self.filter_model.get_item(i)
                if not fi.pinned:
                    items_to_remove.append(fi)
            for item in items_to_remove:
                self.remove_item_from_store(item)
        self.save_state()
    def remove_item_from_store(self, item):
        for i in range(self.store.get_n_items()):
            if self.store.get_item(i) == item:
                self.store.remove(i)
                break
    # --- CORE ---
    def get_selected_item(self):
        return self.selection_model.get_selected_item()
    
    def toggle_pin(self, btn, item, widget_btn=None):
        item.pinned = not item.pinned
        if widget_btn:
            if item.pinned:
                widget_btn.add_css_class("red-icon")
                widget_btn.set_visible(True)
            else:
                widget_btn.remove_css_class("red-icon")
        self.save_state()
        
    def remove_item_by_index(self, index):
        if self.locked:
            return
        item = self.filter_model.get_item(index)
        if not item:
            return
        if item.path.startswith(self.cache_dir):
            try:
                if os.path.exists(item.path):
                    os.remove(item.path)
            except:
                pass
        self.remove_item_from_store(item)
        self.save_state()
        
    def on_delete_clicked(self, btn, list_item):
        if self.locked:
            return
        pos = list_item.get_position()
        if pos != Gtk.INVALID_LIST_POSITION:
            self.remove_item_by_index(pos)
        
    def setup_universal_drop_target(self):
        # 1. Accept FILE LIST (files from file manager)
        target_files = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        target_files.connect("drop", self.on_file_drop)
        self.toolbar_view.add_controller(target_files)
        
        # 2. Accept STRING (text, URLs from browser) - This was missing/disconnected
        target_text = Gtk.DropTarget.new(str, Gdk.DragAction.COPY)
        target_text.connect("drop", self.on_text_drop)
        self.toolbar_view.add_controller(target_text)
        
    def on_file_drop(self, target, value, x, y):

        if self.locked:
            return False
        
        if self.is_dragging:

            self.is_self_drop = True 
            return True 


            self.is_self_drop = True
            return True
        
        # value is Gdk.FileList
        files = value.get_files()
        for gfile in files:
            path = gfile.get_path()
            if path and os.path.exists(path):
                self.add_file_path_to_store(path)
        self.save_state()
        return True
        
    def on_text_drop(self, target, value, x, y):
        if self.locked:
            return False
        
        # Handle self-drop (reordering) logic
        if self.is_dragging:
            self.is_self_drop = True
            return True

        if not value:
            return False
            
        uris = value.splitlines()
        changes_made = False
        
        for uri in uris:
            uri = uri.strip().replace('\x00', '')
            if not uri:
                continue
            
            # 1. Handle Base64 Images
            if uri.startswith("data:image"):
                if self.settings.get("download_images", True):
                    self.save_base64_image(uri)
                continue
            
            # 2. Handle Web URLs
            if uri.startswith("http"):
                clean_uri = uri.lower().split('?')[0]
                is_image = any(clean_uri.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'])
                
                if is_image and self.settings.get("download_images", True):
                    self.download_image(uri)
                    continue
                
                if self.settings.get("csv_mode", False):
                    self.append_to_csv(uri)
                else:
                    self.save_text_content(uri, "saved_link.txt")
                continue
            
            # 3. Handle Local Paths (file:// or /home/...)
            path = None
            if uri.startswith("file://"):
                try:
                    gfile = Gio.File.new_for_uri(uri)
                    path = gfile.get_path()
                except:
                    pass
            elif uri.startswith("/"):
                path = uri
            
            if path and os.path.exists(path):
                self.add_file_path_to_store(path)
                changes_made = True
            else:
                # Fallback: Treat as plain text
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
                f.write(f'"{text.replace(chr(10)," ")}"\n')
            self.add_file_path_to_store(csv_path)
            self.save_state()
            self.show_temp_status("Added to CSV")
        except:
            pass

    def save_text_content(self, content, default_name):
        save_path = self.get_unique_path(default_name)
        try:
            with open(save_path, "w") as f:
                f.write(content)
            self.add_file_path_to_store(save_path)
            self.save_state()
        except:
            pass


    def add_file_path_to_store(self, path):
        for i in range(self.store.get_n_items()):
            if self.store.get_item(i).path == path:
                return 
        self.store.append(FileItem(path))
    def save_base64_image(self, uri):
        try:
            header, encoded = uri.split(",", 1)
            ext = ".png"
            if "jpeg" in header:
                ext = ".jpg"
            save_path = self.get_unique_path("dropped_image" + ext)
            with open(save_path, "wb") as f:
                f.write(base64.b64decode(encoded))
            self.add_file_path_to_store(save_path)
            self.save_state()
        except:
            pass

    def download_image(self, url):
        try:
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path) or "downloaded_image.jpg"
            filename = unquote(filename)
            save_path = self.get_unique_path(filename)
            self.status_label.set_label("Downloading...")
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            
            def dl_worker():
                try:
                    with urllib.request.urlopen(req) as r, open(save_path, 'wb') as f:
                        f.write(r.read())
                    GLib.idle_add(self.on_download_success, save_path)
                except:
                    GLib.idle_add(self.update_status_ui)
                    
            threading.Thread(target=dl_worker, daemon=True).start()
        except:
            pass

    def get_unique_path(self, filename):
        save_path = os.path.join(self.cache_dir, filename)
        base, ext = os.path.splitext(save_path)
        c = 1
        while os.path.exists(save_path):
            save_path = f"{base}_{c}{ext}"
            c += 1
        return save_path
    def on_download_success(self, save_path):
        self.add_file_path_to_store(save_path)
        self.save_state()
        self.show_temp_status("Downloaded!")
    def show_temp_status(self, msg):
        self.status_label.set_label(msg)
        GLib.timeout_add(2000, lambda: self.update_status_ui() or False)
    def toggle_lock_mode(self):
        self.locked = not self.locked
        if self.locked:
            self.status_label.set_label("Locked (Read-Only)")
            self.status_label.add_css_class("error") 
        else:
            self.update_status_ui()
            self.status_label.remove_css_class("error")
    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_q and (state & Gdk.ModifierType.CONTROL_MASK):
            self.app.quit()
            return True
        if keyval == Gdk.KEY_d and (state & Gdk.ModifierType.CONTROL_MASK):
            self.toggle_lock_mode()
            return True
        if keyval == Gdk.KEY_p and (state & Gdk.ModifierType.CONTROL_MASK):
            self.preview_selected()
            return True
        if keyval == Gdk.KEY_question and (state & Gdk.ModifierType.CONTROL_MASK):
            self.show_shortcuts_window()
            return True
        if keyval == Gdk.KEY_f and (state & Gdk.ModifierType.CONTROL_MASK):
            is_active = self.btn_search.get_active()
            self.btn_search.set_active(not is_active)
            return True
        
        is_del = (keyval == Gdk.KEY_Delete)
        is_back = (keyval == Gdk.KEY_BackSpace)
        if is_back or (is_del and not (state & Gdk.ModifierType.SHIFT_MASK)):
            sel_pos = self.selection_model.get_selected()
            if sel_pos != Gtk.INVALID_LIST_POSITION:
                self.remove_item_by_index(sel_pos)
            return True
        if is_del and (state & Gdk.ModifierType.SHIFT_MASK):
            if not self.locked:
                n = self.filter_model.get_n_items()
                for i in range(n-1, -1, -1):
                    self.remove_item_by_index(i)
            return True
        if keyval in [Gdk.KEY_Control_L, Gdk.KEY_Control_R]:
            self.ctrl_pressed = True
            self.update_status_ui()
        return False
    def on_key_released(self, c, k, code, s):
        if k in [Gdk.KEY_Control_L, Gdk.KEY_Control_R]:
            self.ctrl_pressed = False
            self.update_status_ui()

    def update_status_ui(self):
        if self.locked:
            return 
        if self.ctrl_pressed:
            self.status_label.set_label("Single Mode (Drag One)")
            self.status_label.add_css_class("error") 
        else:
            self.status_label.set_label("Batch Mode (Drag All)")
            self.status_label.remove_css_class("error")
    def preview_selected(self):
        item = self.get_selected_item()
        self.preview_selected_item_obj(item)
    def preview_selected_item_obj(self, item):
        if item:
            try:
                l = Gtk.FileLauncher.new(Gio.File.new_for_path(item.path))
                l.launch(self, None, None)
            except:
                pass
            
    def on_list_item_activated(self, list_view, position):
        self.preview_selected()
        
    def on_close_request(self, win):
        self.set_visible(False)
        return True

    def setup_menu_popover(self):
        popover = Gtk.Popover()
        menu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        menu_box.set_margin_top(12)
        menu_box.set_margin_bottom(12)
        menu_box.set_margin_start(12)
        menu_box.set_margin_end(12)
        popover.set_child(menu_box)
        lbl_opacity = Gtk.Label(label="Window Opacity")
        lbl_opacity.set_halign(Gtk.Align.START)
        menu_box.append(lbl_opacity)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.2, 1.0, 0.1)
        scale.set_value(self.settings.get("opacity", 1.0))
        scale.set_size_request(150, -1)
        scale.connect("value-changed", self.on_opacity_changed)
        menu_box.append(scale)
        menu_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        btn_prefs = Gtk.Button(label="Preferences")
        btn_prefs.add_css_class("flat")
        btn_prefs.set_halign(Gtk.Align.FILL)
        btn_prefs.connect("clicked", self.on_prefs_clicked)
        btn_prefs.connect("clicked", lambda x: popover.popdown()) 
        menu_box.append(btn_prefs)
        btn_shortcuts = Gtk.Button(label="Shortcuts")
        btn_shortcuts.add_css_class("flat")
        btn_shortcuts.set_halign(Gtk.Align.FILL)
        btn_shortcuts.connect("clicked", lambda x: self.show_shortcuts_window())
        btn_shortcuts.connect("clicked", lambda x: popover.popdown())
        menu_box.append(btn_shortcuts)
        
        btn_about = Gtk.Button(label="About DropShelf")
        btn_about.add_css_class("flat")
        btn_about.set_halign(Gtk.Align.FILL)
        btn_about.connect("clicked", self.show_about_window)
        btn_about.connect("clicked", lambda x: popover.popdown())
        menu_box.append(btn_about)
        menu_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        btn_quit = Gtk.Button(label="Quit")
        btn_quit.add_css_class("destructive-action") 
        btn_quit.set_halign(Gtk.Align.FILL)
        btn_quit.connect("clicked", lambda x: self.app.quit())
        menu_box.append(btn_quit)
        self.menu_btn.set_popover(popover)
    def on_opacity_changed(self, scale):
        val = scale.get_value()
        self.set_opacity(val)
        self.settings["opacity"] = val
        self.save_state()
    def show_about_window(self, btn):
        display = Gdk.Display.get_default()
        theme = Gtk.IconTheme.get_for_display(display)
        
        # Robust path fix:
        base_dir = os.path.dirname(os.path.realpath(__file__))
        icon_folder = os.path.join(base_dir, "gui")
        
        theme.add_search_path(icon_folder)
        about = Adw.AboutWindow(transient_for=self)
        about.set_application_name("DropShelf")
        about.set_application_icon("icon") 
        about.set_version("1.0")
        about.set_developer_name("Chandrahas Maddineni")
        about.set_comments("A transient drag-and-drop shelf")
        about.add_link("GitHub", "https://github.com/MChandrahas/DropShelf")
        about.set_copyright("© 2024 Chandrahas")
        about.present()
    def load_state(self):
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            items = data.get("items", [])
            for item_data in items:
                path = item_data.get('path')
                pinned = item_data.get('pinned', False)
                if path and os.path.exists(path):
                    self.store.append(FileItem(path, pinned))
            self.settings = data.get("settings", self.settings)
            self.set_opacity(self.settings.get("opacity", 1.0))
        except:
            pass

    def save_state(self):
        items_data = []
        for i in range(self.store.get_n_items()):
            item = self.store.get_item(i)
            items_data.append({"path": item.path, "filename": item.filename, "pinned": item.pinned})
        data = {"items": items_data, "settings": self.settings}
        try:
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except:
            pass

    def on_prefs_clicked(self, btn):
        prefs_window = Adw.PreferencesWindow(transient_for=self)
        prefs_window.set_default_size(500, 400)
        
        # Note: Using a separate controller here to avoid scope issues
        kc = Gtk.EventControllerKey()
        kc.connect("key-pressed", self.on_key_pressed)
        prefs_window.add_controller(kc)
        
        page = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")
        prefs_window.add(page)
        grp = Adw.PreferencesGroup(title="Behavior")
        page.add(grp)
        
        row_csv = Adw.SwitchRow(title="<b>Collect text as CSV</b>")
        row_csv.set_subtitle("Append text to 'collected.csv' instead of creating files")
        row_csv.set_active(self.settings.get("csv_mode", False))
        row_csv.connect("notify::active", lambda r,p: self.update_setting("csv_mode", r.get_active()))
        grp.add(row_csv)
        
        row_dl = Adw.SwitchRow(title="<b>Download images</b>")
        row_dl.set_subtitle("Automatically save dropped image URLs to cache.")
        row_dl.set_active(self.settings.get("download_images", True))
        row_dl.connect("notify::active", lambda r,p: self.update_setting("download_images", r.get_active()))
        grp.add(row_dl)
        
        grp_app = Adw.PreferencesGroup(title="Application")
        page.add(grp_app)
        
        row_shortcuts = Adw.ActionRow(title="<b>Keyboard Shortcuts</b>")
        row_shortcuts.set_subtitle("View hotkeys and commands")
        row_shortcuts.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row_shortcuts.set_activatable(True)
        row_shortcuts.connect("activated", lambda row: self.show_shortcuts_window())
        grp_app.add(row_shortcuts)
        
        grp_data = Adw.PreferencesGroup(title="Data Management")
        page.add(grp_data)
        
        btn_clear = Gtk.Button(label="Clear Cache")
        btn_clear.add_css_class("destructive-action")
        btn_clear.set_valign(Gtk.Align.CENTER)
        btn_clear.connect("clicked", self.clear_cache)
        
        row_clear = Adw.ActionRow(title="<b>Clear Cache and Reset</b>")
        row_clear.set_subtitle("Delete all data")
        row_clear.add_suffix(btn_clear)
        grp_data.add(row_clear)
        
        prefs_window.present()
    def clear_cache(self, btn):
        self.store.remove_all()
        if os.path.exists(self.cache_dir):
            try:
                shutil.rmtree(self.cache_dir)
            except:
                pass
        os.makedirs(self.cache_dir, exist_ok=True)
        self.save_state()
        btn.set_label("All Data Cleared!")
        GLib.timeout_add(2000, lambda: btn.set_label("Clear Cache") or False)


    def update_setting(self, key, val):
        self.settings[key] = val
        self.save_state()


    def update_setting(self, key, val):
        self.settings[key] = val
        self.save_state()

    def show_shortcuts_window(self):
        ui_str = """
        <interface>
          <object class="GtkShortcutsWindow" id="shortcuts_win">
            <property name="modal">True</property>
            <child>
              <object class="GtkShortcutsSection">
                <property name="section-name">main</property>
                <property name="max-height">12</property>
                <child>
                  <object class="GtkShortcutsGroup">
                    <property name="title">General</property>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="title">Show Shortcuts</property>
                        <property name="accelerator">&lt;Ctrl&gt;question</property> 
                      </object>
                    </child>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="title">Toggle Search</property>
                        <property name="accelerator">&lt;Ctrl&gt;f</property>
                      </object>
                    </child>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="title">Toggle Lock Mode</property>
                        <property name="accelerator">&lt;Ctrl&gt;d</property>
                      </object>
                    </child>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="title">Preview File</property>
                        <property name="accelerator">&lt;Ctrl&gt;p</property>
                      </object>
                    </child>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="title">Quit</property>
                        <property name="accelerator">&lt;Ctrl&gt;q</property>
                      </object>
                    </child>
                  </object>
                </child>
                <child>
                  <object class="GtkShortcutsGroup">
                    <property name="title">Editing</property>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="title">Delete Selected</property>
                        <property name="accelerator">BackSpace</property>
                      </object>
                    </child>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="title">Clear All</property>
                        <property name="accelerator">&lt;Shift&gt;Delete</property>
                      </object>
                    </child>
                  </object>
                </child>
                 <child>
                  <object class="GtkShortcutsGroup">
                    <property name="title">Mouse Actions</property>
                    <child>
                      <object class="GtkShortcutsShortcut">
                        <property name="title">Drag Single File</property>
                        <property name="subtitle">Hold key + Drag file</property>
                        <property name="accelerator">&lt;Ctrl&gt;</property>
                      </object>
                    </child>
                  </object>
                </child>
              </object>
            </child>
          </object>
        </interface>
        """
        builder = Gtk.Builder()
        builder.add_from_string(ui_str)
        win = builder.get_object("shortcuts_win")
        win.set_transient_for(self)
        win.present()
        
class DropShelfApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.dropshelf.app', flags=Gio.ApplicationFlags.FLAGS_NONE)
    
    def do_activate(self):
        # --- CUSTOM CSS ---
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            .red-icon { color: #ed333b; }
            .rounded-image { border-radius: 8px; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), 
            css_provider, 
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        # ------------------
        win = self.props.active_window
        if not win:
            win = DropShelfWindow(self)
            win.present()
        else:
            win.set_visible(True)
            win.present()

if __name__ == '__main__':
    app = DropShelfApp()
    app.run(sys.argv)
