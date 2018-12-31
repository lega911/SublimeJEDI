
import string
from .utils import is_empty, get_lvl, SN, rx, parse_function, parse_import


class Source:
    def __init__(self, filename, *, source=None):
        self.filename = filename
        if source:
            self.lines = source.splitlines()
        else:
            self.lines = open(filename).readlines()

    def find_on_lvl(self, word, active_lvl, start, d=1):
        index = start
        if d == 1:
            left = 0
            right = len(self.lines) - 2
        else:
            left = 1
            right = len(self.lines) - 1

        ae = self.get_assign(start, word)
        if ae:
            return ae

        while index >= left and index <= right:
            index += d
            line = self.lines[index]
            if is_empty(line):
                continue
            lvl = get_lvl(line)
            if lvl > active_lvl:
                continue
            elif lvl < active_lvl:
                return SN(kind='lvl', row=index, lvl=lvl)

            ae = self.get_assign(index, word)
            if ae and ae.kind != 'args':
                return ae

    def get_assign(self, index, word):
        line = self.lines[index]
        if not line or is_empty(line):
            return

        r = rx(r'^(\s*)(def|import|from) ').match(line)
        if r:
            for i in range(5):
                if index + i >= len(self.lines):
                    return
                if word in self.lines[index + i]:
                    break
            else:
                return
            lvl = len(r.groups()[0])
            kind = r.groups()[1]
            if kind == 'from':
                kind = 'import2'

            line = self.get_multiline(index)
            if word not in line:
                return

            if kind in ('import', 'import2'):
                im = parse_import(line)
                if word not in im.result:
                    return
            else:
                fl = parse_function(line)
                if not fl:
                    return
                if fl.name == word:
                    kind = 'def'
                elif word in fl.args:
                    kind = 'args'
                else:
                    return
            return SN(kind=kind, lvl=lvl, line=line, row=index)
        else:
            if word not in line:
                return

            r = rx(r'^(\s*)class\s+([\w\d_]+)\W').match(line)
            if r and r.groups()[1] == word:
                return SN(kind='class', lvl=len(r.groups()[0]), row=index, line=line)

            r = rx(r'^(\s*)([\w\d_]+)\s*=').match(line)
            if r and r.groups()[1] == word:
                return SN(kind='var', lvl=len(r.groups()[1]), row=index, line=line)

    def get_multiline(self, index):
        result = ''
        more = False
        quote = None
        bracket = 0
        prefix = False
        spec = set('\'"()#\\')
        while True:
            if index >= len(self.lines):
                return None  # wrong expression
            line = self.lines[index].rstrip('\n')
            index += 1
            for i, a in enumerate(line):
                if a not in spec:
                    continue

                if a == '\\' and i + 1 == len(line):
                    result += line[:-1]
                    more = True
                    break

                if quote:
                    if prefix:
                        prefix = False
                        continue
                    elif a == quote:
                        quote = None
                    elif a == '\\':
                        prefix = True
                    continue

                if a in ('"', "'"):
                    quote = a
                    continue
                elif a == '(':
                    bracket += 1
                    continue
                elif a == ')':
                    bracket -= 1
                    continue
                elif a == '#':
                    result += line[:i] + '\n'
                    break
            else:
                result += line + '\n'

            if more:
                more = False
                continue
            if bracket > 0:
                continue
            if quote:
                return  # not closed quote

            break

        return result

    def get_word(self, row, column):
        line = self.lines[row]
        if not line:
            return

        letters = string.digits + string.ascii_letters + '_.'
        i = column

        if i >= len(line):
            i = len(line) - 1

        if i > 0 and line[i] not in letters:
            i -= 1

        for start in range(i, -1, -1):
            if line[start] not in letters:
                start += 1
                break

        end = start
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
            line = self.lines[start]
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
