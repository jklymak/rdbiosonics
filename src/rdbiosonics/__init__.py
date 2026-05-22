"""rdbiosonics: read Biosonics DTX .DT4 echosounder files into xarray."""

from rdbiosonics.convert import dt4_to_netcdf
from rdbiosonics.rddtx import rddtx

__all__ = ["rddtx", "dt4_to_netcdf"]
__version__ = "0.1.0"
