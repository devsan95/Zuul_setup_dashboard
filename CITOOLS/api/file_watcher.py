#!/usr/bin/env python

"""
Real time log files watcher supporting log rotation.
Author: Giampaolo Rodola' <g.rodola [AT] gmail [DOT] com>
License: MIT
"""

import os
import time
import errno
import stat


class FileWatcher(object):
    """Looks for changes in all files of a directory.
    This is useful for watching log file changes in real-time.
    It also supports files rotation.
    Example:
    >>> def callback(filename, lines):
    ...     print filename, lines
    ...
    >>> l = FileWatcher("/var/log/", callback)
    >>> l.loop()
    """

    def __init__(self, file_name_list, callback, tail_lines=0):
        """Arguments:
        (str) @folder:
            the folder to watch
        (callable) @callback:
            a function which is called every time a new line in a
            file being watched is found;
            this is called with "filename" and "lines" arguments.
        (list) @extensions:
            only watch files with these extensions
        (int) @tail_lines:
            read last N lines from files being watched before starting
        """
        self.files_map = {}
        self.callback = callback
        self.file_list = [os.path.realpath(x) for x in file_name_list]
        self.extensions = None

        assert callable(callback)
        self.update_file()
        # The first time we run the script we move all file markers at EOF.
        # In case of files created afterwards we don't do this.
        for id, file_name in self.files_map.iteritems():
            file_name.seek(os.path.getsize(file_name.name))  # EOF
            if tail_lines:
                lines = self.tail(file_name.name, tail_lines)
                if lines:
                    self.callback(file_name.name, lines)

    def __del__(self):
        self.close()

    def loop(self, interval=0.1, async_=False):
        """Start the loop.
        If async is True make one loop then return.
        """
        while 1:
            self.update_file()
            for fid, file_path in list(self.files_map.iteritems()):
                self.readfile(file_path)
            if async_:
                return
            time.sleep(interval)

    def log(self, line):
        """Log when a file is un/watched"""
        print line

    @staticmethod
    def tail(fname, window):
        """Read last N lines from file fname."""
        try:
            f = open(fname, 'r')
        except IOError, err:
            if err.errno == errno.ENOENT:
                return []
            else:
                raise
        else:
            BUFSIZ = 1024
            f.seek(0, os.SEEK_END)
            fsize = f.tell()
            block = -1
            data = ""
            exit = False
            while not exit:
                step = (block * BUFSIZ)
                if abs(step) >= fsize:
                    f.seek(0)
                    exit = True
                else:
                    f.seek(step, os.SEEK_END)
                data = f.read().strip()
                if data.count('\n') >= window:
                    break
                else:
                    block -= 1
            return data.splitlines()[-window:]

    def update_file(self):
        ls = []
        for absname in self.file_list:
            try:
                st = os.stat(absname)
            except EnvironmentError, err:
                if err.errno != errno.ENOENT:
                    raise
            else:
                if stat.S_ISREG(st.st_mode):
                    fid = self.get_file_id(st)
                    ls.append((fid, absname))

        # check existent files
        for fid, file in list(self.files_map.iteritems()):
            try:
                st = os.stat(file.name)
            except EnvironmentError, err:
                if err.errno == errno.ENOENT:
                    self.unwatch(file, fid)
                else:
                    raise
            else:
                if fid != self.get_file_id(st):
                    # same name but different file (rotation); reload it.
                    self.unwatch(file, fid)
                    self.watch(file.name)

        # add new ones
        for fid, fname in ls:
            if fid not in self.files_map:
                self.watch(fname)

    def readfile(self, file):
        lines = file.readlines()
        if lines:
            self.callback(file.name, lines)

    def watch(self, fname):
        try:
            file = open(fname, "r")
            fid = self.get_file_id(os.stat(fname))
        except EnvironmentError, err:
            if err.errno != errno.ENOENT:
                raise
        else:
            self.log("watching logfile %s" % fname)
            self.files_map[fid] = file

    def unwatch(self, file, fid):
        # file no longer exists; if it has been renamed
        # try to read it for the last time in case the
        # log rotator has written something in it.
        self.readfile(file)
        self.log("un-watching logfile %s" % file.name)
        del self.files_map[fid]

    @staticmethod
    def get_file_id(st):
        return "%xg%x" % (st.st_dev, st.st_ino)

    def close(self):
        for id, file in self.files_map.iteritems():
            file.close()
        self.files_map.clear()
