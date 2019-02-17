from . import config
from .environments import environment_by_prefix, kernel_name_to_prefix, modules_to_packages
from .imports import find_python_imports, find_r_imports

from .utils import logger

from os.path import join, isdir, isfile, basename, dirname, exists, abspath
from textwrap import TextWrapper
from glob import glob

import os
import json
import pandas as pd


def visible_project_environments(project_home):
    project_home = join(project_home, 'envs', '')
    anaconda_root = join(config.WAKARI_HOME, 'anaconda')
    anaconda_envs = join(anaconda_root, 'envs', '')
    test_globs = [
            (join(project_home, 'default'), '{}'),
            (join(project_home, '*'), '{}'),
            (join(anaconda_envs, 'default'), 'anaconda:{}'),
            (join(anaconda_envs, '*'), 'anaconda:{}'),
            (anaconda_root, 'anaconda:root')]
    envs = []
    for test_glob, sname_format in test_globs:
        for file in sorted(glob(join(test_glob, 'conda-meta'))):
            if isdir(file):
                file = dirname(file)
                sname = sname_format.format(basename(file))
                if (file, sname) not in envs:
                    envs.append((file, sname))
    return envs


def find_notebook_metadata(fpath):
    language = nbenv = None
    fdir = dirname(fpath)
    with open(fpath, 'r') as fp:
        ndata = json.load(fp)
    kspec = ndata['metadata']['kernelspec']
    return kspec['language'].lower(), kspec['name']


def find_file_imports(fpath, project_home, prefixes):
    if isdir(fpath) and exists(join(fpath, '__init__.py')):
        language = 'python'
    elif fpath.endswith('.py'):
        language = 'python'
    elif fpath.endswith('.R'):
        language = 'r'
    elif fpath.endswith('.ipynb'):
        language, kspec = find_notebook_metadata(fpath)
        preferred = kernel_name_to_prefix(project_home, kspec)
        if preferred is not None:
            prefixes = [preferred]
    else:
        return (None, None, None)
    package_name = './' + basename(fpath)
    fdir = dirname(fpath)
    best = None
    for prefix in prefixes:
        environment = environment_by_prefix(prefix, fdir)
        modules = environment['packages'][package_name]['imports'][language]
        requested, missing = modules_to_packages(environment, modules, language)
        candidate = (prefix, language, requested, missing, len(missing))
        if best is None or candidate[-1] < best[-1]:
            best = candidate
        if best[-1] == 0:
            break
    return best[:-1]


def sort_candidates(depends):
    edges = {pkg: (deps.copy(), set(p for p, d in depends.items() if pkg in d))
             for pkg, deps in depends.items()}
    heads, tails = [], []
    while True:
        candidates = [(pkg.endswith('.ipynb'), len(deps), pkg)
                      for pkg, (deps, revs) in edges.items() if not revs]
        if candidates:
            dest = heads
        else:
            candidates = [(len(revs), pkg)
                          for pkg, (deps, revs) in edges.items() if not deps]
            if candidates:
                dest = tails
        if candidates:
            candidates = [p[-1] for p in sorted(candidates, reverse=True)]
            dest.extend(candidates)
            for pkg in candidates:
                del edges[pkg]
            for deps, revs in edges.values():
                deps.difference_update(candidates)
                revs.difference_update(candidates)
        else:
            break
    return heads + list(edges) + tails[::-1]


