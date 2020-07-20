import sys
import os
import os.path
import logging
import shutil
import warnings

from datetime import datetime
from itertools import chain
import dateutil.parser
import calendar
import numpy as np
import re

from cdo import Cdo
from netCDF4 import date2num
from dateutil.relativedelta import relativedelta
from enum import Enum

from nchelpers import CFDataset, standard_climo_periods
from nchelpers.date_utils import d2s

from dp.argparse_helpers import strtobool, log_level_choices
from dp.units_helpers import Unit


# Set up logging
formatter = logging.Formatter(
    "%(asctime)s %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"
)
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)  # For testing, overridden by -l when run as a script

# Instantiate CDO interface
cdo = Cdo()


def input_check(filepath, climo, outputer=logger.info):
    """
    This function runs general checks on the given input arguments filepath and climo.
    There are 2 checking processes:

        1. checks if the given input file path is a vaild NetCDF file
        2. checks if the input NetCDF dataset has a set of standard climo periods by
           using climo_periods property

    The function returns CFDataset and list.
    If any of the checks are not passed, the function returns None and empty list.
    """
    outputer(f"File: {filepath}")

    try:
        input_file = CFDataset(filepath)
    except OSError as e:
        logger.critical("{}: {}".format(e.__class__.__name__, e))
        return None, []

    periods = input_file.climo_periods.keys() & climo
    outputer(f"climo_periods: {periods}")
    if len(periods) == 0:
        logger.critical(
            f"{input_file.filepath()} contains no standard climatological periods"
        )
        return None, []

    return input_file, periods


def dry_run_handler(filepath, climo, outpath=None):
    """
    This function handles dry-run operation of generate_climos. The purpose of this function
    is to check variables and attrbutes to be used for generate_climos. 

        * dry-run will not produce any NetCDF output files.
        * dry-run information will be logged out to an output .txt file if outpath is given
        * Otherwise, it will be logged out to terminal
    """
    if outpath:  # Used for wps process in thunderbird
        output_items = []
        outputer = output_items.append
    else:
        outputer = logger.info

    outputer("DRY_RUN")

    input_file, periods = input_check(filepath, climo, outputer)

    for attr in ["project", "institution", "model", "emissions", "run"]:
        try:
            outputer(f"{attr}: {getattr(input_file.metadata, attr)}")
        except Exception as e:
            outputer(f"{attr}: {e.__class__.__name__}: {e}")
    outputer(f"dependent_varnames: {input_file.dependent_varnames()}")
    for attr in ["time_resolution", "is_multi_year_mean"]:
        outputer(f"{attr}: {getattr(input_file, attr)}")

    if outpath:
        with open(outpath, "w") as f:
            for line in output_items:
                f.write(f"{line}\n")


def generate_climos(
    filepath,
    outdir,
    operation,
    climo=standard_climo_periods().keys(),
    convert_longitudes=True,
    split_vars=True,
    split_intervals=True,
    resolutions={"yearly", "seasonal", "monthly"},
):
    """
    This function runs general generate_climos operation. The main purpose of this function
    is to call create_climo_files.
    """
    input_file, periods = input_check(filepath, climo)

    for period in periods:
        t_range = input_file.climo_periods[period]
        create_climo_files(
            period,
            outdir,
            input_file,
            operation,
            *t_range,
            convert_longitudes=convert_longitudes,
            split_vars=split_vars,
            split_intervals=split_intervals,
            output_resolutions=resolutions,
        )


