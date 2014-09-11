from clint.textui import colored, indent, puts, progress
from jukebox import Jukebox, Link
from lib.json_queue import JsonQueue
from lib.ripper_thread import RipperThread
from lib.util import Util
from subprocess import PIPE, Popen, call

import os
import sys
import time


class Encoder(object):
    args = []

    def run(self, session, meta):
        rcmd = [self.cmd] + self.args + self.get_args(session, meta)
        with indent(3, quote = colored.green(' > ')):
            puts("Encode %s: %s\n" %(self.suffix, rcmd))
            if call(rcmd) != 0:
                return False
            if not self.post_process(session, meta):
                return False
        return True

    def get_args(self, session, meta):
        return ["%s.raw" %meta["out_path_esc"],
                "%s.%s" %(meta["out_path_esc"], self.suffix)]

    def post_process(self, session, meta):
        return True

class Mp3Encoder(Encoder):
    suffix = "mp3"
    cmd = "lame"
    def post_process(self, session, meta):
        performers = ""
        for performer in meta["performers"]:
            performers += performer.name()+', '

        performers = performers.strip().rstrip(',')

        # write id3 data
        cmd = ['eyeD3',
              '--title',  meta["title"],
              '--artist', performers,
              '--album',  meta["album"]]

        if not meta['stared']:
            cmd += ['--track',         str(meta["number"]),
                    '--disc-num',      str(meta["disc"]),
                    '--release-year',  str(meta["year"]),
                    '--recording-date',str(meta["year"]),
                    '--add-image', 'cover.jpg:FRONT_COVER',
                    '--text-frame', 'TPE2:'+str(meta["artist"])]
        else:
            cmd += ['--text-frame',
                    'TPE2:Various Artists']

        cmd += ["%s.mp3" %meta["out_path_esc"]]
        print ''

        with indent(3, quote = colored.cyan(' # ')):
            try:
                puts('Executing %s' % cmd)
            except UnicodeEncodeError:
                sys.stdout.write(' # Executing %s\n' % cmd)

            return call(cmd) == 0

def xadd(key, value):
    if value:
        if isinstance(key, (tuple, list)):
            return list(key) + [unicode(value)]
        return [key, unicode(value)]
    else:
        return []

class OpusEncoder(Encoder):
    suffix = "opus"
    cmd = "opusenc"
    def get_args(self, session, meta):
        args = ["--raw"] \
             + xadd("--title", meta["title"]) \
             + xadd("--artist", meta["artist"]) \
             + xadd("--album", meta["album"]) \
             + ["--date", "%s-01-01" %meta["year"]] \
             + xadd("--genre", meta["genre"])
        if meta["number"]:
            args += xadd("--comment", "TRACKNUMBER=%s"%meta["number"])

        for performer in meta["performers"]:
            args += xadd("--comment", "PERFORMER=%s" %performer.name())

        if not meta['stared']:
            args += ["--picture", "3||||cover.jpg"]
        return args + ["%s.raw" %meta["out_path_esc"], "%s.%s" %(meta["out_path_esc"], self.suffix)]



ENCODERS = {
    "mp3": Mp3Encoder,
    "opus": OpusEncoder,
    }



