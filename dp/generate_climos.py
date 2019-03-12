import os
import os.path
import logging
import shutil

from datetime import datetime
import dateutil.parser
import numpy as np

from cdo import Cdo
from netCDF4 import date2num
from dateutil.relativedelta import relativedelta

from nchelpers import CFDataset
from nchelpers.date_utils import d2s

from dp.argparse_helpers import strtobool, log_level_choices
from dp.units_helpers import Unit


# Set up logging
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s', "%Y-%m-%d %H:%M:%S")
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)  # For testing, overridden by -l when run as a script

# Instantiate CDO interface
cdo = Cdo()


def create_climo_files(outdir, input_file, operation, t_start, t_end,
                       convert_longitudes=True, split_vars=True, split_intervals=True):
    """Generate climatological files from an input file and a selected time range.

    Parameters:
        outdir (str): path to base directory in which to store output climo file(s)
        input_file (nchelpers.CFDataset): the input data file
        operation (str): name of the cdo stat operation that will be performed on the data
        convert_longitudes (bool): If True, convert longitudes from [0, 360) to [-180, 180).
        split_vars (bool): If True, produce one file per dependent variable in input file;
            otherwise produce a single output file containing all variables.
            Note: Can split both variables and intervals.
        split_intervals (bool): If True, produce one file per averaging interval (month, season, year);
            otherwise produce a single output file with all averating intervals concatenated.
            Note: Can split both variables and intervals.
        t_start (datetime.datetime): start date of climo period to process
        t_end (datetime.datetime): end date of climo period to process

    The input file is not modified.

    Output is either one of the following:
    - one output file containing all variables and all intervals
    - one output file for each dependent variable in the input file, and all intervals
    - one output file for each interval, containing all variables
    - one output file for each dependent variable and each interval
    This behaviour is selected by the --split-vars and --split-intervals flags.

    We use CDO to where it is convenient; in particular, to form the climatological means and/or
    standard deviations.  Other operations are performed directly by this code, in-place on intermediate
    or final output files.

    To process an input file we must perform the following operations:

    - Select the temporal subset defined by t_start, t_end
    - Form climatological means or standard deviations over each dependent variable over all available averaging intervals
    - if not split_intervals:
        - concat files (averaging intervals)
    - Post-process climatological results:
        - if convert_longitudes, transform longitude range from [0, 360) to [-180, 180)
    - Apply any special per-variable post-processing:
        - pr: scale to mm/day
    - Update global attributes to reflect the fact this is a climatological means or standard deviations file
    - if split_vars:
        - Split multiple variables into separate files

    The above operations could validly be performed in several different orders, but the ordering given optimizes
    execution time and uses less intermediate storage space than most others.
    This ordering/optimization may need to change if different climatological outputs are later required.

    Warning: If the requested date range is not fully included in the input file, then output file will contain a
    smaller date range (defined by what's actually available in the input file) and the date range part of
    output file name will be misleading.

    """
    logger.info('Generating climo period %s to %s', d2s(t_start), d2s(t_end))

    if input_file.is_multi_year:
        raise Exception('This file already contains climatologies')

    validate_operation(operation)

    supported_vars = {
        # Standard climate variables
        'tasmin', 'tasmax', 'pr',
        # Hydrological modelling variables
        'BASEFLOW',
        'EVAP',
        'GLAC_AREA_BAND',
        'GLAC_MBAL_BAND',
        'GLAC_OUTFLOW',
        'PET_NATVEG',
        'PREC',
        'RAINF',
        'RUNOFF',
        'SNOW_MELT',
        'SOIL_MOIST_TOT',
        'SWE',
        'SWE_BAND',
        'TRANSP_VEG',
        # Climdex variables
        'cddETCCDI', 'csdiETCCDI', 'cwdETCCDI', 'dtrETCCDI', 'fdETCCDI',
        'gslETCCDI', 'idETCCDI', 'prcptotETCCDI', 'r10mmETCCDI', 'r1mmETCCDI',
        'r20mmETCCDI', 'r95pETCCDI', 'r99pETCCDI', 'rx1dayETCCDI',
        'rx5dayETCCDI', 'sdiiETCCDI', 'suETCCDI', 'thresholds', 'tn10pETCCDI',
        'tn90pETCCDI', 'tnnETCCDI', 'tnxETCCDI', 'trETCCDI', 'tx10pETCCDI',
        'tx90pETCCDI', 'txnETCCDI', 'txxETCCDI', 'wsdiETCCDI',
    }

    for variable in input_file.dependent_varnames():
        if variable not in supported_vars:
            raise Exception("Unsupported variable: cant't yet process {}".format(variable))

    # Select the temporal subset defined by t_start, t_end
    logger.info('Selecting temporal subset')
    date_range = '{},{}'.format(d2s(t_start), d2s(t_end))
    temporal_subset = cdo.seldate(date_range, input=input_file.filepath())

    # Form climatological means/standard deviations over dependent variables
    def climo_outputs(time_resolution, operation):
        """Return a list of cdo operators that generate the desired climo outputs.
        Result depends on the time resolution of input file data - different operators are applied depending.
        If operators depend also on variable, then modify this function to depend on variable as well.
        """
        validate_operation(operation)
        ops_by_resolution = {
            'daily': ['ymon' + operation, 'yseas' + operation, 'tim' + operation],
            'monthly': ['ymon' + operation, 'yseas' + operation, 'tim' + operation],
            'yearly': ['tim' + operation]
        }
        try:
            return [getattr(cdo, op)(input=temporal_subset) for op in ops_by_resolution[time_resolution]]
        except:
            raise ValueError("Expected input file to have time resolution in {}, found '{}'"
                             .format(ops_by_resolution.keys(), time_resolution))

    logger.info('Forming climatological {}s'.format(operation))
    climo_files = climo_outputs(input_file.time_resolution, operation)

    # Optionally concatenate means/sds for each interval (month, season, year) into one file
    if not split_intervals:
        logger.info('Concatenating {} interval files'.format(operation))
        climo_files = [cdo.copy(input=' '.join(climo_files))]

    # Optionally convert longitudes in each file
    if convert_longitudes:
        logger.info('Converting longitudes')
        climo_files = [convert_longitude_range(climo_file) for climo_file in climo_files]

    # Convert units on any pr variable in each file
    climo_files = [convert_pr_var_units(input_file, climo_file) for climo_file in climo_files]

    # Update metadata in climo files
    logger.debug('Updating climo metadata')
    climo_files = [update_metadata_and_time_var(input_file, t_start, t_end, operation, climo_file)
                         for climo_file in climo_files]

    # Split climo files by dependent variables if required
    if split_vars:
        climo_files = [
            fp
            for climo_file in climo_files
            for fp in split_on_variables(climo_file, input_file.dependent_varnames())
        ]

    # Move/copy the temporary files to their final output filepaths
    output_file_paths = []
    for climo_file in climo_files:
        with CFDataset(climo_file) as cf:
            output_file_path = os.path.join(outdir, cf.cmor_filename)
        try:
            logger.info('Output file: {}'.format(output_file_path))
            if not os.path.exists(os.path.dirname(output_file_path)):
                os.makedirs(os.path.dirname(output_file_path))
            shutil.move(climo_file, output_file_path)
        except Exception as e:
            logger.warning('Failed to create climatology file. {}: {}'.format(e.__class__.__name__, e))
        else:
            output_file_paths.append(output_file_path)

    # TODO: fix <variable_name>:cell_methods attribute to represent climatological aggregation
    # TODO: Does the above TODO make any sense? Each variable has had up to 3 different aggregations applied
    # to it, and there is no standard cell_method string that expresses more than one.

    return output_file_paths


