
from .source import Source
from .context import Context


def goto_definition(path, filename, row, col, source=None):
    """
        return: {filename, row}
    """
    source = Source(filename, source=source)
    fullword = source.get_word(row, col)
    if not fullword:
        return
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
