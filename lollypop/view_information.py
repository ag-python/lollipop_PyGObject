# Copyright (c) 2014-2020 Cedric Bellegarde <cedric.bellegarde@adishatz.org>
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

from gi.repository import Gtk, GLib, Gio, Pango

from gettext import gettext as _
import re

from lollypop.define import App, ArtSize, ViewType, MARGIN, MARGIN_SMALL, Type
from lollypop.define import ARTISTS_PATH
from lollypop.objects_album import Album
from lollypop.helper_art import ArtBehaviour
from lollypop.information_store import InformationStore
from lollypop.view_albums_list import AlbumsListView
from lollypop.view import View
from lollypop.utils import set_cursor_type, get_network_available
from lollypop.utils import get_default_storage_type
from lollypop.helper_gestures import GesturesHelper


class ArtistRow(Gtk.ListBoxRow):
    """
        Artist row for Wikipedia
    """

    def __init__(self, item):
        """
            Init row
            @param item as (str, str, str)
        """
        Gtk.ListBoxRow.__init__(self)
        self.__locale = item[0]
        self.__page_id = item[2]
        label = Gtk.Label.new("%s: %s" % (item[0], item[1]))
        label.set_property("halign", Gtk.Align.START)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.get_style_context().add_class("padding")
        label.show()
        self.add(label)

    @property
    def locale(self):
        """
            Get locale
            @return str
        """
        return self.__locale

    @property
    def page_id(self):
        """
            Get page id
            @return str
        """
        return self.__page_id


class InformationView(View):
    """
        View with artist information
    """

    def __init__(self, view_type, minimal=False):
        """
            Init artist infos
            @param view_type as ViewType
            @param minimal as bool
        """
        View.__init__(self, get_default_storage_type(), view_type)
        self.__information_store = InformationStore()
        self.__cancellable = Gio.Cancellable()
        self.__minimal = minimal
        self.__artist_name = ""

    def populate(self, artist_id=None):
        """
            Show information for artists
            @param artist_id as int
        """
        builder = Gtk.Builder()
        builder.add_from_resource(
            "/org/gnome/Lollypop/ArtistInformation.ui")
        builder.connect_signals(self)
        self.__scrolled = builder.get_object("scrolled")
        widget = builder.get_object("widget")
        self.add(widget)
        self.__stack = builder.get_object("stack")
        self.__listbox = builder.get_object("listbox")
        self.__artist_label = builder.get_object("artist_label")
        title_label = builder.get_object("title_label")
        self.__artist_artwork = builder.get_object("artist_artwork")
        bio_eventbox = builder.get_object("bio_eventbox")
        artist_label_eventbox = builder.get_object("artist_label_eventbox")
        bio_eventbox.connect("realize", set_cursor_type)
        artist_label_eventbox.connect("realize", set_cursor_type)
        self.__gesture1 = GesturesHelper(
            bio_eventbox,
            primary_press_callback=self._on_info_label_press)
        self.__gesture2 = GesturesHelper(
            artist_label_eventbox,
            primary_press_callback=self._on_artist_label_press)
        self.__bio_label = builder.get_object("bio_label")
        if artist_id is None and App().player.current_track.id is not None:
            builder.get_object("header").show()
            if App().player.current_track.album.artist_ids[0] ==\
                    Type.COMPILATIONS:
                artist_id = App().player.current_track.artist_ids[0]
            else:
                artist_id = App().player.current_track.album.artist_ids[0]
            title_label.set_text(App().player.current_track.title)
        self.__artist_name = App().artists.get_name(artist_id)
        if self.__minimal:
            self.__bio_label.set_margin_start(MARGIN)
            self.__bio_label.set_margin_end(MARGIN)
            self.__bio_label.set_margin_top(MARGIN)
            self.__bio_label.set_margin_bottom(MARGIN)
            self.__artist_artwork.hide()
        else:
            self.__artist_artwork.set_margin_start(MARGIN_SMALL)
            builder.get_object("header").show()
            self.__artist_label.set_text(self.__artist_name)
            self.__artist_label.show()
            title_label.show()
            App().art_helper.set_artist_artwork(
                                    self.__artist_name,
                                    ArtSize.SMALL * 3,
                                    ArtSize.SMALL * 3,
                                    self.__artist_artwork.get_scale_factor(),
                                    ArtBehaviour.ROUNDED |
                                    ArtBehaviour.CROP_SQUARE |
                                    ArtBehaviour.CACHE,
                                    self.__on_artist_artwork)
            albums_view = AlbumsListView([], [],
                                         ViewType.SCROLLED)
            albums_view.set_size_request(300, -1)
            albums_view.show()
            albums_view.set_margin_start(5)
            albums_view.add_widget(albums_view.box)
            widget.attach(albums_view, 2, 1, 1, 2)
            albums = []
            storage_type = get_default_storage_type()
            for album_id in App().albums.get_ids([], [artist_id],
                                                 storage_type, True):
                albums.append(Album(album_id))
            if not albums:
                albums = [App().player.current_track.album]
            albums_view.populate(albums)
        content = self.__information_store.get_information(self.__artist_name,
                                                           ARTISTS_PATH)
        if content is None:
            self.__bio_label.set_text(_("Loading information"))
            from lollypop.information_downloader import InformationDownloader
            downloader = InformationDownloader()
            downloader.get_information(self.__artist_name,
                                       self.__on_artist_information,
                                       self.__artist_name)
        else:
            App().task_helper.run(self.__to_markup, content,
                                  callback=(self.__bio_label.set_markup,))

