# This venv was created with --system-site-packages. A 2006 PyPI "uuid"
# backport (Python 2 syntax such as 1<<32L) sits in the system site-packages
# and modulegraph compiles that file, marks uuid as InvalidSourceModule, and
# omits the stdlib module from the frozen app.
import os
import uuid as _stdlib_uuid


def pre_find_module_path(api):
    api.search_dirs = [os.path.dirname(_stdlib_uuid.__file__)]
