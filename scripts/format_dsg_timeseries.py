#!python
'''This script takes a netCDF file and outputs a version that matches the CF
discrete sampling geometry timseries standards. Inputs are unchanged; a new
file is generated.

Features of the DSG standard:
  * 1 "Instance Dimension" counts the # of sites at which data is recorded
  * 1+ "Instance variables" provide information about each site
  * 1 instance variable is the "cf_role" variable: a unique ID for each site

The original use case was for RVIC version 1.1.1 history files, so there are
optional processes intended to accomodate that case and bring RVIC metadata in
line with PCIC standards. These processes are only applied if relevant
attributes are detected but shouldn't have weird effects on non-RVIC files
unless those files coincidentally share metadata attribute or variable names.
'''
from argparse import ArgumentParser
import logging
import sys
import os
from dp.format_dsg_timeseries import logger, format_dsg_timeseries


def main(args):
    format_dsg_timeseries(args.outdir, args.file, args.metadata,
                          args.dry_run, args.instance_dim, args.cf_role)


# TODO - check file existence before calling format_dsg_timeseries?
if __name__ == '__main__':
    parser = ArgumentParser(description='Format netCDF as CF DSG Timeseries')
    parser.add_argument('-d', '--dry-run', action='store_true',
                        help='check requirements, does not output file')
    parser.add_argument('-m', '--metadata', default=[], action='append',
                        help='[prefix,]file for extra metadata attributes')
    parser.add_argument('-o', '--outdir', required=True, help='Output folder')
    parser.add_argument('-i', '--instance_dim', default=None,
                        help='netCDF dimension representing data locations')
    parser.add_argument('-c', '--cf_role', default=None,
                        help='netCDF variable with unique IDs for locations')
    parser.add_argument('file', help='netCDF file to process')

    args = parser.parse_args()
    # make sure input file exists
    if not os.path.isfile(args.file):
        raise Exception("Data file not found: {}".format(args.file))
    
    # standardize output directory format - strip trailing slash if present
    args.outdir = args.outdir.rstrip('/')

    metadata = []
    for m in args.metadata:
        m_list = m.split(',')
        if len(m_list) == 1:  # no prefix given by user
            m_list = m_list.insert(0, None)
        # make sure eupplemental metadata file exists
        if not os.path.isfile(m_list[1]):
            raise Exception("Metadata file not found: {}".format(m_list[1]))
        metadata.append(m_list)
    args.metadata = metadata
    main(args)
