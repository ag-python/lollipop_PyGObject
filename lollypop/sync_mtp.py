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

from gi.repository import GLib, Gio, Gst, GObject

from time import sleep
from re import match
import json

from lollypop.logger import Logger
from lollypop.utils import escape
from lollypop.define import App, Type
from lollypop.objects import Track, Album


class MtpSyncDb:
    """
        Synchronisation db stored on MTP device

        Some MTP devices for instance cannot properly store / retrieve file
        modification times, so we store them in a dedicated file at the root
        of the MTP device instead.

        The storage format is a simple JSON dump.
        It also implements the context manager interface, ensuring database is
        loaded before entering the scope and saving it when exiting.
    """

    def __init__(self):
        """
            Constructor for MtpSyncDb
        """
        self.__encoder = "convert_none"
        self.__normalize = False
        self.__metadata = {}

    def load(self, base_uri):
        """
            Loads the metadata db from the MTP device
            @param base_uri as str
        """
        self.__base_uri = base_uri
        self.__db_uri = self.__base_uri + "/lollypop-sync.db"
        Logger.debug("MtpSyncDb::__load_db()")
        try:
            dbfile = Gio.File.new_for_uri(self.__db_uri)
            (status, jsonraw, tags) = dbfile.load_contents(None)
            if status:
                jsondb = json.loads(jsonraw.decode("utf-8"))
                if "encoder" in jsondb:
                    self.__encoder = jsondb["encoder"]
                if "normalize" in jsondb:
                    self.__normalize = jsondb["normalize"]
                if "version" in jsondb and jsondb["version"] == 1:
                    for m in jsondb["tracks_metadata"]:
                        self.__metadata[m["uri"]] = m["metadata"]
                else:
                    Logger.info("MtpSyncDb::__load_db():"
                                " unknown sync db version")
        except Exception as e:
            Logger.error("MtpSyncDb::load(): %s" % e)

    def save(self):
        """
            Saves the metadata db to the MTP device
        """
        try:
            Logger.debug("MtpSyncDb::__save()")
            jsondb = json.dumps(
                            {"version": 1,
                             "encoder": self.__encoder,
                             "normalize": self.__normalize,
                             "tracks_metadata": [
                                 {"uri": x, "metadata": y}
                                 for x, y in sorted(self.__metadata.items())]})
            dbfile = Gio.File.new_for_uri(self.__db_uri)
            (tmpfile, stream) = Gio.File.new_tmp()
            stream.get_output_stream().write_all(jsondb.encode("utf-8"))
            tmpfile.copy(dbfile, Gio.FileCopyFlags.OVERWRITE, None, None)
            stream.close()
        except Exception as e:
            Logger.error("MtpSyncDb::__save(): %s", e)

    def set_encoder(self, encoder):
        """
            Set encoder
            @param encoder as str
        """
        self.__encoder = encoder

    def set_normalize(self, normalize):
        """
            Set normalize
            @param normalize as bool
        """
        self.__normalize = normalize

    def get_mtime(self, uri):
        """
            Get mtime for a uri on MTP device from the metadata db
            @param uri as str
        """
        return self.__metadata.get(
            self.__get_reluri(uri), {}).get("time::modified", 0)

    def set_mtime(self, uri, mtime):
        """
            Set mtime for a uri on MTP device from the metadata db
            @param uri as str
            @param mtime as int
        """
        self.__metadata.setdefault(self.__get_reluri(uri),
                                   dict())["time::modified"] = mtime

    def delete_uri(self, uri):
        """
            Deletes metadata for a uri from the on-device metadata db
            @param uri as str
        """
        if self.__get_reluri(uri) in self.__metadata:
            del self.__metadata[self.__get_reluri(uri)]

    @property
    def encoder(self):
        """
            Get encoder
            @return str
        """
        return self.__encoder

    @property
    def normalize(self):
        """
            Get normalize
            @return bool
        """
        return self.__normalize

############
# Private  #
############
    def __get_reluri(self, uri):
        """
            Returns a relative on-device uri from an absolute on-device.
            We do not want to store absolute uri in the db as the same
            peripheral could have a different path when mounted on another host
            machine.
            @param uri as str
        """
        if uri.startswith(self.__base_uri):
            uri = uri[len(self.__base_uri) + 1:]
        return uri


