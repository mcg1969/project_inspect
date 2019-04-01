from . import config
from .environments import environment_by_prefix, kernel_name_to_prefix, modules_to_packages
from .imports import find_python_imports, find_r_imports

from .utils import logger, load_file, shortpath, set_log_root
from .version import VersionSpec

from os.path import join, isdir, isfile, basename, dirname, exists, abspath
from textwrap import TextWrapper
from glob import glob

import os
import re
import json
import pandas as pd
import numpy as np


def visible_project_environments(project_home):
    project_home = join(project_home, 'envs', '')
    anaconda_root = join(config.WAKARI_ROOT, 'anaconda')
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
    ndata = load_file(fpath)
    try:
        kspec = ndata['metadata']['kernelspec']
        return kspec['language'].lower(), kspec['name']
    except:
        return None, None


def find_used_packages(fpath, project_home, prefixes):
    if isdir(fpath) and exists(join(fpath, '__init__.py')):
        language = 'python'
    elif fpath.endswith('.py'):
        language = 'python'
    elif fpath.endswith('.R'):
        language = 'r'
    elif fpath.endswith('.ipynb'):
        language, kspec = find_notebook_metadata(fpath)
        if language is None:
            return (None, None, None, None)
        preferred = kernel_name_to_prefix(project_home, kspec)
        if preferred is not None:
            prefixes = [preferred]
        else:
            logger.warning("Unexpected kernel name: {}\n  file: {}".format(kspec, fpath))
    else:
        return (None, None, None, None)
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
    
    wrapper = TextWrapper()
    wrapper.initial_indent = '    '
    wrapper.subsequent_indent = '      '
    def _wrap(t):
        return '\n'.join(wrapper.wrap(t))
    
    all_envs = {}
    for prefix, shortname in visible_project_environments(project_home):
        all_envs[prefix] = {
            'shortname': shortname, 
            'requested': set(), 
            'missing': {}}
    if all_envs:
        logger.info('  {} visible environments:'.format(len(all_envs)))
        for prefix, envrec in all_envs.items():
            logger.info('    {}: {}'.format(envrec['shortname'], shortpath(prefix)))
    else:
        logger.info('    no project environments!')
        all_envs['@'] = {
            'shortname': '<empty>',
            'requested': set(),
            'missing': {}
        }

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
        if env_prefix is None:
            logger.info('  {}: empty notebook'.format(fbase))
            return
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
                   and (root != project_home or file not in ('envs', 'pkgs', 'examples'))]
        
        local_depends.clear()
        for pkg, pdata in environment_by_prefix('@', root)['packages'].items():
            local_depends[pkg[2:]] = set(dep[2:] for dep in pdata['depends'])
        scan_targets = sort_candidates(local_depends)
        
        for file in scan_targets:
            fpath = join(root, file)
            envs = local_envs.get(file) or all_envs
            env_prefix, language, t_requests, t_missing = find_used_packages(fpath, project_home, envs)
            _process(fpath, env_prefix, language, t_requests, t_missing)
            
    if any(envrec['requested'] or envrec['missing'] for envrec in all_envs.values()):
        logger.info('Summary:')
        for prefix, envrec in all_envs.items():
            if envrec['requested']:
                logger.info('  {} ({}):'.format(envrec['shortname'], shortpath(prefix)))
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


COLUMNS = ('owner', 'project', 'environment', 'package', 'version',
           'build', 'required', 'requested', 'required_by')


def _build_df(records):
    df = pd.DataFrame.from_records(records, columns=COLUMNS)
    df['required'] = df['required'].astype('bool')
    df['requested'] = df['requested'].astype('bool')
    return df


def filter_data(df, packages):
    if not packages:
        return df
    mask = np.zeros(len(df), dtype=bool)
    for package in packages:
        spec = re.match(r'^([A-Za-z0-9-_.]+)\s*(.*)', package)
        if not spec:
            raise RuntimeError('Invalid package spec: {}'.format(package))
        name, version = spec.groups()
        t_mask = df['package'] == name
        if t_mask.any() and version:
            vspec = VersionSpec(version)
            t2_mask = df['version'][t_mask].apply(vspec.match).values
            t_mask[t_mask] = t2_mask
        mask = mask | t_mask
    return df[mask]


