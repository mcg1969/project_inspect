import logging
import functools
import json
import os

from . import config

logger = logging.getLogger(__name__.rsplit('.', 1)[0])

# If we're in a Jupyter notebook, we need to play some tricks
# in order to get the logger output to show up in the notebook.
try:
    from IPython import get_ipython
    if 'IPKernelApp' in get_ipython().config:
        import sys
        logger.handlers = [logging.StreamHandler(sys.stderr)]
except Exception:
    pass


LOG_ROOT = None


def set_log_root(fpath):
    global LOG_ROOT
    LOG_ROOT = os.path.abspath(fpath).rstrip('/') + '/'


def shortpath(fpath):
    global LOG_ROOT
    fpath = os.path.abspath(fpath)
    if LOG_ROOT is not None and fpath.startswith(LOG_ROOT):
        return fpath[len(LOG_ROOT):]
    return fpath


@functools.lru_cache()
def load_file(fpath):
    try:
        with open(fpath, 'rb') as fp:
            ndata = fp.read()
    except (IOError, OSError):
        logger.error('{}: CANNOT READ'.format(fpath))
        return None
    if fpath.endswith(('.ipynb', '.json')):
        try:
            result = json.loads(ndata)
        except:
            logger.error('{}: INVALID JSON'.format(fpath))
            return None
    else:
        result = ndata.decode("utf-8", "replace")
    logger.debug('        {}'.format(shortpath(fpath)))
    return result
