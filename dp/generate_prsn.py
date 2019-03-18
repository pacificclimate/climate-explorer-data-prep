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
    '''Ensure the arrays are the same shape'''
    return len(set(map(np.shape, arrays))) == 1


def build_prsn_array(pr_data, means, units):
    '''Mask precipitation data where the temperature is not below freezing'''
    if len(units) > 1:
        raise Exception('Temperature files units do not match: {}'.format(units))

    freezing = 0
    if units.pop() == 'K':
        freezing = 273.15
    return np.where(means < freezing, pr_data, np.nan)


def create_netcdf_from_source(input_filepath, output_filepath):
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


def create_output_filepath(filepath, outdir):
    '''
    Using the precipitation filename and output directory build an output
    filepath
    '''
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
    '''Determine whether the files will produce a correct result'''
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

    # ensure all match
    if len(experiment_id) != 1 or len(model_id) != 1 or len(parent_experiment_rip) != 1:
        return False

    # ensure we have the required variables to produce prsn
    for required_var in ['pr', 'tasmin', 'tasmax']:
        if required_var not in unique_vars:
            return False

    return True


def chunk_process_netcdf(pr, tasmin, tasmax, max_len, output_filepath, chunk_size=100):
    '''Process precipitation data into snowfall data

    This method takes a precipitation, tasmin and tasmax file and uses them to
    produce a snowfall file.  Using a mean of the temperature files the script
    will look through all the cells in the datacube and mask any cells that
    are not freezing.  This mask applies to the precipiation file and thus we
    are left with cells where it was cold enough for snow.

    The input files are read in small chunks to avoid filling up all available
    memory and crashing the script.

    Parameters:
        pr (netCDF.Dataset): Dataset object for precipitation
        tasmin (netCDF.Dataset): Dataset object for tasmin
        tasmax (netCDF.Dataset): Dataset object for tasmax
        max_len (int): The length of the precipitation variable to be used as
            the loop condition
        output_filepath (str): Path to base directory in which to store output
            prsn file
        chunk_size (int): Size of time dimension to be read from the datacube
            (Defaulted to 100). The chunk of datacube being accessed will look
            like: (chunk_size, lat_size, lon_size).
    '''
    # TODO: Figure out a way to dynamically choose chunksize
    chunk_start = 0
    chunk_end = chunk_size

    if chunk_size > max_len:
        chunk_size = max_len

    while(chunk_start < max_len):
        # end of array check
        if chunk_end > max_len:
            chunk_end = max_len

        # get variable data
        pr_data = pr.variables['pr'][chunk_start:chunk_end]
        tasmin_data = tasmin.variables['tasmin'][chunk_start:chunk_end]
        tasmax_data = tasmax.variables['tasmax'][chunk_start:chunk_end]

        # shape check
        if not in_shape([pr_data, tasmin_data, tasmax_data]):
            raise Exception('Arrays do not have the same shape')

        # form temperature means
        means = np.mean([tasmin_data, tasmax_data], axis=0)

        # build data
        units = {tasmin.variables['tasmin'].units,
                 tasmax.variables['tasmax'].units}
        prsn_data = build_prsn_array(pr_data, means, units)

        # write netcdf
        logger.debug('Write prsn data to netCDF')
        copy_netcdf_data(output_filepath, prsn_data, chunk_start, chunk_end)

        # prep next loop
        chunk_start = chunk_end
        chunk_end += chunk_size


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
    if not match_datasets([pr, tasmin, tasmax]):
        raise Exception('Datasets do not match, please ensure you are using the correct files')
    logger.info('Dataset are matching')

    # create template nc file from pr file
    logger.info('Creating outfile')
    output_filepath = create_output_filepath(pr_filepath, outdir)
    create_netcdf_from_source(pr_filepath, output_filepath)

    logger.info('Processing files in chunks')
    chunk_process_netcdf(pr, tasmin, tasmax, len(pr.variables['pr']), output_filepath)

    logger.info('Complete')
