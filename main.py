import sys
import gi

# Require GTK 4.0 and LibAdwaita 1
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw

class DropShelfApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.dropshelf.app',
                         flags=0)

    def do_activate(self):
        win = Adw.ApplicationWindow(application=self)
        win.set_title("DropShelf")
        win.set_default_size(400, 300)
        
        # Add a simple label so we know it's working
        label = Gtk.Label(label="DropShelf is Alive!")
        win.set_content(label)
        
        win.present()

if __name__ == '__main__':
    app = DropShelfApp()
    app.run(sys.argv)