def create_climo_files(
    climo_period,
    outdir,
    input_file,
    operation,
    t_start,
    t_end,
    convert_longitudes,
    split_vars,
    split_intervals,
    output_resolutions,
):
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
        output_resolutions (set): which temporal resolutions for which to generate climatologies

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
    # args used for command line reconstruction for history attribute
    # when no stdin argument is given
    args = {
        "": input_file.filepath(),
        "-c": climo_period,
        "-o": outdir,
        "-p": operation,
        "-g": str(convert_longitudes),
        "-v": str(split_vars),
        "-i": str(split_intervals),
        "-r": str(output_resolutions),
    }

    def curr_time_cdo_format():
        """This function returns current time in the format of
        cdo's history attribute.
        """
        return datetime.now().strftime("%a %b %d %H:%M:%S %Y")

    # Record the starting time of generate_climos
    logger.info("Start of generate_climos")
    t_start_generate_climos = curr_time_cdo_format()

    logger.info("Generating climo period %s to %s", d2s(t_start), d2s(t_end))

    if input_file.is_multi_year:
        raise Exception("This file already contains climatologies")

    validate_operation(operation)

    # Two processes are performed by this script.
    # 1) If possible, it generates datasets with lower time resolution than
    #    the input data: daily -> monthly -> seasonal -> annual
    # 2) It generates climatologies from the input data and any lower-
    #    resolution datasets it has created by taking the multi-year mean
    #    or standard deviation
    # In order to do #1, it must know how to aggregate data across a longer
    # period, which varies by how a variable is generated

    # Point variables represent measurements (or simulations thereof) at a
    # specific moment. Data is aggregated across a longer time period by
    # averaging it.

    # Count variables represent the number of times something happens within
    # a period. Data is aggregated across a longer time period by summing it.

    # Maximum variables represent the largest value recorded over the period
    # of time. Data is aggregated across a longer period by taking the maximum
    # of the constituent periods' values.

    # Minimum variables represent the smallest value recorded over a set period;
    # the value for an aggregated period is the minimum of the constituent periods.

    # Duration variables represent the length of a continuous period of time
    # that meets certain qualifications.
    # These variables cannot be aggregated across a longer time period without
    # more information, due to uncertainity about whether the continuous
    # periods described in shorter time resolutions to be aggregated coincide.

    # TODO - assign variable "thresholds" to a category
    # TODO - determine this from incoming cell methods if possible

    variable_types = {
        # Standard climate variables
        "tasmin": "point",
        "tasmax": "point",
        "pr": "point",
        # Hydrological modelling variables
        "BASEFLOW": "point",
        "EVAP": "point",
        "GLAC_AREA_BAND": "point",
        "GLAC_MBAL_BAND": "point",
        "GLAC_OUTFLOW": "point",
        "PET_NATVEG": "point",
        "PREC": "point",
        "RAINF": "point",
        "RUNOFF": "point",
        "SNOW_MELT": "point",
        "SOIL_MOIST_TOT": "point",
        "SWE": "point",
        "SWE_BAND": "point",
        "TRANSP_VEG": "point",
        # Hydrological outputs
        "streamflow": "point",
        # Climdex variables
        "cddETCCDI": "duration",
        "csdiETCCDI": "duration",
        "cwdETCCDI": "duration",
        "dtrETCCDI": "point",
        "fdETCCDI": "count",
        "gslETCCDI": "duration",
        "idETCCDI": "count",
        "prcptotETCCDI": "count",
        "r10mmETCCDI": "count",
        "r1mmETCCDI": "count",
        "r20mmETCCDI": "count",
        "r95pETCCDI": "count",
        "r99pETCCDI": "count",
        "rx1dayETCCDI": "maximum",
        "rx5dayETCCDI": "maximum",
        "sdiiETCCDI": "point",
        "suETCCDI": "count",
        "tn10pETCCDI": "point",
        "tn90pETCCDI": "point",
        "tnnETCCDI": "minimum",
        "tnxETCCDI": "maximum",
        "trETCCDI": "count",
        "tx10pETCCDI": "point",
        "tx90pETCCDI": "point",
        "txnETCCDI": "minimum",
        "txxETCCDI": "maximum",
        "wsdiETCCDI": "duration",
        # Degree Day Variables
        "cdd": "count",
        "fdd": "count",
        "gdd": "count",
        "hdd": "count",
        # Plan2Adapt Variables
        "prsn": "point",
    }

    try:
        var_types = {
            variable_types[variable] for variable in input_file.dependent_varnames()
        }
    except KeyError as e:
        raise Exception("Unsupported variable: can't yet process {}".format(e.args[0]))

    if not len(var_types) == 1:
        raise Exception("Only one type of variable allowed per file")
    var_type = list(var_types)[0]

    # Select the temporal subset defined by t_start, t_end
    logger.info("Selecting temporal subset")
    date_range = "{},{}".format(d2s(t_start), d2s(t_end))
    temporal_subset = cdo.seldate(date_range, input=input_file.filepath())

    # Update generate_climos history attribute
    temporal_subset = update_generate_climos_history(
        args, temporal_subset, t_start_generate_climos, position=1
    )

    # Form climatological means/standard deviations over dependent variables
    def climo_outputs(
        time_resolution,
        operation,
        data,
        aggregate=True,
        output_resolutions={"monthly", "seasonal", "yearly"},
    ):
        """Return a list of cdo operators that generate the desired climo outputs.
        Result depends on the time resolution of input file data. If
        aggregate is false, only operations that generate climatologies at
        the exact same resolution as the input dataset will be used; otherwise
        data will be aggregated daily -> monthly -> seasonal -> yearly.
        """
        if time_resolution == "daily" and not aggregate:
            raise Exception(
                "Cannot generate non-aggregated climatologies from a daily dataset"
            )

        climo_ops = {
            "daily": {},
            "monthly": {"monthly": "ymon" + operation},
            "seasonal": {"seasonal": "yseas" + operation},
            "yearly": {"yearly": "tim" + operation},
        }
        aggregate_climo_ops = {
            "daily": {
                "monthly": "ymon" + operation,
                "seasonal": "yseas" + operation,
                "yearly": "tim" + operation,
            },
            "monthly": {"seasonal": "yseas" + operation, "yearly": "tim" + operation},
            "seasonal": {"yearly": "tim" + operation},
            "yearly": {},
        }
        operations = climo_ops[time_resolution]
        if aggregate:
            operations.update(aggregate_climo_ops[time_resolution])
        # Filter the operations by resolution to create
        operations = [
            operations[rez] for rez in output_resolutions if rez in operations
        ]

        # It's possible that the set of user selected output
        # resolutions is disjoint with the set of available output
        # resoultions
        if not operations:
            warnings.warn(
                "None of the selected output resolutions %s are "
                "computable from a file with %s temporal resolution".format(
                    " ,".join(output_resolutions), time_resolution
                )
            )
            return []

        try:
            return [getattr(cdo, op)(input=data) for op in operations]
        except:
            raise ValueError(
                "Expected input file to have time resolution in {}, found '{}'".format(
                    climo_ops.keys(), time_resolution
                )
            )

    logger.info("Forming climatological {}s".format(operation))
    if var_type == "point":
        # cdo can handle these variables in a single step
        climo_files = climo_outputs(
            input_file.time_resolution,
            operation,
            temporal_subset,
            True,
            output_resolutions,
        )
    elif var_type in ["count", "maximum", "minimum"]:
        # cdo's ymon* climatology-creating operations assume means for
        # constructing subyear aggregate datasets (like making a monthly
        # dataset from a daily dataset).
        # For these variables, the value of a year is *not* the mean of the
        # monthly or daily values. Therefore, the sub-year aggregate datasets
        # need to be explicitly contructed with a separate cdo command, before
        # calculating climatologies from them.
        aggregations = generate_aggregates(temporal_subset, input_file, var_type)
        climo_files = []
        for res in aggregations:
            climo_files.extend(
                climo_outputs(
                    res, operation, aggregations[res], False, output_resolutions
                )
            )

    elif var_type == "duration":
        # Sub-year aggregation cannot be performed at all with these variables.
        # We can only generate climatologies at the resolution received.
        climo_files = climo_outputs(
            input_file.time_resolution,
            operation,
            temporal_subset,
            False,
            output_resolutions,
        )

    # Optionally concatenate values for each interval (month, season, year) into one file
    if not split_intervals and climo_files:
        logger.info("Concatenating {} interval files".format(operation))
        climo_files = [cdo.copy(input=" ".join(climo_files))]

    # Optionally convert longitudes in each file
    if convert_longitudes and climo_files:
        logger.info("Converting longitudes")
        climo_files = [
            convert_longitude_range(climo_file) for climo_file in climo_files
        ]

    # Convert units on any pr variable in each file
    climo_files = [
        convert_flux_var_units(input_file, climo_file) for climo_file in climo_files
    ]

    # Update metadata in climo files
    logger.debug("Updating climo metadata")
    climo_files = [
        update_metadata_and_time_var(input_file, t_start, t_end, operation, climo_file)
        for climo_file in climo_files
    ]

    # Split climo files by dependent variables if required
    if split_vars:
        climo_files = [
            fp
            for climo_file in climo_files
            for fp in split_on_variables(climo_file, input_file.dependent_varnames())
        ]

    # Record the ending time of generate_climos
    logger.info("End of generate_climos")
    t_end_generate_climos = curr_time_cdo_format()
    # Update generate_climos history attribute
    climo_files = [
        update_generate_climos_history(args, climo_file, t_end_generate_climos)
        for climo_file in climo_files
    ]

    # Move/copy the temporary files to their final output filepaths
    output_file_paths = []
    for climo_file in climo_files:
        with CFDataset(climo_file) as cf:
            output_file_path = os.path.join(outdir, cf.cmor_filename)
        try:
            logger.info("Output file: {}".format(output_file_path))
            if not os.path.exists(os.path.dirname(output_file_path)):
                os.makedirs(os.path.dirname(output_file_path))
            shutil.move(climo_file, output_file_path)
        except Exception as e:
            logger.warning(
                "Failed to create climatology file. {}: {}".format(
                    e.__class__.__name__, e
                )
            )
        else:
            output_file_paths.append(output_file_path)

    # TODO: fix <variable_name>:cell_methods attribute to represent climatological aggregation
    # TODO: Does the above TODO make any sense? Each variable has had up to 3 different aggregations applied
    # to it, and there is no standard cell_method string that expresses more than one.

    return output_file_paths