def generate_climo_time_var(t_start, t_end, types={'monthly', 'seasonal', 'annual'}):
    """Generate information needed to update the climatological time variable.

    :param t_start: (datetime.datetime) start date of period over which climatological means/standard deviations are formed
    :param t_end: (datetime.datetime) end date of period over which climatological means/standards deviation are formed
    :param types: (set) specifies what means/standards deviation have been generted, hence which time values to generate
    :returns: (tuple) times, climo_bounds
        times: (list) datetime for *center* of each climatological mean/standard deviation period; see CF standard
        climo_bounds: (list) bounds (start and end date) of each climatological mean/standard deviation period

    ASSUMPTION: Time values are in the following order within the time dimension variable.
        monthly: 12 months in their usual order
        seasonal: 4 seasons: DJF, MAM, JJA, SON
        annual: 1 value
    """

    # Year of all time values is middle year of period
    year = (t_start + (t_end - t_start)/2).year + 1

    # We follow the examples in sec 7.4 Climatological Statistics of the CF Metadata Standard
    # (http://cfconventions.org/cf-conventions/v1.6.0/cf-conventions.html#climatological-statistics),
    # in which for climatological times they use the 15th day of each month for multi-year monthly averages
    # and the 16th day of the mid-season months (Jan, Apr, July, Oct) for multi-year seasonal averages.
    # In that spirit, we use July 2 as the middle day of the year (https://en.wikipedia.org/wiki/July_2).
    times = []
    climo_bounds = []

    # Monthly time values
    if 'monthly' in types:
        for month in range(1, 13):
            times.append(datetime(year, month, 15))
            climo_bounds.append([datetime(t_start.year, month, 1),
                                 datetime(t_end.year, month, 1) + relativedelta(months=1)])

    # Seasonal time values
    if 'seasonal' in types:
        for month in [1, 4, 7, 10]:  # Center months of season
            times.append(datetime(year, month, 16))
            climo_bounds.append([datetime(t_start.year, month, 1) + relativedelta(months=-1),
                                 datetime(t_end.year, month, 1) + relativedelta(months=2)])

    # Annual time value
    # Standard climatological periods, provided by nchelpers and implicit here, begin Jan 1 and end Dec 31
    # This is a mismatch to hydrological years, which begin/end Oct 1 / Sep 30. Discussions with Markus Schnorbus
    # confirm that for 30-year means/stanard deviations, the difference in annual and
    # season averages is negligible and therefore we do not have to allow for alternate begin and end dates.
    # """
    if 'annual' in types:
        times.append(datetime(year, 7, 2))
        climo_bounds.append([datetime(t_start.year, 1, 1),
                             datetime(t_end.year+1, 1, 1)])

    return times, climo_bounds


