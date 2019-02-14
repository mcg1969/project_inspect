import functools
import subprocess
import sys
import json
import re
import os

from os.path import basename, dirname, join, exists, isfile, isdir, abspath
from glob import glob, iglob

from . import config
from .imports import find_python_imports, find_r_imports, find_file_imports

import logging
logger = logging.getLogger(__name__)

__all__ = ['environment_by_prefix', 'kernel_name_to_prefix']


def get_python_builtins(pybin):
    '''
    Determines the python modules that have been compiled into the Python executable.
    
    Attempts to run the executable and dump sys.builtin_module_names. If this is not
    possible, simply returns a set containing sys.builtin_module_names for the current
    executable. This is a sufficiently close approximation of what we need, so just
    a warning is raised, and execution proceeds.
    
    Args:
        pybin (str): path to a valid Python executable.
    Returns:
        set: a set of module names.
    '''
    try:
        cmd = [pybin, '-c', 'import sys, json; print(json.dumps(sys.builtin_module_names))']
        pycall = subprocess.check_output(cmd)
        return set(json.loads(pycall))
    except Exception as e:
        logger.warning(('Could not execute {} to extract sys.builtin_module_names; '
                        'using current Python interpreter instead:\n{}').format(pybin, str(e)))
        return set(sys.builtin_module_names)


def parse_egg_info(path):
    '''
    Returns the name, version, and key file list for a pip package.
    
    Args:
        path (str): path to the egg file or directory
    Returns:
        name (str): the name of the package.
        version (str): the version of the package.
        files (list of str): a list of the Python files found in the
            manifest file (SOURCES.txt, RECORD), if such a file is found.
            If the manifest is not found, an empty list is returned.
    '''
    name, version, _ = basename(path).rsplit('.', 1)[0].rsplit('-', 2)
    pdata = {'name': name.lower(),
             'version': version,
             'build': '<pip>',
             'depends': set(),
             'modules': {'python': set(), 'r': set()}}
    if path.endswith('.egg'):
        pdata['modules']['python'] = get_python_importables(path)
        path = join(path, 'EGG-INFO')
    else:
        pdata['modules']['python'] = get_python_importables(path.rsplit('.', 1)[0], level=1)
    fname = 'METADATA' if path.endswith('.dist-info') else 'PKG-INFO'
    fpath = join(path, fname)
    info = {}
    if isfile(fpath):
        for line in open(fpath, encoding='utf-8', errors='ignore'):
            m = re.match(r'(\w+):\s*(\S+)', line, re.I)
            if m:
                key = m.group(1).lower()
                info.setdefault(key, []).append(m.group(2))
            break
    if 'Requires-Dist' in info:
        pdata['depends'].update(x.split(' ', 1)[0].lower() for x in info['requires-dist'])
    else:
        req_txt = join(dirname(path2), 'requires.txt')
        if exists(req_txt):
            for dep in open(req_txt, 'rt'):
                m = re.match(r'^([\w_-]+)', dep)
                if not m:
                    break
                pdata['depends'].add(m.groups()[0].lower())
    return pdata

    
def parse_conda_meta(mpath):
    with open(mpath) as fp:
        mdata = json.load(fp)
    pdata = {'name': mdata['name'],
             'version': mdata['version'],
             'build': mdata['build'],
             'depends': set(d.split(' ', 1)[0] for d in mdata['depends']),
             'modules': {'python': set(), 'r': set()},
             'eggs': set()}
    py_modules = pdata['modules']['python']
    r_modules = pdata['modules']['r']
    for fpath in mdata['files']:
        m1 = re.match(r'^lib/python\d.\d/(?:site-packages/|lib-dynload/|)(.*)$', fpath)
        if m1:
            stub = m1.groups()[0]
            m2 = re.match(r'^([^/]*[.](?:egg-info|dist-info|egg))/?(.*)', stub)
            if m2:
                eggname, stub = m2.groups()
                pdata['eggs'].add(eggname)
                if not eggname.endswith('.egg') or not stub:
                    continue
            if stub.endswith('__init__.py'):
                py_modules.add(dirname(stub).replace('/', '.'))
            elif stub.endswith(('.py', '.so')):
                py_modules.add(stub.rsplit('.', 1)[0].replace('/', '.'))
        m1 = re.match(r'lib/R/library/([^/]*)/', fpath)
        if m1:
            stub = m1.groups()[0]
            r_modules.add(stub)
        if fpath == 'bin/python':
            prefix = dirname(dirname(mpath))
            py_modules.update(get_python_builtins(join(prefix, fpath)))
    return pdata


def get_eggs(sp_dir):
    '''
    Returns a list of all egg files/directories in the given site-packages directory.
    
    Args:
        sp_dir (str): the site packages directory to scan
    Returns:
        list: a list of the egg files/dirs found in that directory.
    '''
    results = []
    for fn in os.listdir(sp_dir):
        if not fn.endswith(('.egg', '.egg-info', '.dist-info')):
            continue
        path = join(sp_dir, fn)
        if (isfile(path) or exists(join(path, 'METADATA')) or
            exists(join(path, 'PKG-INFO')) or
            exists(join(path, 'METADATA'))):
            results.append(fn)
    return set(results)


