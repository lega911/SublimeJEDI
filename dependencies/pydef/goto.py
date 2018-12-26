
import os
import string
import re
from types import SimpleNamespace as SN


class Cursor:
    def __init__(self, filename, row=0, col=0, kind=None):
        self.filename = filename
        self.row = row
        self.col = col
        self.kind = kind

    def __repr__(self):
        return '{}[{}:{}] ({})'.format(self.filename, self.row, self.col, self.kind)


def is_assign(line, word):
    if word not in line:
        return
    line = line.lstrip()
    if re.match(r'class\s+' + word + r'\W', line):
        return 'class'
    if re.match(r'def\s+' + word + r'\W', line):
        return 'def'
    if line.startswith('def '):
        r = re.match(r'def\s*[^\()]+\(([^\()]*)\)', line)
        if r:
            r = re.split(r'[\s\,=]+', r.groups()[0])
            if word in r:
                return 'args'
    if re.match(word + r'\s*=', line):
        return 'var'
    if line.startswith('import '):
        im = parse_import(line)
        if word in im.result:
            return 'import'
    else:
        r = re.match(r'from\s+[\w\d\.]+\s+import\s+', line)
        if r:
            im = parse_import(line)
            if word in im.result:
                return 'import2'


_get_lvl_rx = re.compile(r'^([ \t]*)')
rx_skip0 = re.compile(r'\s*$')
rx_skip1 = re.compile(r'\s*\#')
rx_def = re.compile(r'\s*def ')


def get_lvl(line):
    return len(_get_lvl_rx.match(line).groups()[0])


def is_empty(line):
    return bool(rx_skip0.match(line) or rx_skip1.match(line))


class Source:
    def __init__(self, filename, *, source=None):
        self.filename = filename
        if source:
            self.lines = source.splitlines()
        else:
            self.lines = open(filename).readlines()

    def get_line(self, index):
        result = self.lines[index]
        while index < len(self.lines):
            r = re.match(r'^(.*)\\\s*$', result)
            if r:
                index += 1
                result = r.groups()[0] + self.lines[index]
                continue
            if rx_def.match(result) and '):' not in result:
                index += 1
                result += self.lines[index]
                continue
            break

        return result

    def find_on_lvl(self, word, active_lvl, start, d=1):
        index = start
        if d == 1:
            left = 0
            right = len(self.lines) - 2
        else:
            left = 1
            right = len(self.lines) - 1

        line = self.get_line(start)
        kind = is_assign(line, word)
        if kind:
            return SN(row=start, line=line, kind=kind)

        while index >= left and index <= right:
            index += d
            line = self.get_line(index)
            if is_empty(line):
                continue
            lvl = get_lvl(line)
            if lvl > active_lvl:
                continue
            elif lvl < active_lvl:
                return SN(kind='lvl', row=index, lvl=lvl)

            kind = is_assign(line, word)
            if kind and kind != 'args':
                return SN(row=index, line=line, kind=kind)

    def get_word(self, row, column):
        line = self.lines[row]
        letters = string.digits + string.ascii_letters + '_.'
        i = column

        for start in range(i, -1, -1):
            if line[start] not in letters:
                start += 1
                break

        for end in range(start, len(line)):
            a = line[end]
            if a not in letters:
                break
            if a == '.' and end >= i:
                break
        else:
            end += 1

        return line[start:end]

    def find_assigment(self, word, start=None):
        if start is None:
            start = len(self.lines) - 1
            lvl = 0
        else:
            line = self.get_line(start)
            lvl = get_lvl(line)

        result = self.find_on_lvl(word, lvl, start, d=-1)
        if not result:
            return
        elif result.kind != 'lvl':
            return result

        while True:
            r = self.find_on_lvl(word, result.lvl, result.row)
            if r and r.kind != 'lvl':
                return r
            result = self.find_on_lvl(word, result.lvl, result.row, d=-1)
            if not result:
                return
            if result.kind != 'lvl':
                return result


def get_module_filename(name, path=None):
    for p in path:
        module_name = os.path.join(p, name)
        if os.path.isfile(module_name + '.py'):
            return module_name + '.py'
        if os.path.isfile(module_name + '/__init__.py'):
            return module_name + '/__init__.py'


def parse_import(line):
    r = re.match(r'^\s*import\s+(.*)$', line)
    if r:
        libs_line = r.groups()[0]
        root_lib = None
    else:
        r = re.match(r'^\s*from\s+([\w\d\.\_]+)\s+import\s+(.*)$', line)
        root_lib = r.groups()[0]
        libs_line = r.groups()[1]

    result = {}
    parts = re.split(r'\s*,\s*', libs_line)
    for d in parts:
        d = d.split(' as ')
        if len(d) == 1:
            result[d[0]] = d[0]
        else:
            result[d[1]] = d[0]
    return SN(lib=root_lib, result=result)


class Context:
    def __init__(self, sources, *, path=None):
        self.path = path
        self.sources = {}
        for s in sources:
            self.sources[s.filename] = s

    def get_source(self, filename):
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

        line = source.get_line(start)
        class_lvl = get_lvl(line)
        alvl = None
        for i in range(start + 1, len(source.lines)):
            line = source.get_line(i)
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

            r = re.match(r'\s*def\s+([\w\d\_]+)\(', line)
            if not r:
                r = re.match(r'\s*([\w\d\_]+)\s*=', line)
            if r:
                if r.groups()[0] == word:
                    return Cursor(filename, i)

    def find_class(self, filename, index):
        source = self.get_source(filename)

        for index in range(index, -1, -1):
            line = source.get_line(index)
            if is_empty(line):
                continue

            r = re.match(r'^\s*class ', line)
            if r:
                return SN(row=index, line=line, filename=filename)

            lvl = get_lvl(line)
            if not lvl:
                return


def goto_definition(path, filename, row, col, source=None):
    """
        return: {filename, row}
    """
    source = Source(filename, source=source)
    fullword = source.get_word(row, col)
    # print('word', fullword)
    ctx = Context([source], path=path)

    result = None
    for word in fullword.split('.'):
        if result:
            if result.kind == 'class':
                result = ctx.find_attribute(result.filename, result.row, word)
                break
            elif result.kind == 'args':
                class_ = ctx.find_class(result.filename, result.row)
                if not class_:
                    return
                return ctx.find_attribute(class_.filename, class_.row, word)
            elif result.kind == 'var':
                return None
        result = ctx.find_in_file(word, start=row, filename=filename)
        if not result:
            return
        filename = result.filename
        row = None

    return result
