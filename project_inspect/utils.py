import logging

logger = logging.getLogger(__name__.rsplit('.', 1)[0])

# If we're in a Jupyter notebook, we need to play some tricks
# in order to get the logger output to show up in the notebook.
try:
    from IPython import get_ipython
    if 'IPKernelApp' in get_ipython().config:
        import sys
        logger.handlers = [logging.StreamHandler(sys.stderr)]
        logger.setLevel(logging.INFO)
except Exception:
    pass
