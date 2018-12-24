
import os
import string
import re
from types import SimpleNamespace as SN


def get_word(cursor, lines):
    line = lines[cursor[0]]
    letters = string.digits + string.ascii_letters + '_.'
    i = cursor[1]

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


class Cursor:
    def __init__(self, filename, line=0, col=0, kind=None):
        self.filename = filename
        self.line = line
        self.col = col
        self.kind = kind

    def __repr__(self):
        return '{}[{}:{}]'.format(self.filename, self.line, self.col)


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
            r = re.split(r'[\s\,]+', r.groups()[0])
            if word in r:
                return 'args'
    if re.match(word + r'\s*=', line):
        return 'var'
    if line.startswith('import '):
        return 'import'
    r = re.match(r'from\s+[\w\d\.]+\s+import\s+(.*)$', line)
    if r:
        r = re.split(r'[\s\,]+', r.groups()[0])
        if word in r:
            return 'import2'


def get_lvl(line):
    return len(re.match(r'^(\s*)', line).groups()[0])


rx_skip0 = re.compile(r'\s*$')
rx_skip1 = re.compile(r'\s*\#')


def is_empty(line):
    return bool(rx_skip0.match(line) or rx_skip1.match(line))


def find_assigment(lines, word, start=None):

    def get_line(index):
        result = lines[index]
        while index > 0:
            index -= 1
            r = re.match(r'^(.*)\\\s*$', lines[index])
            if not r:
                break
            result = r.groups()[0] + result

        return result

    def find_on_lvl(active_lvl, start, d=1):
        index = start
        if d == 1:
            left = 0
            right = len(lines) - 2
        else:
            left = 1
            right = len(lines) - 1

        line = get_line(start)
        kind = is_assign(line, word)
        if kind:
            return SN(lineno=start, line=line, kind=kind)

        while index >= left and index <= right:
            index += d
            line = get_line(index)
            if is_empty(line):
                continue
            lvl = get_lvl(line)
            if lvl > active_lvl:
                continue
            elif lvl < active_lvl:
                return SN(kind='lvl', lineno=index, lvl=lvl)

            kind = is_assign(line, word)
            if kind and kind != 'args':
                return SN(lineno=index, line=line, kind=kind)

    if start is None:
        start = len(lines) - 1
        lvl = 0
    else:
        line = get_line(start)
        lvl = get_lvl(line)

    result = find_on_lvl(lvl, start, d=-1)
    if not result:
        return

    if result and result.kind != 'lvl':
        return result

    while True:
        r = find_on_lvl(result.lvl, result.lineno)
        if r and r.kind != 'lvl':
            return r
        result = find_on_lvl(result.lvl, result.lineno, d=-1)
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


def find_in_file(word, filename, start=None, lines=None, path=None):
    if not lines:
        lines = open(filename).readlines()
    assign = find_assigment(lines, word, start)
    if not assign:
        return

    if assign.kind == 'import':
        line = list(map(str.strip, assign.line.split('import ')[1].split(',')))
        if word in line:
            module_name = word
        else:
            raise NotImplementedError

        module_name = get_module_filename(module_name, path=path)
        if module_name:
            return Cursor(module_name)
        return
    elif assign.kind == 'import2':
        r = re.match(r'from\s+([\w\d\.\_]+)\s+import', assign.line)
        bmodule = r.groups()[0]
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
            module_name = get_module_filename(names[0], path=path)
            for name in names[1:]:
                module_name = get_module_filename(name, path=[os.path.dirname(module_name)])

        return find_in_file(word, filename=module_name)
    elif assign.kind in ('def', 'var', 'args'):
        return SN(filename=filename, line=assign.lineno, kind=assign.kind)
    elif assign.kind == 'class':
        return Cursor(filename, assign.lineno, kind='class')
    else:
        raise NotImplementedError


def find_attribute(filename, start, word, lines):
    if not lines:
        lines = open(filename).readlines()

    line = lines[start]
    r = re.match(r'^(\s*)\S', line)
    class_lvl = len(r.groups()[0])
    alvl = None
    for i in range(start + 1, len(lines)):
        line = lines[i]
        r = re.match(r'^(\s*)\S', line)
        if not r:
            continue
        lvl = len(r.groups()[0])
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


def goto_definition(path, filename, cursor, source=None):
    if not source:
        source = open(filename, 'r').read()
    lines = source.splitlines()
    fullword = get_word(cursor, lines)
    # print('word', fullword)

    cur_filename = filename
    lineno = cursor[0]
    result = None
    for word in fullword.split('.'):
        if cur_filename == filename:
            cur_lines = lines

        if result:
            if result.kind == 'class':
                result = find_attribute(result.filename, result.line, word, lines=cur_lines)
                if not result:
                    result = Cursor(cur_filename, result.line)
                break
            elif result.kind == 'var':
                return None
        result = find_in_file(word, start=lineno, filename=cur_filename, lines=cur_lines, path=path)
        if not result:
            return
        cur_filename = result.filename
        cur_lines = lineno = None

    return result