def convert_longitude_range(climo_data):
    """Transform longitude range from [0, 360) to [-180, 180).

    CDO offers no simple way to do this computation, therefore we do it directly.

    WARNING: This code modifies the file with filepath climo_data IN PLACE.
    """
    with CFDataset(climo_data, mode='r+') as cf:
        convert_these = [cf.lon_var]
        if hasattr(cf.lon_var, 'bounds'):
            lon_bnds_var = cf.variables[cf.lon_var.bounds]
            convert_these.append(lon_bnds_var)
        for lon_var in convert_these:
            for i, lon in np.ndenumerate(lon_var):
                if lon >= 180:
                    lon_var[i] = lon - 360
    return climo_data


def convert_pr_var_units(input_file, climo_data):
    """If the file contains a 'pr' variable, and if its units are per second, convert its units to per day.

    """
    pr_attributes = {}  # will contain updates, if any, to pr variable attributes

    if 'pr' in input_file.dependent_varnames():
        pr_variable = input_file.variables['pr']
        pr_units = Unit.from_udunits_str(pr_variable.units)
        if pr_units in [Unit('kg / m**2 / s'), Unit('mm / s')]:
            logger.info("Converting 'pr' variable to units mm/day")
            # Update units attribute
            pr_attributes['units'] = (pr_units * Unit('s / day')).to_udunits_str()
            # Multiply values by 86400 to convert from mm/s to mm/day
            seconds_per_day = 86400
            if hasattr(pr_variable, 'scale_factor') or hasattr(pr_variable, 'add_offset'):
                # This is a packed file; need only modify packing parameters
                try:
                    pr_attributes['scale_factor'] = seconds_per_day * pr_variable.scale_factor
                except AttributeError:
                    pr_attributes['scale_factor'] = seconds_per_day * 1.0  # default value 1.0 for missing scale factor
                try:
                    pr_attributes['add_offset'] = seconds_per_day * pr_variable.add_offset
                except AttributeError:
                    pr_attributes['add_offset'] = 0.0  # default value 0.0 for missing offset
            else:
                # This is not a packed file; modify the values proper
                # Extract variable
                pr_only = cdo.select('name=pr', input=climo_data)
                # Multiply values by 86400 to convert from mm/s to mm/day
                pr_only = cdo.mulc(str(seconds_per_day), input=pr_only)
                # Replace pr in all-variables file
                climo_data = cdo.replace(input=[climo_data, pr_only])

    # Update pr variable metadata as necessary to reflect changes madde
    with CFDataset(climo_data, mode='r+') as cf:
        for attr in pr_attributes:
            setattr(cf.variables['pr'], attr, pr_attributes[attr])

    return climo_data


def split_on_variables(climo_file, var_names):
    if len(var_names) > 1:
        return [cdo.select('name={}'.format(var_name), input=climo_file)
                for var_name in var_names]
    else:
        return [climo_file]


