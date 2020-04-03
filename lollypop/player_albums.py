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

from gi.repository import GLib

from random import choice

from lollypop.logger import Logger
from lollypop.objects_album import Album
from lollypop.player_auto_similar import AutoSimilarPlayer
from lollypop.player_auto_random import AutoRandomPlayer
from lollypop.define import App, Repeat
from lollypop.utils import emit_signal


class AlbumsPlayer:
    """
        Handle player albums
    """

    def __init__(self):
        """
            Init player
        """
        # Albums in current playlist
        self._albums = []

    def add_album(self, album):
        """
            Add album to player
            @param album as Album
        """
        self.add_albums([album])

    def add_album_ids(self, album_ids):
        """
            Add album ids to player
            @param album_ids as [int]
        """
        self.add_albums([Album(album_id) for album_id in album_ids])

    def add_albums(self, albums):
        """
            Add albums to player
            @param albums as [Album]
        """
        try:
            for album in albums:
                # Merge album if previous is same
                if self._albums and self._albums[-1].id == album.id:
                    tracks = list(set(self._albums[-1].tracks) |
                                  set(album.tracks))
                    self._albums[-1].set_tracks(tracks)
                    emit_signal(self, "playback-updated", album)
                else:
                    self._albums.append(album)
                    emit_signal(self, "playback-added", album)
            self.update_next_prev()
        except Exception as e:
            Logger.error("Player::add_albums(): %s" % e)

    def remove_album(self, album):
        """
            Remove album from albums
            @param album as Album
        """
        try:
            if album not in self._albums:
                return
            if self._current_track.album == album:
                self.skip_album()
            self._albums.remove(album)
            self.update_next_prev()
            emit_signal(self, "playback-removed", album)
        except Exception as e:
            Logger.error("Player::remove_album(): %s" % e)

    def remove_album_by_id(self, album_id):
        """
            Remove all instances of album id
            @param album_id as int
        """
        self.remove_album_by_ids([album_id])

    def remove_album_by_ids(self, album_ids):
        """
            Remove all instances of album ids
            @param album_ids as [int]
        """
        try:
            for album_id in album_ids:
                for album in self._albums:
                    if album.id == album_id:
                        self.remove_album(album)
                        emit_signal(self, "playback-removed", album)
            self.update_next_prev()
        except Exception as e:
            Logger.error("Player::remove_album_by_ids(): %s" % e)

    def remove_track_from_album(self, track, album):
        """
            Remove track from album
            @param track as Track
            @param album as Album
        """
        is_current_track = track == self.current_track
        if is_current_track:
            self.next()
        if album.remove_track(track):
            self.remove_album(album)
            emit_signal(self, "playback-removed", album)
        else:
            emit_signal(self, "playback-updated", album)
            if not is_current_track:
                self.update_next_prev()

    def play_album(self, album):
        """
            Play album
            @param album as Album
        """
        self.play_album_for_albums(album, [album])

    def play_track_for_albums(self, track, albums):
        """
            Play track and set albums as current playlist
            @param albums as [Album]
            @param track as Track
        """
        if self.is_party:
            App().lookup_action("party").change_state(GLib.Variant("b", False))
        self._albums = albums
        self.load(track)
        for album in albums:
            emit_signal(self, "playback-added", album)

    def play_album_for_albums(self, album, albums):
        """
            Play album and set albums as current playlist
            @param album as Album
            @param albums as [Album]
        """
        if self.is_party:
            App().lookup_action("party").change_state(GLib.Variant("b", False))
        for _album in self._albums:
            emit_signal(self, "playback-removed", _album)
        if App().settings.get_value("shuffle"):
            self.__play_shuffle_tracks(album, albums)
        else:
            self.__play_albums(album, albums)
        for _album in albums:
            emit_signal(self, "playback-added", _album)

    def play_albums(self, albums):
        """
            Play albums
            @param album as [Album]
        """
        if not albums:
            return
        if App().settings.get_value("shuffle"):
            album = choice(albums)
        else:
            album = albums[0]
        self.play_album_for_albums(album, albums)

    def set_albums(self, albums):
        """
            Set player albums
        """
        self._albums = albums
        self.update_next_prev()

    def clear_albums(self):
        """
            Clear all albums
        """
        for album in self._albums:
            emit_signal(self, "playback-removed", album)
        self._albums = []
        self.update_next_prev()

    def skip_album(self):
        """
            Skip current album
        """
        try:
            # In party or shuffle, just update next track
            if self.is_party or App().settings.get_value("shuffle"):
                self.set_next()
                # We send this signal to update next popover
                emit_signal(self, "queue-changed")
            elif self._current_track.id is not None:
                index = self._albums.index(
                    self._current_playback_track.album)
                if index + 1 >= len(self._albums):
                    repeat = App().settings.get_enum("repeat")
                    if repeat == Repeat.AUTO_SIMILAR:
                        next_album = AutoSimilarPlayer.next_album(self)
                        if next_album is not None:
                            self.add_album(next_album)
                    elif repeat == Repeat.AUTO_RANDOM:
                        next_album = AutoRandomPlayer.next_album(self)
                        if next_album is not None:
                            self.add_album(next_album)
                    elif repeat == Repeat.ALL:
                        next_album = self._albums[0]
                    else:
                        self.stop()
                else:
                    next_album = self._albums[index + 1]
                self.load(next_album.tracks[0])
        except Exception as e:
            Logger.error("Player::skip_album(): %s" % e)

    def track_in_playback(self, track):
        """
            True if track present in current playback
            @param track as Track
            @return bool
        """
        for album in self._albums:
            if album.id == track.album.id:
                for track_id in album.track_ids:
                    if track.id == track_id:
                        return True
        return False

    def get_albums_for_id(self, album_id):
        """
            Get albums for id
            @param album_id as int
            @return [Album]
        """
        return [album for album in self._albums if album.id == album_id]

    @property
    def albums(self):
        """
            Return albums
            @return albums as [Album]
        """
        return list(self._albums)

    @property
    def album_ids(self):
        """
            Return albums ids
            @return albums ids as [int]
        """
        return [album.id for album in self._albums]

#######################
# PRIVATE             #
#######################
    def __play_shuffle_tracks(self, album, albums):
        """
            Start shuffle tracks playback.
            @param album as Album
            @param albums as [albums]
        """
        if album is None:
            album = choice(albums)
        if album.tracks:
            track = choice(album.tracks)
        else:
            track = None
        self._albums = albums
        if track is not None:
            self.load(track)
        else:
            self.update_next_prev()

    def __play_albums(self, album, albums):
        """
            Start albums playback.
            @param album as Album
            @param albums as [albums]
        """
        if album is None:
            album = albums[0]
        if album.tracks:
            track = album.tracks[0]
        else:
            track = None
        self._albums = albums
        if track is not None:
            self.load(track)
        else:
            self.update_next_prev()
