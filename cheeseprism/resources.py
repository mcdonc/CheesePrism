import os
import json

from path import path

from pyramid.decorator import reify

from cheeseprism.index import IndexManager

def norm(p):
    return os.path.abspath(os.path.normpath(p))

def get_root(request):
    settings = request.registry.settings
    root_path = path(norm(settings['cheeseprism.file_root']))
    data_json = settings['cheeseprism.data_json']
    filesystem = Filesystem(root_path, data_json)
    return Root(filesystem, root_path)

class Filesystem(object):
    def __init__(self, root_path, data_json):
        self.root_path = root_path
        self.data_json = data_json

    def open(self, path, mode='rb'):
        if path.startswith(self.root_path.abspath()):
            return open(path, mode)

class Directory(object):
    def __init__(self, filesystem, path):
        self.filesystem = filesystem
        self.path = path
        self.acl_path = self.path / 'acl.json'

    @reify
    def name(self):
        return self.__name__

    def _get_acl(self):
        if self.acl_path.isfile():
            try:
                acl = json.load(self.acl_path.open('rb'))
                return acl
            except (ValueError, IOError):
                # valueerror: json object could not be decoded
                # ioerror: file doesn't exist
                pass
        raise AttributeError('__acl__')

    def _set_acl(self, acl):
        serialized = json.dumps(acl)
        tmp = self.acl_path / '_tmp'
        with tmp.open('wb') as fp:
            fp.write(serialized)
        # rename is atomic
        tmp.rename(self.acl_path.abspath())

    __acl__ = property(_get_acl, _set_acl)

    @property
    def distribution_data(self):
        datafile = self.path / self.filesystem.data_json
        if datafile.exists():
            with open(datafile) as stream:
                return json.load(stream)
        return {}

        
class Root(Directory):
    __name__ = ''
    __parent__ = None

    def _makeindex(self, d):
        idx = Index(self.filesystem, d)
        idx.__parent__ = self
        idx.__name__ = d.name
        return idx

    def indexes(self):
        L = []
        for d in self.path.dirs():
            if (d / '__isindex__').exists():
                L.append(self._makeindex(d))
        return L
        
    def __getitem__(self, name):
        nextpath = self.path / name
        # XXX symlinks
        if nextpath.isdir():
            idx = self._makeindex(nextpath)
            return idx
        raise KeyError(name)

    def add_index(self, name):
        index = self._makeindex(self.path / name)
        index.manager.initialize()

    def write_distribution_file(self, name, fp):
        dest = self.path / name
        tmp = dest + '_tmp'
        outfile = tmp.open('wb')
        while True:
            data = fp.read(4096 * 8)
            if not data:
                break
            outfile.write(data)
        outfile.close()
        # rename is atomic
        tmp.rename(dest)

class Index(Directory):
    @reify
    def manager(self):
        return IndexManager(self.path)
        
    def packages(self):
        return[]