def update_metadata_and_time_var(input_file, t_start, t_end, operation, climo_filepath):
    """Updates an existing netCDF file to reflect the fact that it contains climatological means or standard deviations.

    Specifically:
    - add start and end time attributes
    - update tracking_id attribute
    - update the frequency attribute
    - update the time variable with climatological times computed according to CF Metadata Convetions,
    and create a climatology bounds variable with appropriate values.

    :param input_file: (CFDataset) input file from which the climatological output file was produced
    :param t_start: (datetime.datetime) start date of climatological output file
    :param t_end: (datetime.datetime) end date of climatological output file
    :param climo_filepath: (str) filepath to a climatological means output file which needs to have its
        metadata update

    WARNING: THIS CHANGES FILE `climo_filepath` IN PLACE

    For information on climatological statistics, and specifically on datetimes to apply to such statistics,
    see Section 7.4 of http://cfconventions.org/Data/cf-conventions/cf-conventions-1.6/build/cf-conventions.html
    """
    with CFDataset(climo_filepath, mode='r+') as cf:
        # Add start and end time attributes
        # In Python2.7, datetime.datime.isoformat does not take params telling it how much precision to
        # provide in its output; standard requires 'seconds' precision, which means the first 19 characters.
        cf.climo_start_time = t_start.isoformat()[:19] + 'Z'
        cf.climo_end_time = t_end.isoformat()[:19] + 'Z'

        # Update tracking_id attribute
        if hasattr(input_file, 'tracking_id'):
            cf.climo_tracking_id = input_file.tracking_id

        # Deduce the set of averaging intervals from the number of times in the file.
        # WARNING: This is fragile, and depends on the assumption that a climo output file contains only the following
        # possible contents: multi-decadal averages of monthly, seasonal, and annual averages, possibly concatenated
        # in that order (starting with monthly, seasonal, or annual as the original file contents allow).
        # This computation only works because each case results in a unique number of time values!
        try:
            num_times_to_interval_set = {
                12: {'monthly'},
                4: {'seasonal'},
                1: {'annual'},
                5: {'seasonal', 'annual'},
                17: {'monthly', 'seasonal', 'annual'},
            }
            interval_set = num_times_to_interval_set[cf.time_var.size]
        except KeyError:
            raise ValueError('Expected climo file to contain # time values in {}, but found {}'
                             .format(num_times_to_interval_set.keys(), cf.time_var.size))


        # Update cell_methods to reflect the operation being done to the data
        validate_operation(operation)
        cell_method_op = {
            'std': 'standard_deviation',
            'mean': 'mean'
        }[operation]

        for key in cf.variables.keys():
            try:
                cf.variables[key].cell_methods = cf.variables[key].cell_methods + ' time: {} over days'.format(cell_method_op)
            except AttributeError as e:
                # skip over vars that do not have cell_methods i.e. lat, lon
                continue

        # Update frequency attribute to reflect that this is a climo file.
        suffix = {
            'std': 'SD',
            'mean': 'Mean'
        }[operation]

        prefix = ''.join(abbr for interval, abbr in (('monthly', 'm'), ('seasonal', 's'), ('annual', 'a'), )
                         if interval in interval_set)
        cf.frequency = prefix + 'Clim' + suffix

        # Generate info for updating time variable and creating climo bounds variable
        times, climo_bounds = generate_climo_time_var(
            dateutil.parser.parse(cf.climo_start_time[:19]),  # create tz naive dates by stripping off the tz indicator
            dateutil.parser.parse(cf.climo_end_time[:19]),
            interval_set
        )

        # Update time var with CF standard climatological times
        cf.time_var[:] = date2num(times, cf.time_var.units, cf.time_var.calendar)

        # Create new climatology_bnds variable and required bnds dimension if necessary.
        # Note: CDO seems to do some automagic with bounds variable names, converting the string 'bounds' to 'bnds'.
        # For less confusion, we use that convention here, even though original code used the name 'climatology_bounds'.
        # TODO: Should this variable be added to cf.time_var.bounds?
        cf.time_var.climatology = 'climatology_bnds'
        if 'bnds' not in cf.dimensions:
            cf.createDimension('bnds', 2)
        climo_bnds_var = cf.createVariable('climatology_bnds', 'f4', ('time', 'bnds', ))
        climo_bnds_var.calendar = cf.time_var.calendar
        climo_bnds_var.units = cf.time_var.units
        climo_bnds_var[:] = date2num(climo_bounds, cf.time_var.units, cf.time_var.calendar)

    return climo_filepath


def validate_operation(operation):
    """
    Given an operation assert that it is supported.  In order to be a supported
    operation it must be in the cdo table of statistical values.
    """
    supported_operations = {
        'mean',
        'std'
    }
    if operation not in supported_operations:
        raise Exception('Unsupported operation: cant\'t yet process {}'
                        .format(operation))
