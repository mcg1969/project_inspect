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
from .utils import load_file

import logging
import pkg_resources
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


def get_python_path(prefix):
    '''
    Determines the standard python path for a given prefix.

    Args:
        prefix (str): path to the base of the Python environment.
    Returns:
        results: a list of paths.
    '''

    results = (glob(join(prefix, 'lib', 'python*.zip')) +
               glob(join(prefix, 'lib', 'python?.?')) +
               glob(join(prefix, 'lib', 'python?.?', 'lib-dynload')) +
               glob(join(prefix, 'lib', 'python?.?', 'site-packages')))
    return results


def parse_conda_meta(mpath):
    mdata = load_file(mpath) or {}
    fname, fversion, fbuild = basename(mpath).rsplit('.', 1)[0].rsplit('-', 2)
    pdata = {'name': mdata.get('name', fname),
             'version': mdata.get('version', fversion),
             'build': mdata.get('build', fbuild),
             'depends': set(d.split(' ', 1)[0] for d in mdata.get('depends', ())),
             'modules': {'python': set(), 'r': set()},
             'eggs': set(),
             'readable': bool(mdata)}
    py_modules = pdata['modules']['python']
    r_modules = pdata['modules']['r']
    for fpath in mdata.get('files', ()):
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
            elif stub.endswith('.py'):
                py_modules.add(stub.rsplit('.', 1)[0].replace('/', '.'))
            elif stub.endswith('.so'):
                parts = stub.split('.')[:-1]
                if parts[-1].startswith('cpython-'):
                    parts = parts[:-1]
                py_modules.add('.'.join(parts).replace('/', '.'))
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
    results = {}
    for fn in os.listdir(sp_dir):
        if not fn.endswith(('.egg-info', '.dist-info', '.egg', '.egg-link')):
            continue
        fullpath = os.path.join(sp_dir, fn)
        factory = pkg_resources.dist_factory(sp_dir, fn, False)
        try:
            dists = list(factory(fullpath))
        except Exception as e:
            logger.warning('Error reading eggs in {}:\n{}'.format(fullpath, e))
            dists = []
        pdata = {'name': None,
                 'version': None,
                 'build': '<pip>',
                 'depends': set(),
                 'modules': {'python': set(), 'r': set()}}
        results[fn] = pdata
        for dist in dists:
            if pdata['name'] is None:
                pdata['name'] = dist.project_name
                pdata['version'] = dist.version or '<dev>'
            pdata['depends'].update(r.name for r in dist.requires())
            sources = 'RECORD' if dist.has_metadata('RECORD') else 'SOURCES.txt'
            if dist.has_metadata(sources) and dist.has_metadata('top_level.txt'):
                sources = list(map(str.strip, dist.get_metadata(sources).splitlines()))
                top_level = list(map(str.strip, dist.get_metadata('top_level.txt').splitlines()))
                for top in top_level:
                    top_s = top + '/'
                    for src in sources:
                            src = src.split(',', 1)[0]
                            if src.endswith('__init__.py'):
                                src = dirname(src)
                            elif src.endswith(('.py', '.so')):
                                src = src[:-3]
                            else:
                                continue
                            pdata['modules']['python'].add(src.replace('/', '.'))
        if not pdata['name']:
            name, version = fn.rsplit('.', 1)[0], '<dev>'
            if fn.endswith('.dist-info'):
                name, version = fn.rsplit('-', 1)
            elif fn.endswith('.egg-info'):
                name, version, _ = fn.rsplit('-', 2)
            pdata['name'], pdata['version'] = name, version
    return results


@functools.lru_cache()
def get_python_importables(path, level=0):
    gen = ()
    modules = {}
    if isdir(path):
        gen = os.walk(path, followlinks=True)
    elif level > 0:
        for sfx in ('.py', '.so'):
            if isfile(path + sfx):
                gen = [(dirname(path), [], [basename(path) + sfx])]
                path = dirname(path)
                level -= 1
    else:
        return modules
    root_path = path.rstrip('/')
    while level > 0:
        root_path = dirname(root_path)
        level -= 1
    root_len = len(root_path) + 1
    for root, dirs, files in gen:
        dirs[:] = [d for d in dirs if not d.startswith('.')
                   and (exists(join(root, d, '__init__.py'))
                        or root == root_path and d.endswith('.egg'))]
        if root == root_path and root.endswith('.egg'):
            base_module = ''
        else:
            base_module = root[root_len:].replace('/', '.')
        for file in files:
            if file.startswith('.'):
                continue
            fpath = join(root, file)
            if file.endswith(('.pth', '.egg')) and not file.endswith('-nspkg.pth'):
                if root == root_path:
                    print(fpath)
                    pdata = parse_egg_info(fpath)
                    if pdata:
                        modules.update((k, fpath) for k in pdata['modules']['python'])
            elif file == '__init__.py':
                modules[base_module] = fpath
            elif file.endswith(('.so', '.py')):
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
        imports, _ = find_file_imports(fpath, submodules=True)
        pdata['modules']['python'].add(module)
        pdata['imports']['python'].update(imports)
    for fpath in glob(join(path, '*.R')) + glob(join(path, '*.ipynb')):
        if not basename(fpath).startswith('.'):
            bname = './' + basename(fpath)
            pdata = _create(bname)
            imports, language = find_file_imports(fpath, submodules=True)
            if language in pdata['imports']:
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
    eggfiles = {}
    for spdir in glob(join(envdir, 'lib', 'python*', 'site-packages')):
        eggfiles.update(get_eggs(spdir))
    for pdata in packages.values():
        for egg in pdata['eggs']:
            if egg in eggfiles:
                del eggfiles[egg]
    for eggfile, pdata in eggfiles.items():
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


def kernel_name_to_prefix(project_home, kernel_name):
    parent_dir, project_name = os.path.split(project_home)
    project_root, project_user = os.path.split(parent_dir)
    if '-' in kernel_name:
        kernel_loc, language = kernel_name.rsplit('-', 1)
        if kernel_loc == 'conda-root':
            return join(config.WAKARI_ROOT, 'anaconda')
        kernel_base = 'conda-env-anaconda-'
        if kernel_loc.startswith('conda-env-anaconda-'):
            return join(config.WAKARI_ROOT, 'anaconda', 'envs', kernel_loc[len(kernel_base):])
        kernel_base = 'conda-env-{}-'.format(project_name)
        if kernel_loc.startswith(kernel_base):
            return join(project_home, 'envs', kernel_loc[len(kernel_base):])
    
    
def modules_to_packages(environment, modules, language):
    requested = set()
    missing = set()
    packages = environment['imports'][language]
    # Make sure we get the package that imports the base language
    if language == 'python':
        lang_modules = ['math']
    else:
        lang_modules = ['stats']
    for module in list(modules) + lang_modules:
        package = packages.get(module)
        while package is None and '.' in module:
            module = module.rsplit('.', 1)[0]
            package = packages.get(module)
        if package is None:
            missing.add(module)
        else:
            requested.add(package)
    return (requested, missing)
