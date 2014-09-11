from config import *
from subprocess import call

import os
import sys

class MConfig(object):
    pass

class Util:
    _queue = None
    config = MConfig()

    def __init__(self, queue):
        self._queue = queue
        setattr(self.config, "download_missing", config_get("download_missing"))

    def printstr(self, str): # print without newline
        sys.stdout.write(str)
        sys.stdout.flush()

    @classmethod
    def shell(cls, cmdline): # execute shell commands (unicode support)
        call(cmdline, shell=True)

    def get_output_path(self, track, escaped = True):
        _output_path = config_get('output_path')
        if not _output_path:
            _output_path = config_get('mp3_path')

        if self._queue.is_starred_track():
            artist   = track.artists()[0].name()
            _output_path = _output_path+'/'+self.shellreplace('Spotify Starred')
            _output_path = _output_path+'/'+self.shellreplace(artist)
        else:
            artist   = track.album().artist().name()
            album    = track.album().name()
            year     = str(track.album().year())
            _output_path = _output_path+'/'+self.shellreplace(artist)
            _output_path = _output_path+'/'+self.shellreplace(album)
            _output_path = _output_path+' '+self.shellreplace('('+year+')')

        if not os.path.exists(_output_path):
            os.makedirs(_output_path)

        if not self._queue.is_starred_track():
            number = str(track.index()).zfill(2)
            disc = str(track.disc()).zfill(2)

            _output_path = _output_path+'/'+self.shellreplace(disc)+'-' \
                    +self.shellreplace(number)+'. '
        else:
            _output_path = _output_path+'/'

        _output_path = _output_path+self.shellreplace(track.name())

        if escaped:
            return self.shellescape(_output_path)

        return _output_path

    def get_encoders(self):
        lst = config_get("encoders", ["mp3"])
        rv = {}
        for e in lst:
            rv[e] = map(lambda x: unicode(x), config_get(e, []))
        return rv



    def shellreplace(self, s):
        return s \
            .replace('!', '_') \
            .replace('/', '_') \
            .replace(':', '_')

    @classmethod
    def shellescape(cls, s):
        return s \
            .replace('"', '\\"') \
            .replace(' ', '\\ ') \
            .replace('\'', '\\\'') \
            .replace(';', '\\;') \
            .replace('(', '\\(') \
            .replace(')', '\\)') \
            .replace('[', '\\[') \
            .replace(']', '\\]') \
            .replace('&', '\\&') \
            .replace('#', '\\#')

    def is_known_not_available(self, link):
        try:
            f = open('not_available', 'r')
        except IOError:
            return False
        lines = f.readlines()
        f.close()
        found = False
        for line in lines:
            if str(link) in line:
                found = True
                break
        return found

    def mark_as_not_available(self, link):
        if not self.is_known_not_available(link):
            f = open('not_available', 'a')
            f.write(str(link)+"\n")
            f.close()

    def is_compilation(self, album):
        # TODO: Use regexes instead of a manual list
        return album.type() == AlbumType.Compilation \
                or album.artist().name().lower() == 'various artists' \
                or 'anniversary' in album.name().lower() \
                or 'best of' in album.name().lower() \
                or 'collection' in album.name().lower() \
                or 'greatest' in album.name().lower() \
                or 'masterpieces' in album.name().lower() \
                or 'the 99 most' in album.name().lower() \
                or 'the best' in album.name().lower() \
                or 'top 100' in album.name().lower() \
                or 'treasures' in album.name().lower()

class AlbumType:
    Album = 0
    Single = 1
    Compilation = 2
    Unknown = 3
