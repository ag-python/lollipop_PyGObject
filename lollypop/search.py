# Copyright (c) 2014-2017 Cedric Bellegarde <cedric.bellegarde@adishatz.org>
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

from lollypop.define import Lp
from lollypop.helper_task import TaskHelper
from lollypop.objects import Album, Track


class Search:
    """
        Local search
    """

    def __init__(self):
        """
            Init search
        """
        pass

    def get(self, search_items, cancellable, callback):
        """
            Get track for name
            @param search_items as [str]
            @param cancellable as Gio.Cancellable
            @param callback as callback
        """
        helper = TaskHelper()
        helper.run(self.__get, search_items, cancellable, callback=callback)

#######################
# PRIVATE             #
#######################
    def __get(self, search_items, cancellable):
        """
            Get track for name
            @param search_items as [str]
            @param cancellable as Gio.Cancellable
            @return items as [SearchItem]
        """
        album_ids = []
        track_ids = []
        albums = []
        for item in search_items:
            if cancellable.is_cancelled():
                return
            # Get all albums for all artists and non album_artist tracks
            for artist_id in Lp().artists.search(item):
                if cancellable.is_cancelled():
                    return
                for album_id in Lp().albums.get_ids([artist_id], []):
                    if (album_id, artist_id) not in albums:
                        album_ids.append(album_id)
                for track_id in Lp().tracks.get_for_artist(artist_id):
                    track_ids.append(track_id)
            try:
                year = int(item)
                album_ids += Lp().albums.get_by_year(year)
            except:
                pass
            album_ids += Lp().albums.search(item)
            for track_id in Lp().tracks.search(item):
                track_ids.append(track_id)

        # Create albums for album_ids
        for album_id in list(set(album_ids)):
            album = Album(album_id)
            if album.name.lower() in search_items:
                album.inc_score(1)
            for artist in album.artists:
                if artist.lower() in search_items:
                    album.inc_score(1)
            albums.append(album)
        # Create albums for tracks
        album_tracks = {}
        for track_id in list(set(track_ids)):
            track = Track(track_id)
            if track.album.id not in album_ids:
                album = track.album
                if album.id in album_tracks.keys():
                    (album, tracks) = album_tracks[album.id]
                    tracks.append(track)
                else:
                    album_tracks[track.album.id] = (album, [track])
                if track.name.lower() in search_items:
                    album.inc_score(2)
                else:
                    album.inc_score(1)
        for key in album_tracks.keys():
            (album, tracks) = album_tracks[key]
            album.set_tracks(tracks)
            albums.append(album)
        return albums
