from argparse import ArgumentParser
import logging
import sys

from nchelpers import CFDataset, standard_climo_periods
from dp.argparse_helpers import strtobool, log_level_choices
from dp.generate_climos import logger, generate_climos, dry_run_handler


def main(args):
    if args.dry_run:
        logger.info("DRY RUN")
        for filepath in args.filepaths:
            dry_run_handler(filepath, args.climo)
        sys.exit(0)

    for filepath in args.filepaths:
        generate_climos(
            filepath,
            args.outdir,
            args.operation,
            climo=args.climo,
            convert_longitudes=args.convert_longitudes,
            split_vars=args.split_vars,
            split_intervals=args.split_intervals,
            resolutions=args.resolutions,
        )


def runme():
    parser = ArgumentParser(description="Create climatologies from CMIP5 data")
    parser.add_argument("filepaths", nargs="*", help="Files to process")
    parser.add_argument(
        "-c",
        "--climo",
        default=[],
        action="append",
        choices=standard_climo_periods().keys(),
        help="Climatological periods to generate. "
        "Defaults to all available in the input file. "
        "Ex: -c 6190 -c 7100 -c 8100 -c 2020 -c 2050 -c 2080",
    )
    parser.add_argument(
        "-r",
        "--resolutions",
        default=[],
        action="append",
        choices=["yearly", "seasonal", "monthly"],
        help="Temporal resolutions of multiyear means to generate. "
        'Defaults to ["yearly", "seasonal", "monthly"] '
        "Ex: -r yearly -r seasonal",
    )
    parser.add_argument(
        "-l",
        "--loglevel",
        help="Logging level",
        choices=log_level_choices,
        default="INFO",
    )
    parser.add_argument("-n", "--dry-run", dest="dry_run", action="store_true")
    parser.add_argument(
        "-g",
        "--convert-longitudes",
        type=strtobool,
        dest="convert_longitudes",
        help="Transform longitude range from [0, 360) to [-180, 180)",
    )
    parser.add_argument(
        "-v",
        "--split-vars",
        type=strtobool,
        dest="split_vars",
        help="Generate a separate file for each dependent variable in the file",
    )
    parser.add_argument(
        "-i",
        "--split-intervals",
        type=strtobool,
        dest="split_intervals",
        help="Generate a separate file for each climatological period",
    )
    parser.add_argument("-o", "--outdir", required=True, help="Output folder")
    parser.add_argument(
        "-p",
        "--operation",
        required=True,
        help="Data operation for the file",
        choices=["mean", "std"],
    )
    parser.set_defaults(
        dry_run=False, convert_longitudes=True, split_vars=True, split_intervals=True
    )
    args = parser.parse_args()
    if not args.climo:
        args.climo = standard_climo_periods().keys()
    if not args.resolutions:
        args.resolutions = ["yearly", "seasonal", "monthly"]
    logger.setLevel(getattr(logging, args.loglevel))
    main(args)


if __name__ == "__main__":
    runme()
