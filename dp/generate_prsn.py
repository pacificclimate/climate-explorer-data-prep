import logging
import numpy as np
import os

from statistics import mean
from math import floor
from nchelpers import CFDataset
from nchelpers.iteration import opt_chunk_shape, chunk_slices
from pint import UnitRegistry

from dp.units_helpers import Unit


# Pint Setup
ureg = UnitRegistry()
Q_ = ureg.Quantity

# Get Logger
logger = logging.getLogger(__name__)


def dry_run(filepaths):
    '''Perform metadata checks on the input files'''
    logger.info('Dry Run')
    for filepath in filepaths.values():
        logger.info('')
        logger.info('File: {}'.format(filepath))
        try:
            dataset = CFDataset(filepath)
        except Exception as e:
            logger.exception('{}: {}'.format(e.__class__.__name__, e))

        for attr in 'project model institute experiment ensemble_member'.split():
            try:
                logger.info('{}: {}'.format(attr, getattr(dataset.metadata, attr)))
            except Exception as e:
                logger.info('{}: {}: {}'.format(attr, e.__class__.__name__, e))
        logger.info('dependent_varnames: {}'.format(dataset.dependent_varnames()))


def unique_shape(arrays):
    '''Ensure each array in dict is the same shape'''
    shapes = {a.shape for a in arrays.values()}
    return len(shapes) == 1


def is_unique_value(values):
    '''Given a list ensure there is only one unique value'''
    return np.unique(values).size == 1


def pr_freezing_from_units(unit):
    '''Given a unit determine which temperature describes freezing'''
    freezing = Q_(0.0, ureg.degC)

    temp_unit = str(ureg.parse_units(unit))
    if temp_unit != 'degC':
        freezing = freezing.to(temp_unit)

    return freezing.magnitude


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
    for dataset in datasets.values():
        for var in dataset.variables:
            unique_vars.add(var)

    required_vars = set(required_vars)
    return required_vars.intersection(unique_vars) == required_vars


def matching_datasets(datasets):
    '''Given a dict of datasets, match important metadata vars to ensure the
       datasets are compatible.
    '''
    required = {
        'project': [],
        'model': [],
        'institute': [],
        'experiment': [],
        'ensemble_member': []
    }

    for dataset in datasets.values():
        for attr in required.keys():
            required[attr].append(getattr(dataset.metadata, attr))

    for attr, lst in required.items():
        if not is_unique_value(lst):
            logger.warning('Metadata does not match for {}, {}'
                           .format(attr, lst))
            return False
    return True


def convert_temperature_units(data, units_from, units_to):
    '''Given an array of temperature values convert data to desired units'''
    units_from = ureg.parse_units(units_from)
    units_to = ureg.parse_units(units_to)

    logger.debug('Converting temperature units from {}: to: {}'
                 .format(units_from, units_to))
    return (data * Q_(1.0, units_from)).to(units_to).magnitude


def check_pr_units(pr_units):
    '''Ensure we have expected pr units'''
    valid_units = [
        Unit('kg / m**2 / s'),
        Unit('mm / s'),
        Unit('kg / d / m**2'),
        Unit('kg / m**2 / d')
    ]
    units = Unit.from_udunits_str(pr_units)
    return units in valid_units


def preprocess_checks(datasets, variables, required_vars):
    '''Perform all pre-processing checks and return a dict of failed checks (if any)'''
    checks = {
        'matching_datasets': matching_datasets(datasets),
        'has_required_vars': has_required_vars(datasets, required_vars),
        'check_pr_units': check_pr_units(variables['pr'].units),
        'unique_shape': unique_shape(variables)
    }
    return {check: result for check, result in checks.items() if not result}


def process_to_prsn(variables, output_dataset, chunk_size):
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
            variables (dict): Dictionary containing three Variable objects
                (pr, tasmin, tasmax)
            output_dataset (CFDataset): Dataset for prsn output
            chunk_size (int): Number of timeslices to be read/written at a time
    '''
    tasmin_units = variables['tasmin'].units
    tasmax_units = variables['tasmax'].units
    matching_temp_units = is_unique_value([variables['tasmin'].units,
                                           variables['tasmax'].units])
    freezing = pr_freezing_from_units(tasmin_units)

    max_chunk_len = chunk_size * variables['pr'].shape[1] * variables['pr'].shape[2]
    opt_chunk = opt_chunk_shape(variables['pr'].shape, max_chunk_len)

    for chunk in chunk_slices(variables['pr'].shape, opt_chunk):
        if matching_temp_units:
            chunk_data = {varname: data[chunk] for varname, data in variables.items()}
        else:
            chunk_data = {
                varname: convert_temperature_units(data[chunk], tasmin_units, tasmax_units)
                if varname == 'tasmax' else data[chunk]
                for varname, data in variables.items()
            }
        means = np.mean([chunk_data['tasmin'], chunk_data['tasmax']], axis=0)
        prsn_data = np.where(means < freezing, chunk_data['pr'], 0)
        output_dataset.variables['prsn'][chunk] = prsn_data


def generate_prsn_file(filepaths, chunk_size, outdir, output_file=None):
    '''Generate precipiation as snow data using pr, tasmin and tasmax.

       Parameters:
            filepaths (dict): Dictionary containin the three filepaths
            chunk_size (int): Number of timeslices to be read/written
            outdir (str): Output directory
            output_file (str): Optional custom output filename
    '''
    for filepath in filepaths.values():
        logger.info('Retrieving file: {}'.format(filepath))

    datasets = {
        varname: CFDataset(filepath)
        for varname, filepath in filepaths.items()
    }
    variables = {
        varname: datasets[varname].variables[varname]
        for varname in filepaths.keys()
    }

    logger.info('Conducting pre-process checks')
    required_vars = filepaths.keys()
    failures = preprocess_checks(datasets, variables, required_vars)
    if failures:
        for failure in failures.keys():
            logger.exception('{} check failed'.format(failure))
        raise Exception('Pre-process checks have failed')

    logger.info('Creating outfile')
    if output_file:
        output_filepath = custom_filepath(outdir, output_file)
    else:
        output_filepath = create_filepath_from_source(datasets['pr'], 'prsn', outdir)

    with CFDataset(output_filepath, mode='w') as output_dataset:
        create_prsn_netcdf_from_source(datasets['pr'], output_dataset)

    logger.info('Processing files')
    with CFDataset(output_filepath, mode='r+') as output_dataset:
        process_to_prsn(variables, output_dataset, chunk_size)

    logger.info('Output at: {}'.format(output_filepath))
    logger.info('Complete')