def generate_climo_time_var(t_start, t_end, types={"monthly", "seasonal", "annual"}):
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
    year = (t_start + (t_end - t_start) / 2).year + 1

    # We follow the examples in sec 7.4 Climatological Statistics of the CF Metadata Standard
    # (http://cfconventions.org/cf-conventions/v1.6.0/cf-conventions.html#climatological-statistics),
    # in which for climatological times they use the 15th day of each month for multi-year monthly averages
    # and the 16th day of the mid-season months (Jan, Apr, July, Oct) for multi-year seasonal averages.
    # In that spirit, we use July 2 as the middle day of the year (https://en.wikipedia.org/wiki/July_2).
    times = []
    climo_bounds = []

    # Monthly time values
    if "monthly" in types:
        for month in range(1, 13):
            times.append(datetime(year, month, 15))
            climo_bounds.append(
                [
                    datetime(t_start.year, month, 1),
                    datetime(t_end.year, month, 1) + relativedelta(months=1),
                ]
            )

    # Seasonal time values
    if "seasonal" in types:
        for month in [1, 4, 7, 10]:  # Center months of season
            times.append(datetime(year, month, 16))
            climo_bounds.append(
                [
                    datetime(t_start.year, month, 1) + relativedelta(months=-1),
                    datetime(t_end.year, month, 1) + relativedelta(months=2),
                ]
            )

    # Annual time value
    # Standard climatological periods, provided by nchelpers and implicit here, begin Jan 1 and end Dec 31
    # This is a mismatch to hydrological years, which begin/end Oct 1 / Sep 30. Discussions with Markus Schnorbus
    # confirm that for 30-year means/stanard deviations, the difference in annual and
    # season averages is negligible and therefore we do not have to allow for alternate begin and end dates.
    # """
    if "annual" in types:
        times.append(datetime(year, 7, 2))
        climo_bounds.append(
            [datetime(t_start.year, 1, 1), datetime(t_end.year + 1, 1, 1)]
        )

    return times, climo_bounds


