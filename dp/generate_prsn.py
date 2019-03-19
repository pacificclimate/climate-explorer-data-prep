import logging
import numpy as np
import os

from statistics import mean
from math import floor
from netCDF4 import Dataset

from dp.units_helpers import Unit


# Set up logging
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s', "%Y-%m-%d %H:%M:%S")
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


def in_shape(arrays):
    '''Ensure the arrays are the same shape'''
    return len(set(map(np.shape, arrays))) == 1


def is_unique_value(values):
    '''
    Given a list transform into set and ensure there is only one unique value
    '''
    return len(set(values)) == 1


def determine_freezing(unit):
    '''Given a unit determine which temperature describes freezing'''
    freezing = 0.0
    if unit.lower() == 'k':
        freezing = 273.15
    return freezing


def build_prsn_array(pr_data, means, freezing):
    '''Mask precipitation data where the temperature is not below freezing'''
    return np.where(means < freezing, pr_data, np.nan)


def create_prsn_netcdf_from_source(input_filepath, output_filepath):
    '''Using another netCDF as a template copy over the data applicable to prsn'''
    with Dataset(input_filepath) as src, Dataset(output_filepath, mode='w') as dst:
        # Create the dimensions of the file
        for name, dim in src.dimensions.items():
            dst.createDimension(name, len(dim) if not dim.isunlimited() else None)

        # Copy the globals
        dst.setncatts({att:src.getncattr(att) for att in src.ncattrs()})

        # Create the variables in the file
        for name, var in src.variables.items():
            dst.createVariable(name, var.dtype, var.dimensions)

            # Copy the variable attributes
            dst.variables[name].setncatts({att:var.getncattr(att) for att in var.ncattrs()})

            # we will be replacing pr data with prsn data
            if name == 'pr':
                logger.debug('Skipping pr')
                continue
            else:
                logger.debug('Copying {}'.format(name))
                dst.variables[name][:] = src.variables[name][:]

        # change pr metadata to prsn equivalents=
        dst.renameVariable('pr', 'prsn')
        prsn_var = dst.variables['prsn']

        prsn_var.standard_name = 'snowfall_flux'
        prsn_var.long_name = 'Precipitation as Snow'

        prsn_var.delncattr('original_name')
        prsn_var.delncattr('comment')


def copy_netcdf_data(output_filepath, data, start, end):
    '''Copy a chunk of the netCDF data'''
    with Dataset(output_filepath, mode='r+') as dst:
        dst.variables['prsn'][start:end] = data


def create_filepath_from_source(source_path, new_var, outdir):
    '''
    Using the source filename build a new output filepath with new_var and
    output directory.
    '''
    file_name = source_path.split('/')[-1]
    variable, *rest = file_name.split('_')

    suffix = ''
    for var in rest:
        suffix += '_' + var

    if not os.path.exists(os.path.dirname(outdir)):
        os.makedirs(os.path.dirname(outdir))

    return os.path.join(outdir, new_var + suffix)