def validate_summarize(level):
    sep = '_' if '_' in level else '/'
    parts = set(level.lower().split(sep))
    project_choices = {'all', 'node', 'owner', 'project', 'environment'} & parts
    package_choices = {'all', 'package', 'version'} & parts
    if len(project_choices) == 2:
        project_choices.discard('all')
    if len(package_choices) == 2:
        package_choices.discard('all')
    unknown = set(parts) - package_choices - project_choices
    if len(project_choices) > 1 or len(package_choices) > 1 or unknown:
        raise RuntimeError('Invalid summary type: {}'.format(level))
    return ''.join(project_choices), ''.join(package_choices)


def summarize_data(data, level):
    project_group, package_group = validate_summarize(level)

    def _summary(data):
        n_owners = len(data['owner'].drop_duplicates())
        n_projects = len(data[['owner', 'project']].drop_duplicates())
        n_envs = len(data[['owner', 'project', 'environment']].drop_duplicates())
        packages = data[['package', 'version'] if package_group == 'version' else ['package']]
        n_required = sum(data.required)
        n_requested = sum(data.requested)
        n_python = sum(data.package == 'python')
        n_r = sum(data.package == 'r-base')
        return (n_owners, n_projects, n_envs, n_required, n_requested, n_python, n_r)
    columns = ('n_owners', 'n_projects', 'n_environments', 'n_required', 'n_requested', 'n_python', 'n_r')

    if project_group in ('', 'all', 'node'):
        project_group = 'node'
        grouping = []
    elif project_group == 'owner':
        grouping = ['owner']
    elif project_group == 'project':
        grouping = ['owner', 'project']
    else:
        grouping = ['owner', 'project', 'environment']

    left, right = len(grouping), 5
    if package_group in ('', 'all'):
        right = 7
    elif package_group == 'package':
        grouping.append('package')
    else:
        grouping.extend(('package', 'version'))

    records = []
    if not grouping:
        records.append(_summary(data))
    else:
        for group, group_data in data.groupby(grouping):
            results = _summary(group_data)
            record = list(group) if isinstance(group, tuple) else [group]
            record.extend(results[left:right])
            records.append(record)
    df = pd.DataFrame(records, columns=grouping + list(columns[left:right]))
    return df


def build_project_inventory(owner_name, project_name=None, project_root=None, records_only=False):
    if '/' in owner_name:
        project_home = abspath(owner_name)
        project_name = basename(project_home)
        owner_name = basename(dirname(project_home))
    elif project_name is None:
        raise RuntimeError('The name of the project is missing')
    else:
        if project_root is None:
            project_root = config.PROJECT_ROOT
        project_home = join(abspath(project_root), owner_name, project_name)
    set_log_root(project_home)
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
            records.append((owner_name, project_name, envname, pkg, pdata['version'], pdata['build'], True, True, ''))
        for pkg in sorted(required):
            pdata = packages[pkg]
            # If a package depends on another package transitively through one of the base
            # packages (python, r-base), we don't want it to show up in this list. This
            # reduces the noise in this list considerably.
            revs = all_children(packages, pdata['reverse'], 'reverse', bases)
            if not revs:
                revs = all_children(packages, pdata['reverse'], 'reverse', imported)
            revs = ', '.join(sorted(revs))
            records.append((owner_name, project_name, envname, pkg, pdata['version'], pdata['build'], True, False, revs))
        for pkg in sorted(extra):
            pdata = packages[pkg]
            records.append((owner_name, project_name, envname, pkg, pdata['version'], pdata['build'], False, False, ''))
    return records if records_only else _build_df(records)


def build_owner_inventory(owner_name, project_root=None, records_only=False):
    if '/' in owner_name:
        owner_home = owner_name
    else:
        if project_root is None:
            project_root = config.PROJECT_ROOT
        owner_home = join(abspath(project_root), owner_name)
    records = []
    owner_home = abspath(owner_home)
    set_log_root(owner_home)
    for projectrc in sorted(glob(join(owner_home, '*', '.projectrc'))):
        records.extend(build_project_inventory(dirname(projectrc), records_only=True))
    return records if records_only else _build_df(records)


def build_node_inventory(project_root=None, records_only=False):
    if project_root is None:
        project_root = config.PROJECT_ROOT
    records = []
    project_root = abspath(project_root)
    set_log_root(project_root)
    for owner_home in sorted(glob(join(project_root, '*'))):
        records.extend(build_owner_inventory(owner_home, records_only=True))
    return records if records_only else _build_df(records)
