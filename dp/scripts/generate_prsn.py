#!python
from argparse import ArgumentParser
import logging

from dp.generate_prsn import generate_prsn_file, dry_run
from nchelpers import CFDataset


def setup_logger(level):
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s',
                                  '%Y-%m-%d %H:%M:%S')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger = logging.getLogger('dp.generate_prsn')
    logger.addHandler(handler)
    logger.setLevel(level)


def main(args):
    filepaths = {
        'pr': args.prec,
        'tasmin': args.tasmin,
        'tasmax': args.tasmax
    }
    if args.dry_run:
        dry_run(filepaths)
    else:
        generate_prsn_file(filepaths, args.chunk_size, args.outdir, args.output_file)


def runme():
    parser = ArgumentParser(description='Create precipitation as snow data from pr, tasmin, tasmax')
    parser.add_argument('-d', '--dry-run', dest='dry_run', action='store_true')
    parser.add_argument('-c', '--chunk-size', dest='chunk_size', type=int, default=100,
                        help='Number of time slices to be read/written at a time')
    parser.add_argument('-p', '--prec', required=True, help='Precipitation file to process')
    parser.add_argument('-n', '--tasmin', required=True, help='Tasmin file to process')
    parser.add_argument('-x', '--tasmax', required=True, help='Tasmax file to process')
    parser.add_argument('-o', '--outdir', required=True, help='Output directory')
    parser.add_argument('-f', '--output-file', dest='output_file', default=None,
                        help='Optional custom name of output file')
    parser.add_argument('-l', '--loglevel', help='Logging level',
                        choices=['INFO', 'DEBUG', 'WARNING', 'ERROR'], default='INFO')
    args = parser.parse_args()
    setup_logger(args.loglevel)
    main(args)


if __name__ == '__main__':
    runme()