def generate_aggregates(data, input_file, var_type):
    """Generates aggregated datasets with resolutions [monthly, seasonal, yearly]
    as possible from a dataset with a higher time resolution.

    This function is required for the variables where the value of the variable
    over a longer time period is not the mean of the values of of the variable
    over the constituent time periods.

    counted variables: represent the number of times something happens
                       value of period is sum of values of constituent periods

    maximum variables: represent the largest value recorded
                       value of period is maximum of constituent period values

    minimum variables: represent the smallest value recorded
                       value of period is minimum of constituent period values
    """

    logger.info("Generating intermediate aggregate files")
    aggregator = {"count": "sum", "maximum": "max", "minimum": "min"}[var_type]
    aggregations = {}

    if input_file.time_resolution != "daily":
        aggregations[input_file.time_resolution] = data

    if input_file.time_resolution in ["daily", "monthly", "seasonal"]:
        aggregations["yearly"] = getattr(cdo, "year" + aggregator)(input=data)
    if input_file.time_resolution in ["daily", "monthly"]:
        aggregations["seasonal"] = getattr(cdo, "seas" + aggregator)(input=data)
    if input_file.time_resolution == "daily":
        aggregations["monthly"] = getattr(cdo, "mon" + aggregator)(input=data)

    return aggregations