class MtpSync(GObject.Object):
    """
        Synchronisation to MTP devices
    """
    __gsignals__ = {
        "sync-progress": (GObject.SignalFlags.RUN_FIRST, None, (float,)),
        "sync-finished": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "sync-errors": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    __ENCODE_START = 'filesrc location="%s" ! decodebin\
                            ! audioconvert\
                            ! audioresample\
                            ! audio/x-raw,rate=44100,channels=2'
    __ENCODE_END = ' ! filesink location="%s"'
    __NORMALIZE = " ! rgvolume pre-amp=6.0 headroom=10.0\
                    ! rglimiter ! audioconvert"
    __EXTENSION = {"convert_none": None,
                   "convert_mp3": ".mp3",
                   "convert_vorbis": ".ogg",
                   "convert_flac": ".flac",
                   "convert_aac": ".m4a"}
    __ENCODERS = {"convert_none": None,
                  "convert_mp3": " ! lamemp3enc target=bitrate\
                                   cbr=true bitrate=%s ! id3v2mux",
                  "convert_vorbis": " ! vorbisenc max-bitrate=%s\
                                      ! oggmux",
                  "convert_flac": " ! flacenc",
                  "convert_aac": " ! faac bitrate=%s ! mp4mux"}
    _GST_ENCODER = {"convert_mp3": "lamemp3enc",
                    "convert_ogg": "vorbisenc",
                    "convert_flac": "flacenc",
                    "convert_aac": "faac"}

    def __init__(self):
        """
            Init MTP synchronisation
        """
        GObject.Object.__init__(self)
        self.__cancellable = Gio.Cancellable()
        self.__errors_count = 0
        self.__on_mtp_files = []
        self.__last_error = ""
        self.__uri = None
        self.__total = 0  # Total files to sync
        self.__done = 0   # Handled files on sync
        self.__mtp_syncdb = MtpSyncDb()

    def check_encoder_status(self, encoder):
        """
            Check encoder status
            @param encoder as str
            @return bool
        """
        if Gst.ElementFactory.find(self._GST_ENCODER[encoder]):
            return True
        return False

    def sync(self, uri, index):
        """
            Sync playlists with device. If playlists contains Type.NONE,
            sync albums marked as to be synced
            @param uri as str
            @param index as int => device index
        """
        try:
            self.__cancellable = Gio.Cancellable()
            self.__uri = uri
            self.__convert_bitrate = App().settings.get_value(
                "convert-bitrate").get_int32()
            self.__errors_count = 0
            self.__total = 0
            self.__done = 0
            playlists = []
            tracks = []

            Logger.info("Geting tracks to sync")
            # New tracks for synced albums
            album_ids = App().albums.get_synced_ids(index)
            for album_id in album_ids:
                album = Album(album_id)
                tracks += album.tracks
            # New tracks for playlists
            playlist_ids = App().playlists.get_synced_ids(index)
            for playlist_id in playlist_ids:
                name = App().playlists.get_name(playlist_id)
                playlists.append(escape(name))
                if App().playlists.get_smart(playlist_id):
                    request = App().playlists.get_smart_sql(playlist_id)
                    for track_id in App().db.execute(request):
                        tracks.append(Track(track_id))
                else:
                    for track_id in App().playlists.get_track_ids(playlist_id):
                        tracks.append(Track(track_id))

            Logger.info("Getting URIs to copy")
            uris = self.__get_uris_to_copy(tracks, playlists)
            self.__total = len(tracks)

            Logger.info("Delete old files")
            self.__delete_old_uris(uris)

            Logger.info("Copy files")
            for (src_uri, dst_uri) in uris:
                self.__copy_file(src_uri, dst_uri)
                self.__done += 1
                GLib.idle_add(self.emit, "sync-progress",
                              self.__done / self.__total)

            Logger.debug("Create unsync")
            d = Gio.File.new_for_uri(self.__uri + "/unsync")
            if not d.query_exists():
                d.make_directory_with_parents()
        except Exception as e:
            Logger.error("MtpSync::__sync(): %s" % e)
        finally:
            Logger.debug("Save sync db")
            self.__mtp_syncdb.save()
            self.cancel()
            if self.__errors_count != 0:
                Logger.debug("Sync errors")
                GLib.idle_add(self.emit, "sync-errors", self.__last_error)
            Logger.debug("Sync finished")
            GLib.idle_add(self.emit, "sync-finished")

    def cancel(self):
        """
            Cancel sync
        """
        Logger.info("MtpSync::cancel()")
        self.__cancellable.cancel()

    @property
    def db(self):
        """
            Get sync db
        """
        return self.__mtp_syncdb

############
# PRIVATE  #
############
    def __get_album_on_device_uri(self, track):
        """
            Get on device URI for album
            @param track as Track
            @return URI as str
        """
        album_name = track.album_name.lower()
        is_compilation = track.album.artist_ids[0] == Type.COMPILATIONS
        if is_compilation:
            return "%s/%s" % (self.__uri, escape(album_name[:100]))
        else:
            artists = ", ".join(track.album.artists).lower()
            string = escape("%s_%s" % (artists, album_name))
            return "%s/%s" % (self.__uri, string[:100])

    def __get_uris_to_copy(self, tracks, playlists):
        """
            Get on device URI for all tracks
            @param tracks as [Track]
        """
        uris = []
        art_uris = []
        playlist_uris = []
        for track in tracks:
            f = Gio.File.new_for_uri(track.uri)
            album_device_uri = self.__get_album_on_device_uri(track)
            album_local_uri = f.get_parent().get_uri()
            filename = f.get_basename()
            uris.append(("%s/%s" % (album_local_uri, filename),
                         "%s/%s" % (album_device_uri, escape(filename))))
            art_uri = App().art.get_album_artwork_uri(track.album)
            if art_uri is not None:
                art_filename = Gio.File.new_for_uri(art_uri).get_basename()
                art_uris.append((art_uri,
                                 "%s/%s" % (album_device_uri,
                                            escape(art_filename))))
#        for playlist in playlists:
#            on_disk_path = "/tmp/lollypop_%s.m3u" % playlist
#            on_device_uri = "%s/%s" (self.__uri, playlist)
        return uris + art_uris + playlist_uris

    def __delete_old_uris(self, uris):
        """
            Delete old URIs from device
            @param uris as [str]
        """
        on_device_uris = self.__on_device_uris()
        for (src_uri, dst_uri) in uris:
            if dst_uri in on_device_uris:
                on_device_uris.remove(dst_uri)
        for uri in on_device_uris:
            if self.__cancellable.is_cancelled():
                break
            try:
                f = Gio.File.new_for_uri(uri)
                parent = f.get_parent()
                f.delete(self.__cancellable)
                self.__mtp_syncdb.delete_uri(uri)
                infos = parent.enumerate_children(
                    "standard::name,standard::type",
                    Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
                    None)
                if len(list(infos)) == 0:
                    parent.delete(self.__cancellable)
            except Exception as e:
                Logger.error("MtpSync::__delete_old_uris(): %s", e)

    def __on_device_uris(self):
        """
            Get URIS on device
            @return [str]
        """
        children = []
        dir_uris = [self.__uri]
        d = Gio.File.new_for_uri(self.__uri)
        if not d.query_exists():
            d.make_directory_with_parents(None)
        while dir_uris:
            if self.__cancellable.is_cancelled():
                break
            try:
                uri = dir_uris.pop(0)
                d = Gio.File.new_for_uri(uri)
                infos = d.enumerate_children(
                    "standard::name,standard::type",
                    Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
                    None)
                for info in infos:
                    if self.__cancellable.is_cancelled():
                        break
                    if info.get_file_type() == Gio.FileType.DIRECTORY:
                        if info.get_name() != "unsync":
                            f = infos.get_child(info)
                            dir_uris.append(f.get_uri())
                    else:
                        if info.get_name() == "lollypop-sync.db":
                            continue
                        f = infos.get_child(info)
                        if not f.get_uri().endswith(".m3u"):
                            children.append(f.get_uri())
            except Exception as e:
                Logger.error("MtpSync::__get_track_files(): %s, %s" % (e, uri))
        return children

    def __copy_file(self, src_uri, dst_uri):
        """
            Copy source to destination
            @param src_uri as str
            @param dst_uri as str
        """
        Logger.debug("MtpSync::__copy_file(): %s -> %s"
                     % (src_uri, dst_uri))
        src = Gio.File.new_for_uri(src_uri)
        dst = Gio.File.new_for_uri(dst_uri)
        parent = dst.get_parent()
        if not parent.query_exists():
            parent.make_directory_with_parents()
        # Check extension for convertion
        m = match(r".*(\.[^.]*)", src_uri)
        ext = m.group(1)
        convert_ext = self.__EXTENSION[self.__mtp_syncdb.encoder]
        if ext.lower() in [".png", ".jpg", ".jpeg", "gif"]:
            convertion_needed = False
        elif (convert_ext is not None and
                ext != convert_ext) or self.__mtp_syncdb.normalize:
            convertion_needed = True
            dst_uri = dst_uri.replace(ext, convert_ext)
        else:
            convertion_needed = False
        info = src.query_info("time::modified",
                              Gio.FileQueryInfoFlags.NONE,
                              None)
        mtime = info.get_attribute_uint64("time::modified")
        if not dst.query_exists() or\
                self.__mtp_syncdb.get_mtime(dst_uri) < mtime:
            if convertion_needed:
                convert_uri = "file:///tmp/lollypop_convert"
                convert_file = Gio.File.new_for_uri(convert_uri)
                pipeline = self.__convert(src, convert_file)
                # Check if encoding is finished
                if pipeline is not None:
                    bus = pipeline.get_bus()
                    bus.add_signal_watch()
                    bus.connect("message::eos", self.__on_bus_eos)
                    self.__encoding = True
                    while self.__encoding and\
                            not self.__cancellable.is_cancelled():
                        sleep(1)
                    bus.disconnect_by_func(self.__on_bus_eos)
                    pipeline.set_state(Gst.State.PAUSED)
                    pipeline.set_state(Gst.State.READY)
                    pipeline.set_state(Gst.State.NULL)
                    convert_file.move(
                        dst, Gio.FileCopyFlags.OVERWRITE, None, None)
                    # To be sure
                    try:
                        convert_file.delete(None)
                    except:
                        pass
            else:
                src.copy(dst, Gio.FileCopyFlags.OVERWRITE, None, None)
            self.__mtp_syncdb.set_mtime(dst_uri, mtime)

    def __convert(self, src, dst):
        """
            Convert file to mp3
            @param src as Gio.File
            @param dst as Gio.File
            @return Gst.Pipeline
        """
        if src.get_path() is None:
            Logger.error("Can't convert files over sftp, smb, ...")
            return None
        try:
            # We need to escape \ in path
            src_path = src.get_path().replace("\\", "\\\\\\")
            dst_path = dst.get_path().replace("\\", "\\\\\\")
            pipeline_str = self.__ENCODE_START % src_path
            if self.__mtp_syncdb.normalize:
                pipeline_str += self.__NORMALIZE
            if self.__mtp_syncdb.encoder in ["convert_vorbis", "convert_aac"]:
                convert_bitrate = self.__convert_bitrate * 1000
            else:
                convert_bitrate = self.__convert_bitrate
            try:
                pipeline_str += self.__ENCODERS[self.__mtp_syncdb.encoder] %\
                    convert_bitrate
            except:
                pipeline_str += self.__ENCODERS[self.__mtp_syncdb.encoder]
            pipeline_str += self.__ENCODE_END % dst_path
            pipeline = Gst.parse_launch(pipeline_str)
            pipeline.set_state(Gst.State.PLAYING)
            return pipeline
        except Exception as e:
            Logger.error("MtpSync::__convert(): %s" % e)
            return None

    def __on_bus_eos(self, bus, message):
        """
            Stop encoding
            @param bus as Gst.Bus
            @param message as Gst.Message
        """
        self.__encoding = False
