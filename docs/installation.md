# Installation

`rdbiosonics` is a pure-Python package. Its only runtime dependencies are
[NumPy](https://numpy.org) and [xarray](https://docs.xarray.dev) (≥ 2024.10,
for {py:class}`xarray.DataTree`); plotting the example echogram also needs
[matplotlib](https://matplotlib.org).

It is not yet published to PyPI or conda-forge, so install it from a clone or
straight from GitHub.

## With pixi

[pixi](https://pixi.sh) is the recommended route for development. It builds
the whole environment from `pyproject.toml` — runtime dependencies, the
test / plotting / docs tools, and an editable install of the package itself:

```bash
git clone https://github.com/jklymak/rdbiosonics.git
cd rdbiosonics
pixi install
```

Predefined tasks are then available:

```bash
pixi run test       # run the test suite
pixi run echogram   # read a file and plot an echogram
pixi run docs       # build this documentation
```

Run anything else inside the environment with `pixi run <command>`, for
example `pixi run python`.

## With pip

Install into an existing environment with Python ≥ 3.11. From a clone:

```bash
git clone https://github.com/jklymak/rdbiosonics.git
cd rdbiosonics
pip install .
```

or directly from GitHub, without cloning:

```bash
pip install "git+https://github.com/jklymak/rdbiosonics.git"
```

Use `pip install -e .` for an editable install if you intend to modify the
code.

## Checking the install

```python
import rdbiosonics

print(rdbiosonics.__version__)
```
