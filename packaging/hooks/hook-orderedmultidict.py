# orderedmultidict reads __version__.py from disk in __init__.py instead of
# importing it. PyInstaller archives .py files, so that open() fails unless
# the file is also copied into the bundle as data.
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("orderedmultidict", include_py_files=True)
