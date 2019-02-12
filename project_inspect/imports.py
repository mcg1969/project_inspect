import re
import os
import json
import functools

from glob import glob, iglob
from os.path import join, basename, dirname, exists, isfile

from lib2to3 import pygram
from lib2to3 import pytree
from lib2to3.pgen2 import driver
from lib2to3.pgen2 import parse
from lib2to3.pgen2 import token
from lib2to3.pygram import python_symbols as syms
from lib2to3.pytree import Leaf, Node


def stringify(content):
    if isinstance(content, list):
        return ''.join(map(stringify, content))
    elif isinstance(content, pytree.Leaf):
        return content.value
    elif isinstance(content, pytree.Node):
        if content.type in (syms.dotted_as_name, syms.import_as_name):
            right = content.children.index(pytree.Leaf(1, 'as'))
            return stringify(content.children[:right])
        elif content.type == syms.dotted_name:
            return stringify(content.children)
        else:
            raise RuntimeError('Unexpected: {!r}'.format(content))


def yield_imports(node):
    if node.type == syms.import_from:
        # from a import b as c, d as e, f
        right = node.children.index(pytree.Leaf(1, 'import'))
        base = stringify(node.children[1:right])
        if not base.endswith('.'):
            base += '.'
        node = node.children[right+1]
    elif node.type == syms.import_name:
        # import a, b as c
        base = ''
        node = node.children[1]
    else:
        for child in node.children:
            for value in yield_imports(child):
                yield value
        return
    if node.type in (syms.import_as_names, syms.dotted_as_names):
        for child in node.children[::2]:
            yield base + stringify(child)
    else:
        yield base + stringify(node)

                
def find_python_imports(code):
    p3_grammar = pygram.python_grammar_no_print_statement
    p3_driver = driver.Driver(p3_grammar, convert=pytree.convert)
    code = code + '\n'
    try:
        tree = p3_driver.parse_string(code, debug=False)
        return set(yield_imports(tree))
    except parse.ParseError:
        pass
    p2_grammar = pygram.python_grammar
    p2_driver = driver.Driver(p2_grammar, convert=pytree.convert)
    try:
        tree = p2_driver.parse_string(code, debug=False)
        return set(yield_imports(tree))
    except parse.ParseError:
        pass
    for line in code.splitlines():
        imports = set()
        try:
            tree = p3_driver.parse_string(line + '\n', debug=False)
            imports.update(yield_imports(tree))
        except parse.ParseError:
            pass
    return imports


R_PKGNAME = r'[a-zA-Z][a-zA-Z0-9.]*[a-zA-Z0-9]'
LIB_MATCH = r'library\s*\(\s*[''"]?(' + R_PKGNAME + r')[''"]?\s*\)'
COLON_MATCH = r'.*?(' + R_PKGNAME + ')\s*::\s*[a-zA-Z]'
EITHER_MATCH = LIB_MATCH + r'|' + COLON_MATCH


def find_r_imports(code):
    modules = set()
    if not isinstance(code, list):
        code = code.splitlines()
    for line in code:
        if not re.match('\s*#', line):
            for match in re.findall(EITHER_MATCH, line):
                modules.update(match)
        modules.discard('')
    return modules


def find_notebook_imports(nbdata):
    ndata = json.loads(nbdata)
    language = ndata['metadata']['kernelspec']['language'].lower()
    if language not in ('python', 'r'):
        raise RuntimeError('Unsupported language: {}'.format(language))
    modules = set()
    modules.add('ipykernel' if language == 'python' else 'IRkernel')
    for cell in ndata['cells']:
        if cell['cell_type'] == 'code':
            if language == 'python':
                source = '\n'.join(c for c in cell['source'] if not c.startswith('%'))
                processor = find_python_imports
            elif language == 'r':
                source = '\n'.join(cell['source'])
                processor = find_r_imports
            modules.update(processor(source))
    return modules, language


def find_file_imports(fpath):
    if not isfile(fpath):
        raise RuntimeError('Not a file: {}'.format(fpath))
    with open(fpath, 'rt') as fp:
        data = fp.read()
    if fpath.endswith('.ipynb'):
        return find_notebook_imports(data)
    elif fpath.endswith('.py'):
        return find_python_imports(data), 'python'
    elif fpath.endswith('.R'):
        return find_r_imports(data), 'r'
    else:
        raise RuntimeError('Unexpected file: {}'.format(fpath))
        