def convert_longitude_range(climo_data):
    """Transform longitude range from [0, 360) to [-180, 180).

    CDO offers no simple way to do this computation, therefore we do it directly.

    WARNING: This code modifies the file with filepath climo_data IN PLACE.
    """
    with CFDataset(climo_data, mode="r+") as cf:
        convert_these = [cf.lon_var]
        if hasattr(cf.lon_var, "bounds"):
            lon_bnds_var = cf.variables[cf.lon_var.bounds]
            convert_these.append(lon_bnds_var)
        for lon_var in convert_these:
            for i, lon in np.ndenumerate(lon_var):
                if lon >= 180:
                    lon_var[i] = lon - 360
    return climo_data


def convert_flux_var_units(input_file, climo_data):
    """If the file contains a 'pr' or 'prsn' variable, and if its units are per
       second, convert its units to per day.
    """
    flux_vars = [
        var for var in ["pr", "prsn"] if var in input_file.dependent_varnames()
    ]

    for flux_var in flux_vars:
        attributes = {}  # will contain updates, if any, to flux variable attributes
        flux_variable = input_file.variables[flux_var]
        units = Unit.from_udunits_str(flux_variable.units)

        if units in [Unit("kg / m**2 / s"), Unit("mm / s")]:
            logger.info("Converting {} variable to units mm/day".format(flux_var))
            # Update units attribute
            attributes["units"] = (units * Unit("s / day")).to_udunits_str()
            # Multiply values by 86400 to convert from mm/s to mm/day
            seconds_per_day = 86400

            if hasattr(flux_variable, "scale_factor") or hasattr(
                flux_variable, "add_offset"
            ):
                # This is a packed file; need only modify packing parameters
                try:
                    attributes["scale_factor"] = (
                        seconds_per_day * flux_variable.scale_factor
                    )
                except AttributeError:
                    attributes["scale_factor"] = (
                        seconds_per_day * 1.0
                    )  # default value 1.0 for missing scale factor
                try:
                    attributes["add_offset"] = (
                        seconds_per_day * flux_variable.add_offset
                    )
                except AttributeError:
                    attributes[
                        "add_offset"
                    ] = 0.0  # default value 0.0 for missing offset
            else:
                # This is not a packed file; modify the values proper
                # Extract variable
                var_only = cdo.select("name={}".format(flux_var), input=climo_data)
                # Multiply values by 86400 to convert from mm/s to mm/day
                var_only = cdo.mulc(str(seconds_per_day), input=var_only)
                # Replace pr in all-variables file
                climo_data = cdo.replace(input=[climo_data, var_only])

        # Update pr variable metadata as necessary to reflect changes madde
        with CFDataset(climo_data, mode="r+") as cf:
            for attr in attributes:
                setattr(cf.variables[flux_var], attr, attributes[attr])

    return climo_data


