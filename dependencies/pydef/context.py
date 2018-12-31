
import os
from .source import Source
from .utils import parse_import, get_module_filename, rx, get_lvl, is_empty, SN


class Cursor:
    def __init__(self, filename, row=0, col=0, kind=None):
        self.filename = filename
        self.row = row
        self.col = col
        self.kind = kind

    def __repr__(self):
        return '{}[{}:{}] ({})'.format(self.filename, self.row, self.col, self.kind)


class Context:
    def __init__(self, sources, *, path=None):
        self.path = path
        self.sources = {}
        for s in sources:
            self.sources[s.filename] = s

    def get_source(self, filename):
        # type: Source
        s = self.sources.get(filename)
        if s:
            return s

        self.sources[filename] = s = Source(filename)
        return s

    def find_in_file(self, word, filename, start=None):
        source = self.get_source(filename)
        assign = source.find_assigment(word, start)
        if not assign:
            return

        if assign.kind == 'import':
            im = parse_import(assign.line)
            module_name = im.result.get(word)
            assert module_name

            module_name = get_module_filename(module_name, path=self.path)
            if module_name:
                return Cursor(module_name)
            return
        elif assign.kind == 'import2':
            im = parse_import(assign.line)
            bmodule = im.lib
            if bmodule[0] == '.':
                module_name = filename
                if bmodule == '.':
                    module_name = get_module_filename(word, path=[os.path.dirname(module_name)])
                    return Cursor(module_name)
                else:
                    for name in bmodule.split('.')[1:]:
                        module_name = get_module_filename(name, path=[os.path.dirname(module_name)])
            else:
                names = bmodule.split('.')
                module_name = get_module_filename(names[0], path=self.path)
                for name in names[1:]:
                    module_name = get_module_filename(name, path=[os.path.dirname(module_name)])

            word = im.result.get(word, word)
            return self.find_in_file(word, filename=module_name)
        elif assign.kind in ('def', 'var', 'args'):
            return SN(filename=filename, row=assign.row, kind=assign.kind)
        elif assign.kind == 'class':
            return Cursor(filename, assign.row, kind='class')
        else:
            raise NotImplementedError

    def find_attribute(self, filename, start, word):
        source = self.get_source(filename)

        line = source.lines[start]
        class_lvl = get_lvl(line)
        alvl = None
        for i in range(start + 1, len(source.lines)):
            line = source.lines[i]
            if is_empty(line):
                continue
            lvl = get_lvl(line)
            if alvl is None:
                if lvl <= class_lvl:
                    continue
                alvl = lvl

            if lvl < alvl:
                break

            if lvl > alvl:
                continue

            r = rx(r'\s*def\s+([\w\d\_]+)\(').match(line)
            if not r:
                r = rx(r'\s*([\w\d\_]+)\s*=').match(line)
            if r:
                if r.groups()[0] == word:
                    return Cursor(filename, i)

    def find_class(self, filename, index):
        source = self.get_source(filename)

        for index in range(index, -1, -1):
            line = source.lines[index]
            if is_empty(line):
                continue

            r = rx(r'^\s*class ').match(line)
            if r:
                return SN(row=index, line=line, filename=filename)

            lvl = get_lvl(line)
            if not lvl:
                return
