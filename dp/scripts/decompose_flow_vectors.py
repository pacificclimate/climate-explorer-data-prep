#!python
"""This script takes a VIC-formatted parametrization file, including drainage flow
   direction information and outputs a file with the selected flow vectors decomposed 
   into normalized eastward and northward components formatted for ncWMS vector display. 
   The output netCDF will contain lat lon axes and two vector grid variables for
   ncWMS"""

import argparse
import logging

from netCDF4 import Dataset
import numpy as np
import sys
from dp.decompose_flow_vectors import (
    logger,
    decompose_flow_vectors,
    source_check,
    variable_check,
)
from dp.argparse_helpers import log_level_choices


def main(args):
    # check that source file is usable:
    source = Dataset(args.source_file, "r", format="NETCDF4")

    try:
        source_check(source)
    except (AttributeError, ValueError):
        sys.exit(1)

    try:
        variable_check(source, args.variable)
    except (AttributeError, ValueError):
        sys.exit(2)

    decompose_flow_vectors(source, args.dest_file, args.variable)


def runme():
    parser = argparse.ArgumentParser(
        description="Process an indexed flow direction netCDF into a vectored netCDF suitable for ncWMS display"
    )
    parser.add_argument("source_file", metavar="infile", help="source netCDF file")
    parser.add_argument("dest_file", metavar="outfile", help="destination netCDF file")
    parser.add_argument(
        "variable", metavar="variable", help="netCDF variable describing flow direction"
    )
    parser.add_argument(
        "-l",
        "--loglevel",
        help="Logging level",
        choices=log_level_choices,
        default="INFO",
    )

    args = parser.parse_args()
    logger.setLevel(getattr(logging, args.loglevel))
    main(args)


if __name__ == "__main__":
    runme()
