import logging
import numpy as np
import os

from statistics import mean
from math import floor
from nchelpers import CFDataset

from dp.units_helpers import Unit


# Set up logging
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s',
                              "%Y-%m-%d %H:%M:%S")
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


def unique_shape(arrays):
    '''Ensure the arrays are the same shape'''
    shapes = set(map(np.shape, arrays))
    if not len(shapes) == 1:
        logger.warning('Arrays are not the same shape {}'.format(shapes))
        return False
    else:
        return True


def is_unique_value(values):
    '''Given a list transform into set and ensure there is only one unique
       value.
    '''
    return len(set(values)) == 1


def determine_freezing(unit):
    '''Given a unit determine which temperature describes freezing'''
    freezing = 0.0
    if unit.lower() == 'k':
        freezing = 273.15
    return freezing


def create_prsn_netcdf_from_source(src, dst):
    '''Using a precipiation netCDF as a template copy over the data applicable
       to prsn
    '''
    # Create the dimensions of the file
    for name, dim in src.dimensions.items():
        dst.createDimension(name, len(dim) if not dim.isunlimited() else None)

    # Copy the globals
    dst.setncatts({attr:src.getncattr(attr) for attr in src.ncattrs()})

    # Create the variables in the file
    for name, var in src.variables.items():
        dst.createVariable(name, var.dtype, var.dimensions)

        # Copy the variable attributes
        dst.variables[name].setncatts({attr:var.getncattr(attr) for attr in var.ncattrs()})

        # we will be replacing pr data with prsn data
        if name != 'pr':
            logger.debug('Copying {}'.format(name))
            dst.variables[name][:] = src.variables[name][:]
        else:
            continue


    # change pr metadata to prsn equivalents
    dst.renameVariable('pr', 'prsn')
    prsn_var = dst.variables['prsn']

    prsn_var.standard_name = 'snowfall_flux'
    prsn_var.long_name = 'Precipitation as Snow'

    to_delete = ['original_name', 'comment']
    for item in to_delete:
        if hasattr(prsn_var, item):
            prsn_var.delncattr(item)


def create_filepath_from_source(source, new_var, outdir):
    '''Using the source cmor_filename build a new output filepath with new_var
       and output directory.
    '''
    variable, *rest = source.cmor_filename.split('_')

    suffix = ''
    for var in rest:
        suffix += '_' + var

    if not os.path.exists(os.path.dirname(outdir)):
        os.makedirs(os.path.dirname(outdir))

    return os.path.join(outdir, new_var + suffix)


def has_required_vars(datasets, required_vars):
    ''' Given a list of datasets and a list of required variables, ensure the
        datasets contain all required variables.
    '''
    unique_vars = set()
    for dataset in datasets:
        for var in dataset.variables:
            unique_vars.add(var)

    for required_var in required_vars:
        if required_var not in unique_vars:
            logger.warning('Files do not contain required variables. required: {} have: {}'
                           .format(required_vars, unique_vars))
            return False

    return True


def matching_datasets(datasets):
    '''Given a list of datasets, match important metadata vars to ensure the
       datasets are compatible.
    '''
    required = {
        'project': [],
        'model': [],
        'institute': [],
        'experiment': [],
        'ensemble_member': []
    }

    for dataset in datasets:
        for attr in required.keys():
            required[attr].append(getattr(dataset.metadata, attr))

    for attr, lst in required.items():
        if not is_unique_value(lst):
            logger.warning('Metadata does not match for {}, {}'
                           .format(attr, lst))
            return False
    return True


def matching_temperature_units(tasmin, tasmax):
    '''Ensure the temperature datasets have matching units'''
    min_units = tasmin.variables['tasmin'].units
    max_units = tasmax.variables['tasmax'].units
    if not is_unique_value([min_units, max_units]):
        logger.warning('Temperature units do not match: tasmin: {} tasmax: {}'
                       .format(min_units, max_units))
        return False
    else:
        return True


def check_pr_units(pr):
    '''Ensure we have expected pr units'''
    valid_units = [
        Unit('kg / m**2 / s'),
        Unit('mm / s'),
        Unit('kg / d / m**2'),
        Unit('kg / m**2 / d')
    ]
    pr_variable = pr.variables['pr']
    pr_units = Unit.from_udunits_str(pr_variable.units)

    if pr_units not in valid_units:
        logger.warning('Unexpected precipitation units {}'.format(pr_units))
        return False
    else:
        return True