def has_required_vars(datasets, required_vars):
    '''
    Given a list of datasets and a list of required variables, ensure the
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
    '''
    Given a list of datasets, match important metadata vars to ensure the
    datasets are compatible.
    '''
    experiment_id = []
    model_id = []
    parent_experiment_rip = []

    for dataset in datasets:
        experiment_id.append(dataset.getncattr('experiment_id'))
        model_id.append(dataset.getncattr('model_id'))
        parent_experiment_rip.append(dataset.getncattr('parent_experiment_rip'))

    # ensure metadata match
    if not is_unique_value(experiment_id) or not is_unique_value(model_id) \
       and not is_unique_value(parent_experiment_rip):
        logger.warning(('Files do not have the same metadata:'
                        '\n\texperiment_id: {}'
                        '\n\tmodel_id: {}'
                        '\n\tparent_experiment_rip: {}')
                       .format(experiment_id, model_id, parent_experiment_rip))
        return False

    return True


def matching_temperature_units(tasmin, tasmax):
    '''Ensure the temperature datasets have matching units'''
    return is_unique_value([tasmin.variables['tasmin'].units,
                            tasmax.variables['tasmax'].units])


def check_pr_units(pr):
    '''Ensure we have expected pr units'''
    pr_variable = pr.variables['pr']
    pr_units = Unit.from_udunits_str(pr_variable.units)
    return pr_units in [Unit('kg / m**2 / s'), Unit('mm / s')]


def preprocess_checks(pr, tasmin, tasmax, required_vars):
    '''Perform all pre-processing checks'''
    return matching_datasets([pr, tasmin, tasmax]) and \
        has_required_vars([pr, tasmin, tasmax], required_vars) and \
        matching_temperature_units(tasmin, tasmax) and \
        check_pr_units(pr)


def process_to_prsn(pr, tasmin, tasmax, max_len, output_filepath, freezing):
    '''Process precipitation data into snowfall data

    This method takes a precipitation, tasmin and tasmax file and uses them to
    produce a snowfall file.  Using a mean of the temperature files the script
    will look through all the cells in the datacube and mask any cells that
    are not freezing.  This mask applies to the precipiation file and thus we
    are left with cells where it was cold enough for snow.

    The input files are read in small chunks to avoid filling up all available
    memory and crashing the script.  Size refers to the chunk size being read
    in from the time dimension.  Example: Chunk read in (100, all lon, all lat)

    Parameters:
        pr (netCDF.Dataset): Dataset object for precipitation
        tasmin (netCDF.Dataset): Dataset object for tasmin
        tasmax (netCDF.Dataset): Dataset object for tasmax
        max_len (int): The length of the precipitation variable to be used as
            the loop condition
        output_filepath (str): Path to base directory in which to store output
            prsn file
        freezing (float): Freezing temperature
    '''
    # TODO: Figure out a way to dynamically choose chunksize
    size = 100
    start = 0
    end = size

    if size > max_len:
        size = max_len

    while(start < max_len):
        # end of array check
        if end > max_len:
            end = max_len

        # get variable data
        pr_data = pr.variables['pr'][start:end]
        tasmin_data = tasmin.variables['tasmin'][start:end]
        tasmax_data = tasmax.variables['tasmax'][start:end]

        # shape check
        if not in_shape([pr_data, tasmin_data, tasmax_data]):
            raise Exception('Arrays do not have the same shape')

        # form temperature means
        means = np.mean([tasmin_data, tasmax_data], axis=0)

        # build data
        prsn_data = build_prsn_array(pr_data, means, freezing)

        # write netcdf
        logger.debug('Write prsn data to netCDF')
        copy_netcdf_data(output_filepath, prsn_data, start, end)

        # prep next loop
        start = end
        end += size


def generate_prsn_file(pr_filepath, tasmin_filepath, tasmax_filepath, outdir):
    '''Generate precipiation as snow data using pr, tasmin and tasmax.

    Parameters:
        pr_filepath (str): The filepath to desired precipiation data
        tasmin_filepath (str): The filepath to desired tasmin data
        tasmax_filepath (str): The filepath to desired tasmax data
        outdir (str): Output directory path
    '''
    logger.info('Retrieving files:\n\t{},\n\t{},\n\t{}'
                .format(pr_filepath, tasmin_filepath, tasmax_filepath))

    pr = Dataset(pr_filepath)
    tasmin = Dataset(tasmin_filepath)
    tasmax = Dataset(tasmax_filepath)

    # make sure datasets match
    logger.info('Conducting pre-process checks')
    if not preprocess_checks(pr, tasmin, tasmax, ['pr', 'tasmin', 'tasmax']):
        raise Exception('Pre-process checks have failed.')

    # create template nc file from pr file
    logger.info('Creating outfile')
    output_filepath = create_filepath_from_source(pr_filepath, 'prsn', outdir)
    create_prsn_netcdf_from_source(pr_filepath, output_filepath)

    logger.info('Processing files in chunks')
    freezing = determine_freezing(tasmin.variables['tasmin'].units)
    max_len = len(pr.variables['pr'])
    process_to_prsn(pr, tasmin, tasmax, max_len, output_filepath, freezing)

    logger.info('Complete')
