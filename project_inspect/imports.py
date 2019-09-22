import re
import os
import json
import functools

from glob import glob, iglob
from os.path import join, basename, dirname, exists, isfile

from lib2to3 import pygram
from lib2to3 import pytree
from lib2to3.pgen2 import driver, parse, token
from lib2to3.pgen2.parse import ParseError
from lib2to3.pgen2.tokenize import TokenError
from lib2to3.pygram import python_symbols as syms
from lib2to3.pytree import Leaf, Node

from .utils import load_file, set_log_root, shortpath


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

                
p3_grammar = pygram.python_grammar_no_print_statement
p3_driver = driver.Driver(p3_grammar, convert=pytree.convert)
p2_grammar = pygram.python_grammar
p2_driver = driver.Driver(p2_grammar, convert=pytree.convert)


def find_python_imports(code, recurse=True):
    imports = set()
    code = code + '\n'
    try:
        tree = p3_driver.parse_string(code, debug=False)
        imports.update(yield_imports(tree))
    except:
        try:
            tree = p2_driver.parse_string(code, debug=False)
            imports.update(yield_imports(tree))
        except:
            if recurse:
                for line in map(str.strip, code.splitlines()):
                    if line and not line.startswith('#'):
                        imports.update(find_python_imports(line, False))
    return imports


R_PKGNAME = r'[a-zA-Z][a-zA-Z0-9.]*[a-zA-Z0-9]'
LIB_MATCH = (r'library\s*\(\s*["{0}]?(' + R_PKGNAME + r')["{0}]?\s*\)').format("'")
COLON_MATCH = r'.*?(' + R_PKGNAME + r')\s*::\s*[a-zA-Z]'
EITHER_MATCH = LIB_MATCH + r'|' + COLON_MATCH


def find_r_imports(code):
    modules = set()
    if not isinstance(code, list):
        code = code.splitlines()
    for line in code:
        if not re.match(r'\s*#', line):
            for match in re.findall(EITHER_MATCH, line):
                modules.update(match)
        modules.discard('')
    return modules


def strip_python_magic(cell):
    for c in cell:
        cstrip = c.lstrip()
        if cstrip.startswith('%'):
            if not cstrip.startswith('%%') and ' ' in cstrip:
                yield cstrip.split(' ', 1)[1]
        else:
            yield c


def find_notebook_imports(ndata):
    try:
        language = ndata['metadata']['kernelspec']['language'].lower()
    except (KeyError, TypeError):
        language = 'unknown'
    modules = set()
    if language in ('python', 'r'):
        modules.add('ipykernel' if language == 'python' else 'IRkernel')
        for cell in ndata['cells']:
            if cell['cell_type'] == 'code':
                if language == 'python':
                    source = '\n'.join(strip_python_magic(cell['source']))
                    processor = find_python_imports
                elif language == 'r':
                    source = '\n'.join(cell['source'])
                    processor = find_r_imports
                modules.update(processor(source))
    return modules, language


def find_file_imports(fpath, submodules=False, locals=False):
    if not isfile(fpath) or not fpath.endswith(('.ipynb', '.py', '.R')):
        return set(), None
    data = load_file(fpath)
    if data is None:
    	return set(), None
    elif fpath.endswith('.ipynb'):
        imports, language = find_notebook_imports(data)
    elif fpath.endswith('.py'):
        imports, language = find_python_imports(data), 'python'
    else: # .R
        imports, language = find_r_imports(data), 'r'
    if language == 'python':
        if not submodules:
            imports = set('.' if imp.startswith('.') else imp.split('.', 1)[0] for imp in imports)
        if not locals:
            imports = set(imp for imp in imports if not imp.startswith('.'))
    return imports, language