class Ripper(Jukebox):
    _all_processes = [ ]
    _dot_count     = 0
    _downloaded    = 0.0
    _duration      = 0
    _end_of_track  = None
    _pipe          = None
    _json_queue    = None
    _ripper_thread = None
    _ripping       = False
    _util          = None
    _meta          = {}

    def __init__(self, *a, **kw):
        Jukebox.__init__(self, *a, **kw)

        self._json_queue = JsonQueue()
        self._util       = Util(self._json_queue)

        self._ripper_thread = RipperThread(self, self._json_queue)
        self._end_of_track = self._ripper_thread.get_end_of_track()
        self.set_ui_thread(self._ripper_thread)

        self.session.set_preferred_bitrate(1) # 320 kbps (ostensibly)

    def music_delivery_safe(self, \
            session, \
            frames, \
            frame_size, \
            num_frames, \
            sample_type, \
            sample_rate, \
            channels):
        self.rip(
                session,
                frames,
                frame_size,
                num_frames,
                sample_type,
                sample_rate,
                channels)
        return num_frames

    def end_of_track(self, session):
        Jukebox.end_of_track(self, session)
        os.rename(self._meta["out_path"] + ".raw.tmp",self._meta["out_path"] + ".raw")
        self._end_of_track.set()

    def get_encoders(self):
        rv = []
        for enc,args in self._util.get_encoders().iteritems():
            if not enc in ENCODERS:
                print colored.red("can't find encoder %s" %enc)
                continue
            e = ENCODERS[enc]()
            e.args = args
            rv.append(e)
        return rv

    def rip_init(self, session, track):
        output_path = self._util.get_output_path(track, escaped = False)

        print ''
        print colored.yellow(str(Link.from_track(track)))

        required = False
        if self._util.config.download_missing:
            for enc in self.get_encoders():
                if not os.path.exists("%s.%s" %(output_path, enc.suffix)):
                    required = True
        if not self._json_queue.is_downloaded(Link.from_track(track)):
            required = True

        #            or os.path.isfile(output_path):
        with indent(3, quote = colored.white(' > ')):
            if not required:
                try:
                    puts('Skipping %s' % output_path)
                except UnicodeEncodeError:
                    # Non-ASCII characters
                    sys.stdout.write(' > Skipping %s\n' % output_path)
                return False
            else:
                try:
                    puts('Downloading %s' % output_path)
                except UnicodeEncodeError:
                    # Non-ASCII characters
                    sys.stdout.write(' > Downloading %s\n' % output_path)

            meta = self._meta = self.prepare_meta(session, track)

            puts('Track URI:    %s'        % Link.from_track(track))

            try:
                puts('Album:        %s (%i)'   % (meta["album"], meta["year"]))
            except UnicodeEncodeError:
                sys.stdout.write(' > Album:        %s (%i)\n' % (meta["album"], meta["year"]))

            try:
                puts('Artist(s):    %s'        % meta["artist"])
            except UnicodeEncodeError:
                sys.stdout.write(' > Artist(s):    %s\n' % meta["artist"])

            try:
                puts('Album artist: %s'        % meta["artist"])
            except UnicodeEncodeError:
                sys.stdout.write(' > Album artist(s):    %s\n' % meta["artist"])

            try:
                puts('Track:        %s-%s. %s' % (meta["disc"], meta["number"], meta["title"]))
            except UnicodeEncodeError:
                sys.stdout.write(' > Track:        %s-%s. %s \n' \
                        % (meta["disc"], meta["number"], meta["title"]))

        rv = True
        if os.path.exists(meta["out_path"] + ".raw"):
            print colored.red("raw file exists, skipping download")
            self._pipe = None
            rv = -1
        else:
            self._pipe   = open(meta["out_path"] + ".raw.tmp","w")
        self._ripping    = True
        self._dotCount   = 0
        self._downloaded = 0.0
        self._duration   = track.duration()

        return rv

    def rip_terminate(self, session, track):
        if self._pipe is not None:
            self._pipe.close()
        self._ripping = False

    def rip(self,
            session,     # the current session
            frames,      # the audio data
            frame_size,  # bytes per frame
            num_frames,  # number of frames in this delivery
            sample_type, # currently this is always 0, which means 16-bit
                         # signed native endian integer samples
            sample_rate, # audio sample rate, in samples per second
            channels):   # number of audio channels, currently 1 or 2

        self._downloaded += float(frame_size) * float(num_frames)

        if self._ripping:
            # 320 kilobits per second
            # 40 kilobytes per second
            # duration in milliseconds
            # 40 bytes per millisecond
            if not self._pipe:
                self.end_of_track(session)
                return

            total_bytes = float(self._duration) * 40.0
            # 100 = 4.41 (don't ask me why)
            progress_perc = self._downloaded / total_bytes
            progress_perc = progress_perc * (100.0 / 4.41)
            progress.bar(range(100))
            sys.stdout.write('\r > Progress:     %.2f%%' % progress_perc)

            try:
                self._pipe.write(frames);
            except IOError as e:
                print colored.red("ERROR: %s" %e)
                os.kill(os.getpid(), 9)

    def prepare_meta(self, session, track):
        #out_path = self._util.get_mp3_path(track)
        out_path = self._util.get_output_path(track, escaped = False)
        out_path_esc = self._util.get_output_path(track, escaped = False)

        if self._json_queue.is_starred_track():
            album = 'Spotify Starred'
        else:
            album = track.album().name()

        disc       = track.disc()
        number     = track.index()
        title      = track.name()
        year       = track.album().year()
        artist     = track.album().artist().name()
        performers = track.artists()
        stared  = self._json_queue.is_starred_track()

        if not stared:
            # download cover
            image = session.image_create(track.album().cover())

            while not image.is_loaded():
                time.sleep(0.1)

            with open('cover.jpg', 'wb') as fp:
                fp.write(image.data())

        return {
            "out_path": out_path,
            "out_path_esc": out_path_esc,
            "album": album,
            "disc":  disc,
            "number": number,
            "title": title,
            "year": year,
            "artist": artist,
            "performers": performers,
            "stared": stared,
            "genre": None
            }


    def encode(self, session, track): # write ID3 data

        print "\n" + colored.green(str("Encode:"))
        success = True
        for enc in self.get_encoders():
            if not enc.run(session, self._meta):
                print colored.red("Error encoding: %s" %enc.suffix)
                success = False

        #try:
            #puts('Moving %s to %s' % ('temp.mp3', mp3_path))
        #except UnicodeEncodeError:
            #sys.stdout.write(' # Moving %s to %s\n' \
                    #% ('temp.mp3', mp3_path))

        ## move mp3 to final directory
        if not success:
            print colored.red("Error processing file. Keep raw file")
            return
        os.unlink(self._meta["out_path"] + ".raw")

        if os.path.exists("cover.jpg"):
            os.unlink("cover.jpg")
        # delete cover
        #if not self._json_queue.is_starred_track():
            #self._util.shell("rm -f cover.jpg")

        self._json_queue.mark_as_downloaded(Link.from_track(track))

