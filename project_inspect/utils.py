import logging
import functools
import json
import os

from textwrap import TextWrapper


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


wrapper = TextWrapper()
wrapper.initial_indent = '    '
wrapper.subsequent_indent = '      '


def wrap(t):
    return '\n'.join(wrapper.wrap(t))


def warn_file(fpath, msg, exc=None):
    if exc is not None:
        msg = msg + '\n' + wrap(str(exc))
    logger.warning('{}: {}'.format(shortpath(fpath), msg))


last_path = None


@functools.lru_cache()
def load_file(fpath):
    global last_path
    try:
        with open(fpath, 'rb') as fp:
            ndata = fp.read()
    except (IOError, OSError):
        logger.error('{}: CANNOT READ'.format(shortpath(fpath)))
        return None
    if fpath.endswith(('.ipynb', '.json')):
        try:
            result = json.loads(ndata)
        except Exception:
            if last_path != fpath:
                logger.error('{}: INVALID JSON'.format(shortpath(fpath)))
                last_path = fpath
            return None
    else:
        result = ndata.decode("utf-8", "replace")
    logger.debug('{}: loaded'.format(shortpath(fpath)))
    return result
