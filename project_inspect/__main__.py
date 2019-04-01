import os
import argparse

from . import config
from .utils import logger, set_log_root


# Arguments for command line
parser = argparse.ArgumentParser(
    prog="python -m project_inspect",
    description="AE4 project inspection utilities.")
parser.add_argument(
    "--log",
    help="set log level",
    choices=['error', 'warning', 'info', 'debug'],
    action="store")
parser.add_argument(
    "--owner",
    help="Limit the inventory to a single user.",
    action="store")
parser.add_argument(
    "--project",
    help="Limit the inventory to a single project. Must be accompanied by --user.",
    action="store")
parser.add_argument(
    "--output", '-o',
    help="Deliver the output to the named file instead of standard output.",
    action="store")
parser.add_argument(
    "--root",
    help="Specify the root directory of the project store.",
    action="store")
parser.add_argument(
    "--package", action="append",
    help="""Limit the list/summary to the given package. The argument can
simply be the name of a package, or a conda-style package/version spec;
e.g., 'pandas<0.20'. Multiple --package arguments can be supplied.""")
parser.add_argument(
    "--package-file", action="store",
    help="""Read a list of package specs from the given file. One spec
should be supplied per line. The spec can simply be the name of a package,
or a conda-style package/version spec; e.g., 'pandas<0.20'.""")
parser.add_argument(
    "--summarize", '-s',
    help="""Optionally summarize the inventory. Choices include
project groupings (node, owner, project, environment) and package
groupings (package, version). You may combine one choice from each
category as well by separating them with a slash; e.g., owner/package.
Unsummarized data is equivalent to environment/version.""",
    action="store")


def main(**kwargs):
    loglev = (kwargs.get('log') or 'warning').upper()
    import logging
    logging.basicConfig(format='%(message)s')
    logger.setLevel(getattr(logging, loglev))
    root = kwargs.get('root')
    if root:
        root = os.path.abspath(root)
        set_log_root(root)
    else:
        root = config.PROJECT_ROOT
    logger.info('Project root: {}'.format(root))
    from . import project
    uname = kwargs.get('owner')
    pname = kwargs.get('project')
    if uname:
        if pname:
            df = project.build_project_inventory(uname, pname, root)
        else:
            df = project.build_owner_inventory(uname, root)
    elif pname:
        raise RuntimeError('Must supply --owner with --project')
    else:
        df = project.build_node_inventory(root)
    packages = kwargs.get('package') or []
    package_file = kwargs.get('package_file')
    if package_file:
        with open(package_file, 'rt') as fp:
            packages.extend(spec for spec in map(str.strip, fp) if spec)
    if packages:
        df = project.filter_data(df, packages)
    summary = kwargs.get('summarize')
    if summary:
        df = project.summarize_data(df, summary)
    fname = kwargs.get('output')
    if fname and fname != '-':
        df.to_csv(fname, index=None)
    else:
        print(df.to_csv(index=None))
    return 0


main(**(parser.parse_args().__dict__))