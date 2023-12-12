#!python
"""Update NetCDF metadata from a YAML file.

WARNING: THIS SCRIPT MODIFIES THE ORIGINAL FILE.

See README for details of update specification file (YAML format).
"""
from argparse import ArgumentParser
import logging

from dp.argparse_helpers import log_level_choices
from dp.update_metadata import logger, main


def runme():
    parser = ArgumentParser(
        description="Update NetCDF file attributes based on an updates "
        "specification file"
    )
    parser.add_argument(
        "-l",
        "--loglevel",
        help="Logging level",
        choices=log_level_choices,
        default="INFO",
    )
    parser.add_argument(
        "-u", "--updates", required=True, help="File containing updates"
    )
    parser.add_argument("ncfile", help="NetCDF file to update")
    args = parser.parse_args()
    logger.setLevel(getattr(logging, args.loglevel))
    main(args)


if __name__ == "__main__":
    runme()