def split_on_variables(climo_file, var_names):
    if len(var_names) > 1:
        return [
            cdo.select("name={}".format(var_name), input=climo_file)
            for var_name in var_names
        ]
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
    with CFDataset(climo_filepath, mode="r+") as cf:
        # Add start and end time attributes
        # In Python2.7, datetime.datime.isoformat does not take params telling it how much precision to
        # provide in its output; standard requires 'seconds' precision, which means the first 19 characters.
        cf.climo_start_time = t_start.isoformat()[:19] + "Z"
        cf.climo_end_time = t_end.isoformat()[:19] + "Z"

        # Update tracking_id attribute
        if hasattr(input_file, "tracking_id"):
            cf.climo_tracking_id = input_file.tracking_id

        # Deduce the set of averaging intervals from the number of times in the file.
        # WARNING: This is fragile, and depends on the assumption that a climo output file contains only the following
        # possible contents: multi-decadal averages of monthly, seasonal, and annual averages, possibly concatenated
        # in that order (starting with monthly, seasonal, or annual as the original file contents allow).
        # This computation only works because each case results in a unique number of time values!
        try:
            num_times_to_interval_set = {
                12: {"monthly"},
                4: {"seasonal"},
                1: {"annual"},
                5: {"seasonal", "annual"},
                17: {"monthly", "seasonal", "annual"},
            }
            interval_set = num_times_to_interval_set[cf.time_var.size]
        except KeyError:
            raise ValueError(
                "Expected climo file to contain # time values in {}, but found {}".format(
                    num_times_to_interval_set.keys(), cf.time_var.size
                )
            )

        # Update cell_methods to reflect the operation being done to the data
        validate_operation(operation)
        cell_method_op = {"std": "standard_deviation", "mean": "mean",}[operation]

        for key in cf.variables.keys():
            try:
                cf.variables[key].cell_methods = cf.variables[
                    key
                ].cell_methods + " time: {} over days".format(cell_method_op)
            except AttributeError as e:
                # skip over vars that do not have cell_methods i.e. lat, lon
                continue

        # Update frequency attribute to reflect that this is a climo file.
        suffix = {"std": "SD", "mean": "Mean",}[operation]

        prefix = "".join(
            abbr
            for interval, abbr in (
                ("monthly", "m"),
                ("seasonal", "s"),
                ("annual", "a"),
            )
            if interval in interval_set
        )
        cf.frequency = prefix + "Clim" + suffix

        # Generate info for updating time variable and creating climo bounds variable
        times, climo_bounds = generate_climo_time_var(
            dateutil.parser.parse(
                cf.climo_start_time[:19]
            ),  # create tz naive dates by stripping off the tz indicator
            dateutil.parser.parse(cf.climo_end_time[:19]),
            interval_set,
        )

        # Update time var with CF standard climatological times
        cf.time_var[:] = date2num(times, cf.time_var.units, cf.time_var.calendar)

        # Create new climatology_bnds variable and required bnds dimension if necessary.
        # Note: CDO seems to do some automagic with bounds variable names, converting the string 'bounds' to 'bnds'.
        # For less confusion, we use that convention here, even though original code used the name 'climatology_bounds'.
        # TODO: Should this variable be added to cf.time_var.bounds?
        cf.time_var.climatology = "climatology_bnds"
        if "bnds" not in cf.dimensions:
            cf.createDimension("bnds", 2)
        climo_bnds_var = cf.createVariable("climatology_bnds", "f4", ("time", "bnds",))
        climo_bnds_var.calendar = cf.time_var.calendar
        climo_bnds_var.units = cf.time_var.units
        climo_bnds_var[:] = date2num(
            climo_bounds, cf.time_var.units, cf.time_var.calendar
        )

    return climo_filepath


