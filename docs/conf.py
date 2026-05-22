"""Sphinx configuration for the rdbiosonics documentation."""

from importlib.metadata import version as _version

# -- Project information -----------------------------------------------------
project = "rdbiosonics"
author = "rdbiosonics contributors"
copyright = "2026, rdbiosonics contributors"

try:
    release = _version("rdbiosonics")
except Exception:  # package not installed (e.g. partial local build)
    release = "0.1.0"
version = release

# -- General configuration ---------------------------------------------------
extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

myst_enable_extensions = ["colon_fence", "deflist"]

napoleon_numpy_docstring = True
napoleon_google_docstring = False
autodoc_typehints = "description"
autodoc_member_order = "bysource"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable", None),
    "xarray": ("https://docs.xarray.dev/en/stable", None),
}

# -- HTML output -------------------------------------------------------------
html_theme = "furo"
html_title = f"rdbiosonics {release}"
html_static_path = ["_static"]
