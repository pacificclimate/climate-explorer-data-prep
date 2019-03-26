import logging
import numpy as np
import os

from statistics import mean
from math import floor
from nchelpers import CFDataset
from pint import UnitRegistry

from dp.units_helpers import Unit


# Set up logging
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s',
                              "%Y-%m-%d %H:%M:%S")
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

ureg = UnitRegistry()
Q_ = ureg.Quantity


def chunk_generator(max_len):
    '''Yield the start and end indices for chunking through a given array length'''
    size = 100
    start = 0
    end = size

    if size > max_len:
        size = max_len

    while(start < max_len):
        if end > max_len:
            end = max_len

        yield start, end

        start = end
        end += size


def unique_shape(arrays):
    '''Ensure the arrays are the same shape'''
    shapes = {a.shape for a in arrays}
    if not len(shapes) == 1:
        logger.warning('Arrays are not the same shape {}'.format(shapes))
        return False
    else:
        return True


def is_unique_value(values):
    '''Given a list ensure there is only one unique value'''
    return np.unique(values).size == 1


def determine_freezing(unit):
    '''Given a unit determine which temperature describes freezing'''
    freezing = Q_(0.0, ureg.degC)

    temp_unit = ureg.parse_units(unit)
    logger.info('Temperature units: {}'.format(temp_unit))
    if temp_unit != 'degC':
        freezing.to(temp_unit)

    return freezing


def create_prsn_netcdf_from_source(src, dst):
    '''Using a precipiation netCDF as a template copy over the data applicable
       to prsn
    '''
    # Create the dimensions of the file
    for name, dim in src.dimensions.items():
        dst.createDimension(name, len(dim) if not dim.isunlimited() else None)

    # Copy the globals
    unwanted_globals = [
        'history',
    ]
    dst.setncatts({attr:src.getncattr(attr)
                   for attr in src.ncattrs() if attr not in unwanted_globals})

    # Create the variables in the file
    for name, var in src.variables.items():
        dst.createVariable(name, var.dtype, var.dimensions)

        # Copy the variable attributes
        dst.variables[name].setncatts({attr:var.getncattr(attr) for attr in var.ncattrs()})

        # we will be replacing pr data with prsn data
        if name == 'pr':
            continue
        logger.debug('Copying {}'.format(name))
        dst.variables[name][:] = src.variables[name][:]


    # change pr metadata to prsn equivalents
    dst.renameVariable('pr', 'prsn')
    prsn_var = dst.variables['prsn']

    prsn_var.standard_name = 'snowfall_flux'
    prsn_var.long_name = 'Precipitation as Snow'

    to_delete = ['original_name', 'comment']
    for item in to_delete:
        if hasattr(prsn_var, item):
            prsn_var.delncattr(item)


def custom_filepath(directory, file):
    '''Check if directory exists and return the filepath'''
    if not os.path.exists(os.path.dirname(directory)):
        os.makedirs(os.path.dirname(directory))

    return os.path.join(directory, file)


def create_filepath_from_source(source, new_var, outdir):
    '''Using the source cmor_filename build a new output filepath with new_var
       and output directory.
    '''
    variable, *rest = source.cmor_filename.split('_')

    suffix = ''
    for var in rest:
        suffix += '_' + var

    return custom_filepath(outdir, new_var + suffix)


def has_required_vars(datasets, required_vars):
    ''' Given a list of datasets and a list of required variables, ensure the
        datasets contain all required variables.
    '''
    unique_vars = set()
    for dataset in datasets:
        for var in dataset.variables:
            unique_vars.add(var)

    required_vars = set(required_vars)
    if required_vars.intersection(unique_vars) == required_vars:
        return True
    else:
        logger.warning('Files do not contain required variables. required: {} have: {}'
                       .format(required_vars, unique_vars))
        return False


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
    '''Check if temperature datasets have matching units,
       if not convert tasmax units
    '''
    min_units = ureg.parse_units(tasmin.units)
    max_units = ureg.parse_units(tasmax.units)

    if not is_unique_value([min_units, max_units]):
        logger.warning('Converting tasmax units: {} to match tasmin units: {}'
                       .format(max_units, min_units))

        # tasmax units converted to tasmin units
        converted_tasmax = np.zeros(np.shape(tasmax))
        for start, end in chunk_generator(len(tasmax)):
            try:
                converted_var[start:end] = (tasmax[start:end] * Q_(1.0, max_units)).to(min_units).magnitude
            except:
                raise Exception('Error occured while converting units')
        return converted_tasmax
    else:
        logger.info('Units match')
        return tasmax


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
    '''Perform all pre-processing checks, if any check(s) have failed raise Exception'''
    checks = {
        'matching_datasets': matching_datasets([pr, tasmin, tasmax]),
        'has_required_vars': has_required_vars([pr, tasmin, tasmax], required_vars),
        'check_pr_units': check_pr_units(pr),
        'unique_shape': unique_shape(variables)
    }
    failures = [check for check, result in checks.items() if not result]
    if failures:
        for failure in failures:
            logger.exception('{} check failed'.format(failure))
        raise Exception('Pre-process checks have failed')


def process_to_prsn(pr, tasmin, tasmax, output_dataset):
    '''Process precipitation data into snowfall data

       This method takes a precipitation, tasmin and tasmax file and uses them
       to produce a snowfall file.  Using a mean of the temperature files the
       script will look through all the cells in the datacube and 0 any cells
       that are not freezing.  This mask applies to the precipiation file and
       thus we are left with cells where it was cold enough for snow.

       The input files are read in small chunks to avoid filling up all
       available memory and crashing the script.  Size refers to the chunk size
       being read in from the time dimension.  Example: Chunk read in
       (100, all lon, all lat).

       Parameters:
            pr (Variable): Variable object for precipitation
            tasmin (Variable): Variable object for tasmin
            tasmax (Variable): Variable object for tasmax
            output_dataset (CFDataset): Dataset for prsn output
    '''
    freezing = determine_freezing(tasmin.units)
    for start, end in chunk_generator(len(pr)):
        pr_data = pr[start:end]
        tasmin_data = tasmin[start:end]
        tasmax_data = tasmax[start:end]

        means = np.mean([tasmin_data, tasmax_data], axis=0)
        prsn_data = np.where(means < freezing, pr_data, 0)
        output_dataset.variables['prsn'][start:end] = prsn_data


def generate_prsn_file(pr_filepath, tasmin_filepath, tasmax_filepath, outdir, output_file=None):
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
    preprocess_checks(pr_dataset, tasmin_dataset, tasmax_dataset, variables,
                      required_vars)

    logger.info('Checking temperature units')
    tasmax_variable = matching_temperature_units(tasmin_variable, tasmax_variable)

    logger.info('Creating outfile')
    if output_file:
        output_filepath = custom_filepath(outdir, output_file)
    else:
        output_filepath = create_filepath_from_source(pr_dataset, 'prsn', outdir)

    with CFDataset(output_filepath, mode='w') as output_dataset:
        create_prsn_netcdf_from_source(pr_dataset, output_dataset)

    logger.info('Processing files in chunks')
    with CFDataset(output_filepath, mode='r+') as output_dataset:
        process_to_prsn(pr_variable, tasmin_variable, tasmax_variable,
                        output_dataset)

    logger.info('Output at: {}'.format(output_filepath))
    logger.info('Complete')