@functools.lru_cache()
def get_python_importables(path, level=0):
    modules = {}
    root_path = path.rstrip('/')
    while level > 0:
        root_path = dirname(root_path)
    root_len = len(root_path) + 1
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith('.')
                   and exists(join(root, d, '__init__.py'))]
        base_module = root[root_len:].replace('/', '.')
        for file in files:
            if file.startswith('.'):
                continue
            elif file.endswith('.pth'):
                fpath = join(root, file)
                with open(fpath, 'rt') as fp:
                    for npath in fp:
                        npath = abspath(join(root, npath.strip()))
                        modules.update(get_python_importables(npath))
            elif file.endswith(('.so', '.py')):
                fpath = join(root, file)
                if file == '__init__.py':
                    file = base_module
                else:
                    file = file.rsplit('.', 1)[0]
                    if base_module:
                        file = base_module + '.' + file
                modules[file] = fpath
    return modules


@functools.lru_cache()
def get_local_packages(path):
    packages = {}
    def _create(bname):
        if bname not in packages:
            packages[bname] = {'name': bname,
                               'version': '<local>',
                               'build': '<local>',
                               'modules': {'python': set(), 'r': set()},
                               'imports': {'python': set(), 'r': set()}}
        return packages[bname]
    for module, fpath in get_python_importables(path).items():
        bname = './' + module.split('.', 1)[0]
        if exists(join(path, bname) + '.py'):
            bname += '.py'
        pdata = _create(bname)
        imports, _ = find_file_imports(fpath)
        pdata['modules']['python'].add(module)
        pdata['imports']['python'].update(imp for imp in imports if not imp.startswith('.'))
    for fpath in glob(join(path, '*.R')) + glob(join(path, '*.ipynb')):
        if not basename(fpath).startswith('.'):
            bname = './' + basename(fpath)
            pdata = _create(bname)
            imports, language = find_file_imports(fpath)
            pdata['imports'][language] = imports
    return packages


@functools.lru_cache()
def environment_by_prefix(envdir, local=None):
    if local is not None:
        envdata = environment_by_prefix(envdir).copy()
        packages = envdata['packages'] = envdata['packages'].copy()
        imports = envdata['imports'] = envdata['imports'].copy()
        all_locals = get_local_packages(local)
        for name, package in all_locals.items():
            packages[name] = package.copy()
        for language in imports:
            imports_lang = imports[language] = imports[language].copy()
            for name, package in all_locals.items():
                for module in package['modules'][language]:
                    imports_lang[module] = name
        for name in all_locals:
            package = packages[name]
            depends = package['depends'] = set()
            for language, imports in package['imports'].items():
                imports_lang = envdata['imports'][language]
                for imod in imports:
                    dep = imports_lang.get(imod)
                    if dep is None and '.' in imod:
                        dep = imports_lang.get(imod.rsplit('.', 1)[0])
                    if dep is not None:
                        depends.add(dep)
        return envdata
    
    envname = basename(envdir)
    envdata = {'prefix': envdir}
    imports = envdata['imports'] = {'python': {}, 'r': {}}
    packages = envdata['packages'] = {}

    # Find all conda-managed modules and attach the conda package name to each.
    for file in glob(join(envdir, 'conda-meta', '*.json')):
        pdata = parse_conda_meta(file)
        pname = pdata['name']
        packages[pname] = pdata
        for language, mdata in pdata['modules'].items():
            for module in mdata:
                imports[language][module] = pname

    # Find all non-conda egg directories and determine package name and version
    # If a manifest exists, use that to remove imports from the unmanaged list
    eggfiles = set()
    for spdir in glob(join(envdir, 'lib', 'python*', 'site-packages')):
        eggfiles = get_eggs(spdir)
    for pdata in packages.values():
        eggfiles -= pdata['eggs']
    for eggfile in (): # eggfiles:
        pdata = parse_egg_info(join(spdir, eggfile))
        pname = pdata['name']
        packages[pdata['name']] = pdata
        for language, mdata in pdata['modules'].items():
            for module in mdata:
                imports[language][module] = pname

    # Construct reverse dependency info
    for pkg, pdata in packages.items():
        pdata['reverse'] = set()
    for pkg, pdata in packages.items():
        for dep in pdata['depends']:
            if dep in packages:
                packages[dep]['reverse'].add(pkg)

    return envdata


@functools.lru_cache()
def kernel_name_to_prefix(project_home, kernel_name):
    parent_dir, project_name = os.path.split(project_home)
    project_root, project_user = os.path.split(parent_dir)
    if '-' not in kernel_name:
        return None
    kernel_loc, language = kernel_name.rsplit('-', 1)
    if kernel_loc == 'conda-root':
        return join(config.WAKARI_HOME, 'anaconda')
    kernel_base = 'conda-env-anaconda-'
    if kernel_loc.startswith('conda-env-anaconda-'):
        return join(config.WAKARI_HOME, 'anaconda', 'envs', kernel_loc[len(kernel_base):])
    kernel_base = 'conda-env-{}-'.format(project_name)
    if kernel_loc.startswith(kernel_base):
        return join(project_home, 'envs', kernel_loc[len(kernel_base):])
    
    
def modules_to_packages(environment, modules, language):
    requested = set()
    missing = set()
    packages = environment['imports'][language]
    for module in modules:
        package = packages.get(module)
        while package is None and '.' in module:
            module = module.rsplit('.', 1)[0]
            package = packages.get(module)
        if package is None:
            missing.add(module)
        else:
            requested.add(package)
    return (requested, missing)
