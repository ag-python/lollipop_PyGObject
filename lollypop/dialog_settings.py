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

from gi.repository import Gtk, GLib, Handy

from gettext import gettext as _

from lollypop.define import App, MARGIN_SMALL, ScanType, NetworkAccessACL
from lollypop.widgets_row_device import DeviceRow


class SettingsDialog:
    """
        Dialog showing lollypop settings
    """

    __BOOLEAN = ["dark-ui", "artist-artwork", "auto-update", "background-mode",
                 "save-state", "import-playlists", "save-to-tags",
                 "show-compilations", "transitions", "network-access"]

    __RANGE = ["cover-size", "transitions-duration"]

    __COMBO = ["replay-gain", "orderby"]

    def __init__(self):
        """
            Init dialog
        """
        self.__timeout_id = None
        self.__choosers = []
        builder = Gtk.Builder()
        builder.add_from_resource("/org/gnome/Lollypop/SettingsDialog.ui")
        self.__settings_dialog = builder.get_object("settings_dialog")
        for setting in self.__BOOLEAN:
            button = builder.get_object("%s_boolean" % setting)
            value = App().settings.get_value(setting)
            button.set_state(value)
        for setting in self.__RANGE:
            widget = builder.get_object("%s_range" % setting)
            value = App().settings.get_value(setting).get_int32()
            widget.set_value(value)
        for setting in self.__COMBO:
            widget = builder.get_object("%s_combo" % setting)
            value = App().settings.get_enum(setting)
            widget.set_active(value)
        builder.connect_signals(self)
        self.__music_group = builder.get_object("music_group")
        button = Gtk.Button.new_with_label(_("Add a new folder"))
        button.show()
        button.set_margin_top(MARGIN_SMALL)
        button.set_halign(Gtk.Align.CENTER)
        button.connect("clicked", self.__on_new_button_clicked)
        self.__music_group.add(button)
        for uri in App().settings.get_value("music-uris"):
            button = self.__get_new_chooser(uri)
            self.__music_group.add(button)
        for device in App().settings.get_value("devices"):
            row = DeviceRow(device)
            builder.get_object("device_group").add(row)
        acl = App().settings.get_value("network-access-acl").get_int32()
        for key in NetworkAccessACL.keys():
            if acl & NetworkAccessACL[key]:
                builder.get_object("%s_button" % key).set_state(True)
        artists_count = App().artists.count()
        albums_count = App().albums.count()
        tracks_count = App().tracks.count()
        builder.get_object("stat_artists").set_title(
            _("Artists count: %s") % artists_count)
        builder.get_object("stat_albums").set_title(
            _("Albums count: %s") % albums_count)
        builder.get_object("stat_tracks").set_title(
            _("Tracks count: %s") % tracks_count)

        self.__settings_dialog.connect("destroy", self.__on_destroy)

    def show(self):
        """
            Show dialog
        """
        self.__settings_dialog.show()

#######################
# PROTECTED           #
#######################
    def _on_boolean_state_set(self, widget, state):
        """
            Save setting
            @param widget as Gtk.Switch
            @param state as bool
        """
        setting = widget.get_name()
        App().settings.set_value(setting,
                                 GLib.Variant("b", state))
        if setting == "dark-ui":
            if not App().player.is_party:
                settings = Gtk.Settings.get_default()
                settings.set_property("gtk-application-prefer-dark-theme",
                                      state)
        elif setting == "artist-artwork":
            print("coucou")
            App().window.container.reload_view()

    def _on_range_changed(self, widget):
        """
            Save value
            @param widget as Gtk.Range
        """
        setting = widget.get_name()
        value = widget.get_value()
        App().settings.set_value(setting, GLib.Variant("i", value))
        if setting == "cover-size":
            if self.__timeout_id is not None:
                GLib.source_remove(self.__timeout_id)
            self.__timeout_id = GLib.timeout_add(500,
                                                 self.__update_coversize,
                                                 widget)

    def _on_combo_changed(self, widget):
        """
            Save value
            @param widget as Gtk.ComboBoxText
        """
        setting = widget.get_name()
        value = widget.get_active()
        App().settings.set_enum(setting, value)

    def _on_clean_artwork_cache_clicked(self, button):
        """
            Clean artwork cache
            @param button as Gtk.Button
        """
        App().task_helper.run(App().art.clean_all_cache)
        button.set_sensitive(False)

    def _on_acl_state_set(self, widget, state):
        """
            Save network acl state
            @param widget as Gtk.Switch
            @param state as bool
        """
        key = widget.get_name()
        acl = App().settings.get_value("network-access-acl").get_int32()
        if state:
            acl |= NetworkAccessACL[key]
        else:
            acl &= ~NetworkAccessACL[key]
        acl = App().settings.set_value("network-access-acl",
                                       GLib.Variant("i", acl))

#######################
# PRIVATE             #
#######################
    def __on_new_button_clicked(self, button):
        """
            Add a new chooser
            @param button as Gtk.Button
        """
        button = self.__get_new_chooser(None)
        self.__music_group.add(button)

    def __get_new_chooser(self, uri):
        """
            Get a new chooser
            @param uri as str
            @return Handy.ActionRow
        """
        chooser = Gtk.FileChooserButton()
        chooser.show()
        chooser.set_local_only(False)
        chooser.set_action(Gtk.FileChooserAction.SELECT_FOLDER)
        chooser.set_valign(Gtk.Align.CENTER)
        chooser.set_hexpand(True)
        self.__choosers.append(chooser)
        if uri is not None:
            chooser.set_uri(uri)
        button = Gtk.Button.new_from_icon_name("list-remove-symbolic",
                                               Gtk.IconSize.BUTTON)
        button.show()
        button.set_valign(Gtk.Align.CENTER)
        row = Handy.ActionRow()
        row.show()
        row.add(chooser)
        row.add(button)
        button.connect("clicked", lambda x: self.__choosers.remove(chooser))
        button.connect("clicked", lambda x: row.destroy())
        return row

    def __update_coversize(self, widget):
        """
            Update cover size
            @param widget as Gtk.Range
        """
        self.__timeout_id = None
        App().task_helper.run(App().art.clean_all_cache)
        App().art.update_art_size()
        App().window.container.reload_view()

    def __on_destroy(self, widget):
        """
            Save settings and update if needed
            @param widget as Gtk.Window
        """
        # Music uris
        uris = []
        default = GLib.get_user_special_dir(
            GLib.UserDirectory.DIRECTORY_MUSIC)
        if default is not None:
            default = GLib.filename_to_uri(default)
        else:
            default = None
        for chooser in self.__choosers:
            uri = chooser.get_uri()
            if uri is not None and uri not in uris:
                uris.append(uri)
        if not uris:
            uris.append(default)

        previous = App().settings.get_value("music-uris")
        App().settings.set_value("music-uris", GLib.Variant("as", uris))

        if set(previous) != set(uris):
            to_delete = [uri for uri in previous if uri not in uris]
            to_scan = [uri for uri in uris if uri not in previous]
            if to_delete:
                App().scanner.update(ScanType.FULL)
            elif to_scan:
                App().scanner.update(ScanType.NEW_FILES, to_scan)
