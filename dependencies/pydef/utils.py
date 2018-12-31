
import os
from types import SimpleNamespace as SN
import re


def rx(e):
    r = rx._cache.get(e)
    if r:
        return r
    rx._cache[e] = r = re.compile(e)
    return r

rx._cache = {}


def get_lvl(line):
    return len(rx(r'^([ \t]*)').match(line).groups()[0])


def is_empty(line):
    return bool(rx(r'\s*$').match(line) or rx(r'\s*\#').match(line))


def parse_import(line):
    r = rx(r'^\s*import\s+(.*)$').match(line)
    if r:
        libs_line = r.groups()[0]
        root_lib = None
    else:
        r = rx(r'^\s*from\s+([\w\d\.\_]+)\s+import\s+(.*)$').match(line)
        root_lib = r.groups()[0]
        libs_line = r.groups()[1]

    result = {}
    parts = rx(r'\s*,\s*').split(libs_line)
    for d in parts:
        d = d.split(' as ')
        if len(d) == 1:
            result[d[0]] = d[0]
        else:
            result[d[1]] = d[0]
    return SN(lib=root_lib, result=result)


def parse_function(line):
    r = rx(r'^(\s*)def\s*([\w\d_]+)\s*\(([^\()]*)\)').match(line)
    if not r:
        return

    lvl = len(r.groups()[0])
    func_name = r.groups()[1]
    args = rx(r'[\s\,=]+').split(r.groups()[2])
    return SN(name=func_name, args=args, lvl=lvl)


def get_module_filename(name, path=None):
    for p in path:
        module_name = os.path.join(p, name)
        if os.path.isfile(module_name + '.py'):
            return module_name + '.py'
        if os.path.isfile(module_name + '/__init__.py'):
            return module_name + '/__init__.py'
