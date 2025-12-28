import sys
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio, Gdk

class DropShelfWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="DropShelf")
        self.set_default_size(500, 400)

        # 1. Main Layout
        self.toolbar_view = Adw.ToolbarView()
        self.set_content(self.toolbar_view)

        self.header_bar = Adw.HeaderBar()
        self.toolbar_view.add_top_bar(self.header_bar)

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content_box.set_valign(Gtk.Align.CENTER)
        self.content_box.set_halign(Gtk.Align.CENTER)
        
        # 2. UI Elements
        self.status_icon = Gtk.Image.new_from_icon_name("folder-drag-accept-symbolic")
        self.status_icon.set_pixel_size(64)
        
        self.status_label = Gtk.Label(label="Drop Files Here")
        self.status_label.add_css_class("title-1")
        
        self.content_box.append(self.status_icon)
        self.content_box.append(self.status_label)
        
        self.toolbar_view.set_content(self.content_box)

        # 3. Enable Drag and Drop
        self.setup_drop_target()

    def setup_drop_target(self):
        # We create a target that accepts a FileList (multiple files)
        # We allow the "COPY" action
        target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        
        # Connect the "drop" signal to our function
        target.connect("drop", self.on_file_drop)
        
        # Add the target to the whole window content
        self.toolbar_view.add_controller(target)

    def on_file_drop(self, target, file_list, x, y):
        # This triggers when you release the mouse
        print(f"--- DROP DETECTED! ---")
        
        # Get the files from the Gdk.FileList object
        files = file_list.get_files()
        
        for file_obj in files:
            # Get the path on disk
            path = file_obj.get_path()
            print(f"Received: {path}")
            
        # Update the UI text to prove it worked
        self.status_label.set_label(f"Received {len(files)} files!")
        
        # Return True to tell the system the drop succeeded
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