def preprocess_checks(pr, tasmin, tasmax, variables, required_vars):
    '''Perform all pre-processing checks'''
    return matching_datasets([pr, tasmin, tasmax]) and \
        has_required_vars([pr, tasmin, tasmax], required_vars) and \
        matching_temperature_units(tasmin, tasmax) and \
        check_pr_units(pr) and \
        unique_shape(variables)


def process_to_prsn(pr, tasmin, tasmax, max_len, output_dataset, freezing):
    '''Process precipitation data into snowfall data

       This method takes a precipitation, tasmin and tasmax file and uses them
       to produce a snowfall file.  Using a mean of the temperature files the
       script will look through all the cells in the datacube and mask any
       cells that are not freezing.  This mask applies to the precipiation file
       and thus we are left with cells where it was cold enough for snow.

       The input files are read in small chunks to avoid filling up all
       available memory and crashing the script.  Size refers to the chunk size
       being read in from the time dimension.  Example: Chunk read in
       (100, all lon, all lat).

       Parameters:
            pr (Variable): Variable object for precipitation
            tasmin (Variable): Variable object for tasmin
            tasmax (Variable): Variable object for tasmax
            max_len (int): The length of the precipitation variable to be used
                as the loop condition
            output_dataset (CFDataset): Dataset for prsn output
            freezing (float): Freezing temperature
    '''
    # TODO: Figure out a way to dynamically choose chunksize
    size = 100
    start = 0
    end = size

    if size > max_len:
        size = max_len

    while(start < max_len):
        if end > max_len:
            end = max_len

        pr_data = pr[start:end]
        tasmin_data = tasmin[start:end]
        tasmax_data = tasmax[start:end]

        means = np.mean([tasmin_data, tasmax_data], axis=0)
        prsn_data = np.where(means < freezing, pr_data, np.nan)

        logger.debug('Write prsn data to netCDF')
        output_dataset.variables['prsn'][start:end] = prsn_data

        start = end
        end += size


def generate_prsn_file(pr_filepath, tasmin_filepath, tasmax_filepath, outdir):
    '''Generate precipiation as snow data using pr, tasmin and tasmax.

       Parameters:
            pr_filepath (str): The filepath to desired precipiation data
            tasmin_filepath (str): The filepath to desired tasmin data
            tasmax_filepath (str): The filepath to desired tasmax data
            outdir (str): Output directory
    '''
    for filepath in [pr_filepath, tasmin_filepath, tasmax_filepath]:
        logger.info('Retrieving file: {}'.format(filepath))

    # datasets
    pr_dataset = CFDataset(pr_filepath)
    tasmin_dataset = CFDataset(tasmin_filepath)
    tasmax_dataset = CFDataset(tasmax_filepath)

    # variables
    pr_variable = pr_dataset.variables['pr']
    tasmin_variable = tasmin_dataset.variables['tasmin']
    tasmax_variable = tasmax_dataset.variables['tasmax']

    logger.info('Conducting pre-process checks')
    variables = [pr_variable, tasmin_variable, tasmax_variable]
    required_vars = ['pr', 'tasmin', 'tasmax']
    if not preprocess_checks(pr_dataset, tasmin_dataset, tasmax_dataset,
                             variables, required_vars):
        raise Exception('Pre-process checks have failed.')

    logger.info('Creating outfile')
    output_filepath = create_filepath_from_source(pr_dataset, 'prsn', outdir)
    with CFDataset(output_filepath, mode='w') as output_dataset:
        create_prsn_netcdf_from_source(pr_dataset, output_dataset)

    logger.info('Processing files in chunks')
    # by now we know that tasmin/tasmax have the same units
    freezing = determine_freezing(tasmin_variable.units)
    max_len = len(pr_variable)
    with CFDataset(output_filepath, mode='r+') as output_dataset:
        process_to_prsn(pr_variable, tasmin_variable, tasmax_variable,
                        max_len, output_dataset, freezing)

    logger.info('Output at: {}'.format(output_filepath))
    logger.info('Complete')
