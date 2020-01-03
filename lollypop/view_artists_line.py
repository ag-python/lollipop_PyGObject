# Copyright (c) 2014-2019 Cedric Bellegarde <cedric.bellegarde@adishatz.org>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

from gi.repository import Gtk, Pango, GLib

from gettext import gettext as _

from lollypop.define import App, MARGIN, ViewType
from lollypop.helper_horizontal_scrolling import HorizontalScrollingHelper
from lollypop.view_artists_rounded import RoundedArtistsView


class ArtistsLineView(RoundedArtistsView, HorizontalScrollingHelper):
    """
        Show artist in an horizontal flowbox
    """

    def __init__(self, view_type):
        """
            Init artist view
            @param view_type as ViewType
        """
        RoundedArtistsView.__init__(self, view_type)
        self.connect("map", self.__on_map)
        self.set_row_spacing(5)
        self._label = Gtk.Label.new()
        self._label.set_ellipsize(Pango.EllipsizeMode.END)
        self._label.get_style_context().add_class("dim-label")
        self.__update_label(App().window.is_adaptive)
        self._label.set_hexpand(True)
        self._label.set_property("halign", Gtk.Align.START)
        self._backward_button = Gtk.Button.new_from_icon_name(
                                                    "go-previous-symbolic",
                                                    Gtk.IconSize.BUTTON)
        self._forward_button = Gtk.Button.new_from_icon_name(
                                                   "go-next-symbolic",
                                                   Gtk.IconSize.BUTTON)
        self._backward_button.get_style_context().add_class("menu-button")
        self._forward_button.get_style_context().add_class("menu-button")
        header = Gtk.Grid()
        header.set_column_spacing(10)
        header.add(self._label)
        header.add(self._backward_button)
        header.add(self._forward_button)
        header.set_margin_end(MARGIN)
        header.show_all()
        HorizontalScrollingHelper.__init__(self)
        self.add(header)
        self._label.set_property("halign", Gtk.Align.START)
        self.add_widget(self._box)

    @property
    def args(self):
        return None

#######################
# PROTECTED           #
#######################
    def _on_adaptive_changed(self, window, status):
        """
            Update label
            @param window as Window
            @param status as bool
        """
        RoundedArtistsView._on_adaptive_changed(self, window, status)
        self.__update_label(status)

    def _on_populated(self, widget):
        """
            Update button state
            @param widget as Gtk.Widget
        """
        RoundedArtistsView._on_populated(self, widget)
        if self.is_populated:
            self._update_buttons()

    def _on_artist_updated(self, scanner, artist_id, add):
        pass

#######################
# PRIVATE             #
#######################
    def __update_label(self, is_adaptive):
        """
            Update label style based on current adaptive state
            @param is_adaptive as bool
        """
        style_context = self._label.get_style_context()
        if is_adaptive:
            style_context.remove_class("text-x-large")
        else:
            style_context.add_class("text-x-large")

    def __on_map(self, widget):
        """
            Update buttons state
        """
        if self.is_populated:
            self._update_buttons()


class ArtistsRandomLineView(ArtistsLineView):
    """
        Line view showing 6 random artists
    """
    def __init__(self, view_type):
        """
            Init artist view
            @param view_type as ViewType
        """
        ArtistsLineView.__init__(self, view_type)
        self._label.set_text(_("Why not listen to?"))

    def populate(self):
        """
            Populate view
        """
        def on_load(items):
            self._box.set_min_children_per_line(len(items))
            ArtistsLineView.populate(self, items)
            if items:
                self.show()

        def load():
            ids = App().artists.get_randoms(15)
            return ids

        App().task_helper.run(load, callback=(on_load,))


class ArtistsSearchLineView(ArtistsLineView):
    """
        Line view for search
    """
    def __init__(self):
        """
            Init artist view
        """
        ArtistsLineView.__init__(self, ViewType.SEARCH | ViewType.SCROLLED)
        self._label.set_text(_("Artists"))

    def add_value(self, item_id):
        """
            Insert item
            @param item_id as int
        """
        ArtistsLineView.populate(self, [item_id])
        self._box.set_min_children_per_line(len(self._box.get_children()))

    def clear(self):
        """
            Clear and hide the view
        """
        ArtistsLineView.clear(self)
        GLib.idle_add(self.hide)
