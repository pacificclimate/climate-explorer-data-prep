#!python
from argparse import ArgumentParser
import logging

from nchelpers import CFDataset

from dp.split_merged_climos import logger, split_merged_climos


def main(args):
    for filepath in args.filepaths:
        logger.info("")
        logger.info("Processing: {}".format(filepath))
        try:
            input_file = CFDataset(filepath)
        except Exception as e:
            logger.info("{}: {}".format(e.__class__.__name__, e))
        else:
            split_merged_climos(input_file, args.outdir)


def runme():
    parser = ArgumentParser(description="Create climatologies from CMIP5 data")
    parser.add_argument("filepaths", nargs="*", help="Files to process")
    log_level_choices = "NOTSET DEBUG INFO WARNING ERROR CRITICAL".split()
    parser.add_argument(
        "-l",
        "--loglevel",
        help="Logging level",
        choices=log_level_choices,
        default="INFO",
    )
    parser.add_argument("-o", "--outdir", required=True, help="Output folder")
    args = parser.parse_args()
    logger.setLevel(getattr(logging, args.loglevel))
    main(args)


if __name__ == "__main__":
    runme()
