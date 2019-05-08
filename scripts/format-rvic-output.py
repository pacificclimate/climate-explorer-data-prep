#!python
'''This script takes a RVIC-formatted output file, as well as the hydromodel output
VICGL file RVIC took as input to generate it, and outputs a file that contains the same
data but matches the CF standards for discrete structured geometries and the PCIC
standards for routed streamflow data.

It is written for VICGL version 1.0 and RVIC version 1.1.1 and may need revision if
new versions of either come out.
'''
from argparse import ArgumentParser
import logging
import sys
from dp.format_rvic import logger, format_rvic_output
    
#TODO - consider supporting multiple files
def main(args):
    format_rvic_output(args.outdir, args.file, args.hydromodel, args.dry_run, args.instance_dim, args.cf_role)    
    
# TODO - consider letting user hint at instance dimensions, id variable and its value.
# TODO - required / optional stuff
if __name__== '__main__':
    parser = ArgumentParser(description='Format RVIC output to match CF discrete sampling geometry standards')
    parser.add_argument('-d', '--dry-run', action='store_true', 
                        help='check whether everything needed is present, without making any changes')
    parser.add_argument('-m', '--hydromodel', help='hydromodel file input to RVIC')
    parser.add_argument('-o', '--outdir', required=True, help='Output folder')
    parser.add_argument('-i', '--instance_dim', help='dimension representing data locations', default=None)
    parser.add_argument('-c', '--cf_role', help='a variable that provides a unique ID for each data location', default=None)
    parser.add_argument('file', help='RVIC output file to process')
    
    args = parser.parse_args()
    main(args)

