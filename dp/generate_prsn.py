import logging
import numpy as np
import os

from statistics import mean
from netCDF4 import Dataset


# Set up logging
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s', "%Y-%m-%d %H:%M:%S")
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


def in_shape(arrays):
    return len(set(map(np.shape, arrays))) == 1


def build_prsn_array(pr_data, means, units):
    if len(units) > 1:
        raise Exception('Temperature files units do not match: {}'.format(units))

    freezing = 0
    if units.pop() == 'K':
        freezing = 273.15
    return np.where(means < freezing, pr_data, np.nan)


def create_netcdf_from_source(input_filepath, output_filepath):
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
    with Dataset(output_filepath, mode='r+') as dst:
        dst.variables['prsn'][start:end] = data


def create_output_filepath(filepath, outdir):
    file_name = filepath.split('/')[-1]
    variable, *rest = file_name.split('_')
    variable = 'prsn'
    suffix = ''
    for var in rest:
        suffix += '_' + var
    if not os.path.exists(os.path.dirname(outdir)):
        os.makedirs(os.path.dirname(outdir))
    return os.path.join(outdir, variable + suffix)


def match_datasets(datasets):
    unique_vars = set()
    experiment_id = set()
    model_id = set()
    parent_experiment_rip = set()

    for dataset in datasets:
        for var in dataset.variables:
            unique_vars.add(var)

        experiment_id.add(dataset.getncattr('experiment_id'))
        model_id.add(dataset.getncattr('model_id'))
        parent_experiment_rip.add(dataset.getncattr('parent_experiment_rip'))

    if len(experiment_id) != 1 or len(model_id) != 1 or len(parent_experiment_rip) != 1:
        return False

    for required_var in ['pr', 'tasmin', 'tasmax']:
        if required_var not in unique_vars:
            return False

    return True


def generate_prsn_file(pr_filepath, tasmin_filepath, tasmax_filepath, outdir):
    '''Generate precipiation as snow data using pr, tasmin and tasmax.

    Parameters:
        pr_filepath (str): The filepath

    '''
    logger.info('Retrieving files:\n\t{},\n\t{},\n\t{}'
                .format(pr_filepath, tasmin_filepath, tasmax_filepath))

    # create template nc file from pr file
    output_filepath = create_output_filepath(pr_filepath, outdir)
    create_netcdf_from_source(pr_filepath, output_filepath)

    # open datasets
    pr_dataset = Dataset(pr_filepath)
    tasmin_dataset = Dataset(tasmin_filepath)
    tasmax_dataset = Dataset(tasmax_filepath)

    # make sure datasets match
    if not match_datasets([pr_dataset, tasmin_dataset, tasmax_dataset]):
        raise Exception('Datasets do not match, please ensure you are using the correct files')

    # prepare loop vars
    max_len = len(pr_dataset.variables['pr'])
    chunk_size = 100
    chunk_start = 0
    chunk_end = chunk_size
    if chunk_size > max_len:
        chunk_size = max_len

    logger.info('Processing files')
    while(chunk_start < max_len):
        # end of array check
        if chunk_end > max_len:
            chunk_end = max_len

        logger.info('{}/{}, {}%'.format(chunk_end, max_len, round(((chunk_end/max_len) * 100), 2)))

        # get variable data
        pr_data = pr_dataset.variables['pr'][chunk_start:chunk_end]
        tasmin_data = tasmin_dataset.variables['tasmin'][chunk_start:chunk_end]
        tasmax_data = tasmax_dataset.variables['tasmax'][chunk_start:chunk_end]

        # shape check
        if not in_shape([pr_data, tasmin_data, tasmax_data]):
            raise Exception('Arrays do not have the same shape')

        # form temperature means
        means = np.mean([tasmin_data, tasmax_data], axis=0)

        # build data
        units = {tasmin_dataset.variables['tasmin'].units,
                 tasmax_dataset.variables['tasmax'].units}
        prsn_data = build_prsn_array(pr_data, means, units)

        # write netcdf
        logger.debug('Write prsn data to netCDF')
        copy_netcdf_data(output_filepath, prsn_data, chunk_start, chunk_end)

        # prep next loop
        chunk_start = chunk_end
        chunk_end += chunk_size

    logger.info('Complete')