#######################
# PROTECTED           #
#######################
    def _on_unmap(self, widget):
        """
            Cancel operations
            @param widget as Gtk.Widget
        """
        self.__cancellable.cancel()

    def _on_previous_button_clicked(self, button):
        """
            Go back to main view
            @param button as Gtk.Button
        """
        self.__stack.set_visible_child_name("main")

    def _on_artist_label_press(self, x, y, event):
        """
            Go to artist view
            @param x as int
            @param y as int
            @param event as Gdk.Event
        """
        popover = self.get_ancestor(Gtk.Popover)
        if popover is not None:
            popover.popdown()
        if App().player.current_track.id is None:
            return
        GLib.idle_add(App().window.container.show_view,
                      [Type.ARTISTS],
                      App().player.current_track.album.artist_ids)

    def _on_info_label_press(self, x, y, event):
        """
            Show information cache (for edition)
            @param x as int
            @param y as int
            @param event as Gdk.Event
        """
        if get_network_available("WIKIPEDIA"):
            from lollypop.wikipedia import Wikipedia
            wikipedia = Wikipedia()
            self.__stack.set_visible_child_name("select")
            App().task_helper.run(wikipedia.get_search_list,
                                  self.__artist_name,
                                  callback=(self.__on_wikipedia_search_list,))

    def _on_row_activated(self, listbox, row):
        """
            Update artist information
            @param listbox as Gtk.ListBox
            @param row as Gtk.ListBoxRow
        """
        self.__stack.set_visible_child_name("main")
        from lollypop.wikipedia import Wikipedia
        wikipedia = Wikipedia()
        App().task_helper.run(wikipedia.get_content_for_page_id,
                              row.page_id, row.locale,
                              callback=(self.__on_wikipedia_get_content,))

#######################
# PRIVATE             #
#######################
    def __to_markup(self, data):
        """
            Transform message to markup
            @param data as bytes
            @return str
        """
        pango = ["large", "x-large", "xx-large"]
        start = ["^===*", "^==", "^="]
        end = ["===*$", "==$", "=$"]
        i = 0
        text = GLib.markup_escape_text(data.decode("utf-8"))
        while i < len(pango):
            text = re.sub(start[i], "<b><span size='%s'>" % pango[i],
                          text, flags=re.M)
            text = re.sub(end[i], "</span></b>", text, flags=re.M)
            i += 1
        return text

    def __on_wikipedia_search_list(self, items):
        """
            Populate view with items
            @param items as [(str, str)]
        """
        for item in items:
            row = ArtistRow(item)
            row.show()
            self.__listbox.add(row)

    def __on_wikipedia_get_content(self, content):
        """
            Update label and save to cache
            @param content as str
        """
        if content is not None:
            App().task_helper.run(self.__to_markup, content,
                                  callback=(self.__bio_label.set_markup,))
            self.__information_store.save_information(
                self.__artist_name, ARTISTS_PATH, content)

    def __on_artist_artwork(self, surface):
        """
            Finish widget initialisation
            @param surface as cairo.Surface
        """
        if surface is None:
            self.__artist_artwork.hide()
        else:
            self.__artist_artwork.set_from_surface(surface)
            del surface

    def __on_artist_information(self, content, artist_name):
        """
            Set label
            @param content as bytes
            @param artist_name as str
        """
        if artist_name != self.__artist_name:
            return
        if content is None:
            self.__bio_label.set_text(
                _("No information for %s") % self.__artist_name)
        else:
            App().task_helper.run(self.__to_markup, content,
                                  callback=(self.__bio_label.set_markup,))
            self.__information_store.save_information(self.__artist_name,
                                                      ARTISTS_PATH,
                                                      content)
