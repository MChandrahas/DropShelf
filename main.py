import sys
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio

class DropShelfWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="DropShelf")
        self.set_default_size(500, 400)

        # 1. Main Container: ToolbarView
        # This manages the top bar and the content below it automatically
        self.toolbar_view = Adw.ToolbarView()
        self.set_content(self.toolbar_view)

        # 2. Top Bar: HeaderBar
        # This is the title bar with window controls (X, -, [])
        self.header_bar = Adw.HeaderBar()
        self.toolbar_view.add_top_bar(self.header_bar)

        # 3. Main Content Area: A Placeholder Box
        # We will put the Drag-and-Drop list here later
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content_box.set_valign(Gtk.Align.CENTER)
        self.content_box.set_halign(Gtk.Align.CENTER)
        
        # Add a placeholder icon and text
        icon = Gtk.Image.new_from_icon_name("folder-drag-accept-symbolic")
        icon.set_pixel_size(64)
        
        label = Gtk.Label(label="Drop Files Here")
        label.add_css_class("title-1") # Make text big
        
        self.content_box.append(icon)
        self.content_box.append(label)

        # Add the content box to the ToolbarView
        self.toolbar_view.set_content(self.content_box)

class DropShelfApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.dropshelf.app',
                         flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        # We keep the window logic separate in the class above
        win = self.props.active_window
        if not win:
            win = DropShelfWindow(self)
        win.present()

if __name__ == '__main__':
    app = DropShelfApp()
    app.run(sys.argv)