def find_project_imports(project_home):
    project_name = basename(project_home)
    project_user = basename(dirname(project_home))
    project_envs = join(project_home, 'envs', '')
    logger.info('Scanning project: {}/{}'.format(project_user, project_name))
    
    all_envs = {}
    for prefix, shortname in visible_project_environments(project_home):
        all_envs[prefix] = {
            'shortname': shortname, 
            'requested': set(), 
            'missing': {}}

    logger.info('  {} visible environments:'.format(len(all_envs)))
    for prefix, envrec in all_envs.items():
        logger.info('    {}: {}'.format(envrec['shortname'], prefix))
    if not all_envs:
        logger.info('    no project environments!')
        all_envs['@'] = {
            'shortname': '<empty>',
            'requested': set(),
            'missing': {}
        }

    wrapper = TextWrapper()
    wrapper.initial_indent = '    '
    wrapper.subsequent_indent = '      '
    def _wrap(t):
        return '\n'.join(wrapper.wrap(t))
    
    local_envs = {}
    local_depends = {}
    def _touch(pkg, env):
        if pkg not in local_envs:
            local_envs[pkg] = set()
        if env not in local_envs[pkg]:
            local_envs[pkg].add(env)
            # Dependencies must live in this env, too
            for dep in local_depends.get(pkg):
                _touch(dep, env)
    
    def _process(fpath, env_prefix, language, file_requests, file_missing):
        fdir = dirname(fpath)
        fbase = fpath[root_len:]
        local_imports = set()
        env_imports = set()
        envrec = all_envs[env_prefix]
        for pkg in file_requests:
            (local_imports if pkg.startswith('./') else env_imports).add(pkg)
        logger.info('  {}: {}, environment: {}'.format(fbase, language, envrec['shortname']))
        if env_imports:
            logger.info(_wrap('packages: {}'.format(', '.join(sorted(env_imports)))))
            envrec['requested'].update(env_imports)
        if local_imports:
            local_imports = sorted(pkg[2:] for pkg in local_imports)
            logger.info(_wrap('local imports: {}'.format(', '.join(local_imports))))
            for pkg in local_imports:
                _touch(pkg, env_prefix)
        if file_missing:
            logger.info(_wrap('unresolved: {}'.format(', '.join(sorted(file_missing)))))
            envrec['missing'].setdefault(language, set()).update(file_missing)
            
    root_len = len(project_home.rstrip('/')) + 1
    for root, dirs, files in os.walk(project_home, topdown=True):
        # Do not descend into dotted directories, Python package directories,
        # or the "envs" or "examples" directories
        dirs[:] = [file for file in dirs if not file.startswith('.')
                   and not exists(join(root, file, '__init__.py'))
                   and (root != project_home or file not in ('envs', 'examples'))]
        
        local_depends.clear()
        for pkg, pdata in environment_by_prefix('@', root)['packages'].items():
            local_depends[pkg[2:]] = set(dep[2:] for dep in pdata['depends'])
        scan_targets = sort_candidates(local_depends)
        
        visited = set()
        for file in scan_targets:
            visited.add(file)
            fpath = join(root, file)
            envs = local_envs.get(file) or all_envs
            env_prefix, language, t_requests, t_missing = find_file_imports(fpath, project_home, envs)
            _process(fpath, env_prefix, language, t_requests, t_missing)
            
    if any(envrec['requested'] or envrec['missing'] for envrec in all_envs.values()):
        logger.info('Summary:')
        for prefix, envrec in all_envs.items():
            if envrec['requested']:
                logger.info('  {} ({}):'.format(envrec['shortname'], prefix))
                logger.info(_wrap('packages: {}'.format(', '.join(sorted(envrec['requested'])))))
            for language, mset in envrec['missing'].items():
                logger.info(_wrap('missing {} imports: {}'.format(language, ', '.join(sorted(mset)))))
            
    return all_envs


def all_children(packages, children, field, filter=None):
    nresult = 0
    result = set(children)
    while nresult != len(result):
        nresult = len(result)
        for pkg in list(result):
            if filter is None or pkg not in filter: 
                result.update(packages.get(pkg, {}).get(field, ()))
    if filter is not None:
        result.intersection_update(filter)
    return result


def build_project_inventory(project_home):
    project_envs = join(project_home, 'envs', '')
    all_envs = find_project_imports(project_home)
    records = []
    for prefix, envrec in all_envs.items():
        imported = envrec['requested']
        if not imported and not prefix.startswith(project_envs):
            continue
        envdata = environment_by_prefix(prefix)
        packages = envdata.get('packages', {})
        required = imported.copy()
        while True:
            n_pkgs = len(required)
            for pkg in list(required):
                deps = packages.get(pkg, {}).get('depends', set)
                required.update(deps.intersection(packages))
            if len(required) == n_pkgs:
                break
        bases = {}
        for base in required.intersection(('r-base', 'python')):
            imported.add(base)
            bases[base] = all_children(packages, packages[base]['reverse'], 'reverse')
        envname = envrec['shortname']
        extra = set(packages) - required
        required -= imported
        for pkg in sorted(imported):
            pdata = packages[pkg]
            records.append((envname, pkg, pdata['version'], pdata['build'], True, True, ''))
        for pkg in sorted(required):
            pdata = packages[pkg]
            # If a package depends on another package transitively through one of the base
            # packages (python, r-base), we don't want it to show up in this list. This
            # reduces the noise in this list considerably.
            revs = all_children(packages, pdata['reverse'], 'reverse', bases)
            if not revs:
                revs = all_children(packages, pdata['reverse'], 'reverse', imported)
            revs = ', '.join(sorted(revs))
            records.append((envname, pkg, pdata['version'], pdata['build'], True, False, revs))
        for pkg in sorted(extra):
            pdata = packages[pkg]
            records.append((envname, pkg, pdata['version'], pdata['build'], False, False, ''))
    df = pd.DataFrame.from_records(records, columns=('env', 'package', 'version', 'build', 'required', 'requested', 'required_by'))
    return df


def build_user_inventory(username):
    if '/' in username:
        user_home = abspath(username)
        username = basename(user_home)
    else:
        user_home = join(config.PROJECT_HOME, username)
    df = []
    for projectrc in sorted(glob(join(user_home, '*', '.projectrc'))):
        project_home = dirname(projectrc)
        t_df = build_project_inventory(project_home)
        if t_df is not None:
            t_df.insert(0, 'project', basename(project_home))
            df.append(t_df)
    df = pd.concat(df) if df else None
    return df


def build_node_inventory(project_home=None):
    if project_home is None:
        project_home = config.PROJECT_HOME
    df = []
    for user_home in sorted(glob(join(project_home, '*'))):
        t_df = build_user_inventory(user_home)
        if t_df is not None:
            t_df.insert(0, 'user', basename(user_home))
            df.append(t_df)
    df = pd.concat(df) if df else None
    return df
