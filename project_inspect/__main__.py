import argparse


# Arguments for command line
parser = argparse.ArgumentParser(
    prog="python -m project_inspect",
    description="AE4 project inspection utilities.")
parser.add_argument(
    "-v", "--verbose",
    help="show more output",
    action="store_true")
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
    "--root", '-r',
    help="Specify the root directory of the project store.",
    action="store")
parser.add_argument(
    "--summarize", '-s',
    help="""Optionally summarize the inventory. Choices include
project groupings (node, owner, project, environment) and package
groupings (package, version). You may combine one choice from each
category as well by separating them with a slash; e.g., owner/package.
Unsummarized data is equivalent to environment/version.""",
    action="store")


def main(**kwargs):
    if kwargs.get('verbose'):
        import logging
        from .utils import logger
        logger.setLevel(logging.DEBUG)
    root = kwargs.get('root')
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