def update_generate_climos_history(args, netCDF_file, time_cdo_format, position=0):
    """This function takes the start time and end time history-attribute-lines
    of generate_climos command. It returns a string of the entire history
    attribute. The result indicates when the generate_climos started and ended.

    :param netCDF_file: (CFDataset) netCDF file to be updated
    :param time_cdo_format: (str) the point of time that generate_climos_history(start or end) to be updated
    :param position: (int) the position that the new history attribute line will be inserted

    The "position" parameter also implies the start/end flag of the history line
    to be inserted. At the current stage, this function only updates the output
    netCDF file(s) that has been created. Therefore, this function will only be
    called after the first or latter cdo command to insert the "start" flagged
    history line, which makes the position parameter greater than or equal to 1.
    Otherwise, this function will only be called after the last cdo command to
    append the "end" flagged history line, which makes the position parameter
    equal to 0.

    For example:

    :history = 
        "Thu May 21 11:12:04 2020: cdo -O -seldate ..."    <--- position 0
        "Thu May 21 11:12:04: start: generate_climos ..."  <--- position 1: insert "start: genereate_climos"
        "Thu Mar 21 14:49:01 2019: cdo sellonlatbox ..."   <--- position 2
        "Thu Sep  1 14:34:03 2016: ncrcat ..."             <--- position 3
        "Thu Sep 01 14:33:15 2016: cdo -O seldate ..."     <--- position 4
        
        ...

    or

    :history = 
        "Thu May 21 11:12:05: end: generate_climos ..."    <--- position 0: insert "end: genereate_climos"
        "Thu May 21 11:12:05 2020: cdo -O -replace ..."    <--- position 1 
        "Thu May 21 11:12:04 2020: cdo -O -timmean ..."    <--- position 2
        "Thu May 21 11:12:04 2020: cdo -O -seldate ..."    <--- position 3
        "Thu May 21 11:12:04: start: generate_climos ..."  <--- position 4
        "Thu Mar 21 14:49:01 2019: cdo sellonlatbox ..."   <--- position 5
        "Thu Sep  1 14:34:03 2016: ncrcat ..."             <--- position 6
        "Thu Sep 01 14:33:15 2016: cdo -O seldate ..."     <--- position 7

        ...

    """
    # command line input through terminal
    if len(sys.argv) > 1:
        arguments_list = sys.argv[1:]
    # command line input not given
    else:
        arguments_list = list(chain(*args.items()))

    command = ": generate_climos " + " ".join(arguments_list)

    with CFDataset(netCDF_file, "r+") as cf:
        history = cf.history

        # update_generate_climos_history for the start has to be called after the first or latter cdo command
        # update_generate_climos_history for the end has to be called after the last cdo command
        if position != 0:
            hist_line = time_cdo_format + ": start" + command
        else:
            hist_line = time_cdo_format + ": end" + command
        hist_list = history.split("\n")
        hist_list.insert(position, hist_line)

        separ = "\n"
        hist_str = separ.join(hist_list)

        cf.history = hist_str

    return netCDF_file


def validate_operation(operation):
    """
    Given an operation assert that it is supported.  In order to be a supported
    operation it must be in the cdo table of statistical values.
    """
    supported_operations = {
        "mean",
        "std",
    }
    if operation not in supported_operations:
        raise Exception("Unsupported operation: can't yet process {}".format(operation))
