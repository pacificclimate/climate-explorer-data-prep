from netCDF4 import Dataset
import numpy
import random
import string
import logging
import re
import datetime
import os
import math
import time
'''
Formats a netCDF file to meet the CF Standards for Discrete Structured Geometry
data. This is data recorded at one or more distinct locations, instead of at
every point on a grid.

Also corrects some common metadata issues in files output from RVIC.
'''

# Set up logging
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s', "%Y-%m-%d %H:%M:%S")
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)  # For testing, overridden by -l when run as a script

# TODO: make clear with variable names which functions accept a variable object
#    and which the name of one. Better yet, be more consistent about it, pass
#    only what's needed.


def format_dsg_timeseries(outdir, input_file, metadata_files,
                          dry_run, instance_dim, id_var):
    '''Formats a netCDF file to match the CF Standards for Discrete Structured
    Geometries. The original file is unchanged; a new file is created in the
    output directory.
    
    Needed to meet DSG Standards:
        * Determine the "instance dimension" that counts the data locations
        * Determine "instance variables" that have only the instance dimension
          and provide metadata at each location
            - convert character variables with a string length dimension to
              string variables so they can be standard instance variables
        * Designate one instance dimension to act as a unique ID for locations
        * Provide a list of instance variables as a metadata attribute to data variables

    Optional operations done to RVIC data to bring it up to PCIC standards:
        * Import metadata from the hydromodel files used to generate the data
        * Translate RVIC standard metadata into PCIC standard metadata:
            casename -> domain
            history -> creation_date
            fill in time.units if missing
            assign a more descriptive outlet name instead of default "p-0"
    
    The new file will have a randomly generated name.
        
    Terminology note: "instance variable" and "coordinate variable" refer to
    the same group of variables when dealing with discrete sampling datasets.
    (Though not for other datasets). This script refers to "instance variables", 
    but nchelpers calls them "coordinate variables".
    '''

    try:
        input = Dataset(input_file, 'r')
        if not metadata_files:
            metadata_files = []

        random_filename = ''.join(random.choice(string.ascii_lowercase) for i in range(8))
        random_filename = "{}/{}.nc".format(outdir, random_filename)
        output = None if dry_run else Dataset(random_filename, "w", format="NETCDF4")

        # First, copy over dimensions. Don't copy any string length dimensions;
        # we'll be converting character variables to string variables.    
        if output:
            logger.info("Copying dimensions")
            for d in input.dimensions:
                if guess_dim_type(d) != "text":
                    size = None if input.dimensions[d].isunlimited() else len(input.dimensions[d])
                    output.createDimension(d, size)

        # Format variables
        # First determine the instance dimension - this will be the dimension
        # of the number of locations at which data is recorded or calculated.
        # Can be user-specified or determined from the data.
        if not instance_dim:
            instance_dim = guess_instance_dimension(input)
        logger.info("Instance dimension: {}".format(instance_dim))

        # One specific variable provides a unique id for each location in the
        # sampling geometry.
        # This variable is indicated with the cf_role attribute. It is required
        # by the CF standards for discrete sampling geometries.
        # The user may specify which variable it is, it may be identified by the
        # cf_role attribute in the input file, or - as a last resort - the script
        # will check whether there's only one possibility.
        if not id_var:
            id_var = guess_id_variable(input, instance_dim)
        logger.info("Location ID variable: {}".format(id_var))

        # Copy variables to output file
        for var in input.variables:
            write_variable(input, output, var, var == id_var, instance_dim)

        # Global metadata
        logger.info("Copying global metadata")
        if output:
            output.setncatts(input.__dict__)
            output.setncattr("featureType", "timeSeries")

        # Additional metadata
        # Copies metadata from one or more additional files, optionally with a
        # prefix, as specified by user.  Useful for PCIC metadata standards,
        # where metadata "cascades" through each step of data processing,
        # adding a prefix each time - this can add missing metadata from a
        # previous step.
        metadata_conflicts = input.__dict__
        for file in metadata_files:
            logger.info("Adding additional metadata from {}".format(file[1]))
            prefix = file[0]
            dest = output if output else metadata_conflicts
            md_file = Dataset(file[1], 'r')
            copy_global_metadata(md_file, prefix, dest)
            md_file.close()

        # Check for missing metadata required by the PCIC standards, generate it from RVIC
        # equivalents if possible
        rvic_metadata_to_pcic_metadata(input, output, id_var, metadata_files)

        # Update history. Note that default arguments left unspecified by user
        # will be explicitly included.
        logger.info("Updating history attribute")
        hist_entry = '{}: format_dsg_timeseries -o {}{} -i {} -c {} {}\n '.format(
            time.ctime(time.time()),
            outdir,
            " -m {}".format(metadata_files) if metadata_files else "",
            instance_dim,
            id_var,
            input_file
            )
        
        if output:
            output.history = hist_entry + (output.history if "history" in output.__dict__ else "")        
            

    except:
        # something went wrong; close the files.
        input.close()
        if output:
            logger.info("Cleaning up temporary files after error")
            output.close()
            os.remove(random_filename)
        raise
    
    if(output):
        logger.info("Discrete Structured Geometry written to {}".format(random_filename))
        output.close()
    input.close()


def guess_dim_type(dim):
    '''Looks up the name of a dimension in the dictionary and guesses
    what that dimension likely represents'''
    axes = {
        'lat': 'Y',
        'latitude': 'Y',
        'y': 'Y',
        'yc': 'Y',
        'lon': 'X',
        'longitude': 'X',
        'x': 'X',
        'xc': 'X',
        'level': 'Z',
        'depth': 'Z',
        'altitude': 'Z',
        'plev': 'Z',
        'lev': 'Z',
        'time': 'T',
        'timeofyear': 'T',
        'days': 'T',
        'nc_chars': 'text',
        'nv': 'bounds',
        'outlets': 'I'
        }
    return axes[dim] if dim in axes else None


def find_singular_item(list, predicate, description, exception=True):
    '''This function is used when a user hasn't specified which netCDF data
    object (var, dimension, etc) should be used to satisfy the cf standards.
    It determines whether only *one* suitable object exists, and therefore
    should be defaulted to.
    It accepts a list of data objects and a predicate that returns true for a
    data object meeting the desired criteria.The predicate is run on each data
    object. If only one returns true, it is returned. 
    If more or less than one data object fits the criteria, a warning message
    will be printed using the description argument. If the exception argument
    is true, an exception will be thrown as well to bring the whole process to
    a halt.'''
    logger.debug("No {} specified; determining from data".format(description))
    candidates = []
    for c in list:
        if predicate(c):
            candidates.append(c)
    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) == 0:
        msg = ("No possible {} candidates found".format(description))
    else:
        msg = ("Multiple possible {} candidates found: {}".format(description, candidates))
    logger.info(msg)
    if exception:
        raise Exception(msg)
    return candidates


def guess_instance_dimension(nc):
    '''Returns the instance dimension of a dataset: the dimension that
    is nether latitude nor longitude, nor a bounds or string dimension.'''
    def possible_instance_dimension(d):
        return guess_dim_type(d) == "I" or not guess_dim_type(d)
    return find_singular_item(nc.dimensions, possible_instance_dimension, "instance dimension")

def is_instance_variable(nc, var, instance_dim):
    '''Returns true if the selected variable has only the instance 
    dimension and text dimension(s).'''
    for d in nc.variables[var].dimensions:
        if d != instance_dim and guess_dim_type(d) != 'text':
            return False
    return True

def guess_id_variable(nc, instance_dim):
    '''Returns the unique location ID variable of a dataset.
    It may already be specified via the cf_role metadata attribute.
    If not, and there's only one variable that qualifies (has a single
    dimension, the instance dimension), return it.'''
    
    def check_instance_variable(var):
        '''is_instance_variable but with bound arguments so it fits into find_sungular'''
        return is_instance_variable(nc, var, instance_dim)

    # first check whether one variable is already specified
    def is_id_variable(var):
        v = nc.variables[var]
        if 'cf_role' in v.__dict__ and check_instance_variable(v.name):
            if v.getncattr('cf_role') == "timeseries_id":
                return True
            else:
                raise Exception("This process is only for timeseries datasets")
        return False
    variables = find_singular_item(nc.variables, is_id_variable,
                                   "predefined id variable", False)
    variables = listify(variables)
    if len(variables) == 0:
        # no pre-defined id variable. see if we can determine a suitable one
        return find_singular_item(nc.variables, check_instance_variable, "id variable")
    elif(len(variables) == 1):
        return variables[0]
    else:
        # multiple pre-defined id variables: not allowed under CF standards
        raise Exception("Multiple variables have a cf_role metadata attribute: {}".format(variables))


def text_dimension(var):
    '''Returns the name of this variable's text dimension, or None if the
    variable doesn't have a text dimension. Throws an error if the variable
    has more than one text dimension or has a string length dimension but
    isn't a character variable.'''
    text_d = None
    for d in var.dimensions:
        if guess_dim_type(d) == 'text':
            if text_d:
                raise Exception("Error: can't handle multiple text dimensions on variable {}".format(var.name))
            elif var.dtype != 'S1':
                raise Exception("Error: don't understand non-character variable with string length: {}".format(var.name))
            elif len(var.dimensions) == 1:
                raise Exception("Cannot reduce 1-dimensional character variable {}".format(var.name))
            else:
                text_d = d
    return text_d


def creation_date_from_history(hist):
    '''This function attemps to extract a creation date from the 'history'
    metadata attribute. So far, it only understands RVIC 1.1.1's history
    format, which looks like:
        "Created: Fri Jan 18 18:48:23 2019"
    If this script is used for data output by other systems (or if RVIC
    upgrades), this function should be updated.'''
    date = re.search(r'Created: (Sun|Mon|Tue|Wed|Thu|Fri|Sat) (.{3} \d{2} \d{2}:\d{2}:\d{2} \d{4})', hist)
    if date:
        return datetime.datetime.strptime(date[2], '%b %d %H:%M:%S %Y')
    else:
        logger.warning("Don't understand date format of history metadata")
        return None


# TODO: convert to general "find dimension variable" function?
def find_time_variable(input):
    def is_time_variable(var):
        return len(input.variables[var].dimensions) == 1 and guess_dim_type(input.variables[var].dimensions[0]) == 'T'
    return find_singular_item(input.variables, is_time_variable, "time variable", False)


def determine_reference_date(input, output):
    '''This function attempts to determine what the reference date for the time
    variable is, which will be used in the units of the time variable, like
    "days since 1950-01-01 0:0:0" It checks for various possible metadata
    attributes, but falls back on (ugh) parsing the filename if none of them
    are present'''
    # find time variable:
    time_var = find_time_variable(input)
    if time_var:
        # check metadata attributes
        # TODO: this
        if input.getncattr('title') == 'RVIC history file':
            # this rvic history file has the end date in the filename, if it hasn't been renamed.
            filename = input.filepath().split('/')[-1]
            edate = re.search(r'\.(\d{4}-\d{2}-\d{2})\.nc$', filename)
            if edate:
                days = len(input.variables[time_var])
                edate = datetime.datetime.strptime(edate[1], '%Y-%m-%d')
                calendar = input.variables[time_var].getncattr('calendar')
                return subtract_dates(edate, days, calendar)
    return None


def subtract_dates(end, days, calendar):
    '''Return the date n days earlier'''
    if calendar in ['standard', 'gregorian', 'proleptic_gregorian']:
        return end - datetime.timedelta(days=days)
    elif calendar in ['noleap', '365_day']:
        days_per_year = 365
    elif calendar in ['360_day']:
        days_per_year = 360
    else:
        raise Exception("Don't understand calendar type {}".format(calendar))

    year_diff = math.floor(days / days_per_year)
    day_diff = days - year_diff * days_per_year
    sdate = end - datetime.timedelta(days=day_diff)
    return sdate.replace(year=(sdate.year - year_diff))


# TODO: combine date arithmetic functions
def add_dates(start, days, calendar):
    '''Return the day n days later'''
    if calendar in ['standard', 'gregorian', 'proleptic_gregorian']:
        return start + datetime.timedelta(days=days)
    elif calendar in ['noleap', '365_day']:
        days_per_year = 365
    elif calendar in ['360_day']:
        days_per_year = 360
    else:
        raise Exception("Don't understand calendar type {}".format(calendar))

    year_diff = math.floor(days / days_per_year)
    day_diff = days - year_diff * days_per_year
    edate = start + datetime.timedelta(days=day_diff)
    return edate.replace(year=(edate.year + year_diff))


def copy_global_metadata(input, prefix, dest):
    '''This function copies global netCDF attributes from one file to another,
    or from a file to a dictionary, optionally prefixing the attribute names
    with a prefix and two underscores. It does not overwrite existing
    attributes. For dry run purposes, it can be run with just a dictionary,
    not a full netCDF file.'''
    copied = 0
    pre = "{}__".format(prefix) if prefix else ""
    testing = type(dest) == 'dict'
    attributes_list = dest if testing else dest.__dict__
    for m in input.__dict__:
        copied = copied + 1
        prefixed = "{}{}".format(pre, m)
        if prefixed in attributes_list:
            logger.warning("Output file already has a {} attribute".format(prefixed))
            copied = copied - 1
        elif testing:
            dest[prefixed] = input.getncattr(m)
        else:
            dest.setncattr(prefixed, input.getncattr(m))
    logger.info("Copied {} attributes".format(copied))

def is_rvic_output(nc):
    return nc.getncattr('title') == 'RVIC history file'

def equivalent_calendars(a, b):
    calendars = {
        "gregorian": "gregorian",
        "standard": "gregorian",
        "proleptic_gregorian": "gregorian",
        "365_day": "365_day",
        "noleap": "365_day",
        "360_day": "360_day"}
    return calendars[a] == calendars[b]

def copy_time_metadata(src, dest):
    '''This function copies metadata associated with the time variable
    from one file to another. It is intended to be used to update an
    RVIC streamflow result from the hydromodel input used to generate it.
    For some reason, RVIC sets times (possibly incorrectly) with reference
    year 0001.
    It raises an exception rather than doing anything clever in an 
    unexpected case.'''
    src_time = src.variables[find_time_variable(src)]
    dest_time = dest.variables[find_time_variable(dest)]
    
    if not len(src_time) == len(dest_time):
        raise Exception("Cannot compare time metadata if time dimension is unequal {} {}".format(dest.filepath, src.filepath))
    if not equivalent_calendars(src_time.getncattr('calendar'),dest_time.getncattr('calendar')):
        raise Exception("Cannot compare time metadata with two different calendars")
    
    ref_date_pattern = r'days since (\d\d\d\d)-(\d\d?)-(\d\d?)( \d\d?:\d\d?:\d\d?)?'
    ref_date_match = re.match(ref_date_pattern, src_time.getncattr('units'))
    
    if ref_date_match:
        time = ref_date_match.group(4)
        if time:
            time = time.split(':')
            refdate = datetime.datetime(int(ref_date_match.group(1)),
                                        int(ref_date_match.group(2)),
                                        int(ref_date_match.group(3)),
                                        int(time[0]), int(time[1]), int(time[2]))
            
        else:
            refdate = datetime.datetime(int(ref_date_match.group(1)),
                                        int(ref_date_match.group(2)),
                                        int(ref_date_match.group(3)))
        print("refdate = {}".format(refdate))
        dest_time.setncattr('units', 'days since {}'.format(refdate.strftime("%Y-%m-%d")))
        dest_time[:] = src_time[:]
    else:
        raise Exception("Cannot understand format of units string: {}".format(src_time.getncattr('units')))

def rvic_metadata_to_pcic_metadata(input, output, id_var, metadata_files):
    '''RVIC and PCIC have different metadata standards. This function checks
    for attributes required by the PCIC metadata standards, and if they are
    missing or incorrect, generate them from equivalent RVIC metadata.
    
    This function *can* be run on non-RVIC files, but it will print warnings
    about missing metadata instead of correcting it, since assumptions about
    RVIC's data process will not hold true.'''

    # Fix time units
    # For inscrutable reasons, RVIC streamflow files are generated with time.units
    #   "days since 0001-1-1 0:0:0"
    # However, the hydrological datafiles used as *inputs* to RVIC have 
    # valid time values. If this is an RVIC file with an 
    # invalid reference date, and we have a hydromodel output file, copy
    # the relevant values to the time variable.
    zeroed_time_units = [  # update these as new weird 0 dates discovered
        "days since 0001-1-1 0:0:0",
        "days since 1-01-01"
        ]
    time_var = find_time_variable(input)
    if input.variables[time_var].units in zeroed_time_units:
        logger.info("Invalid time units found")
        if is_rvic_output(input):
            def is_hydromodel_input(filearg):
                return filearg[0] == 'hydromodel'            
            hydromodel_file = find_singular_item(metadata_files, is_hydromodel_input, 
                                                 "hydromodel input file", False)
            if isinstance(hydromodel_file, list):
                hf = Dataset(hydromodel_file[1], 'r')
                logger.info("Populating time metadata from hydromodel input file")
                if output:
                    try:
                        copy_time_metadata(hf, output)
                    except Exception as e:
                        print("Unable to correct time variable metadata. Reason: {}".format(e))
                hf.close()
            else:
                logger.warn("Unable to determine hydromodel input file to update time metadata")
        else:
            logger.warn("Cannot correct time units: {}".format(input.variables[time_var].units))

    # PCIC metadata standards require a creation date; parse it from RVIC's history.
    if 'creation_date' not in input.__dict__ and 'history' in input.__dict__:
        logger.info("Generating creation_date from history")
        cdate = creation_date_from_history(input.getncattr('history'))
        if output and cdate:
            output.setncattr('creation_date', str(cdate))
    
    #RVIC files sometimes lack the PCIC required "product" attribute
    if 'product' not in input.__dict__:
        if is_rvic_output(input):
            if output:
                output.setncattr('product', 'streamflow model output')
        else:
            logger.warn("Unknown data product type, metadata update needed")

    # casename, in the RVIC model, is a short alphanumeric code for the
    # location being modeled. If the datafile is missing a domain attribute
    # but has a casename, set the domain equal to the casename.
    if 'casename' in input.__dict__:
        casename = input.getncattr('casename')
        if 'domain' not in input.__dict__:
            logger.info("Generating domain from casename: {}".format(casename))
            if output:
                output.setncattr('domain', casename)
        # the default outlet names generated by RVIC are unhelpfully 'p-0', 'p-1', etc.
        # If the outlet name is 'p-0' and this file contains only a single outlet,
        # set the outlet name equal to the casename attribute.
        if 'outlet_name' in input.variables and id_var == 'outlet_name' and \
           'outlets' in input.dimensions and len(input.dimensions['outlets']) == 1:
            if output.variables['outlet_name'][0] == 'p-0':
                logger.info("Setting outlet name to casename {}".format(casename))
                if output:
                    output.variables['outlet_name'][0] = casename


def write_variable(input, output, var, id_variable, instance_dim):
    '''Copies a variable from the input netCDF to the output netCDF, making the
    following three changes as necessary:
      * char variables with a string length dimension -> vlen variables
      * variable designated the id variable += cf_role: timeseries_id attribute
      * non-instance variables associated with the instance dimension get a
        'coordinates' attribute.
    '''
    reduce_dimension = text_dimension(input.variables[var])
    if reduce_dimension:
        logger.info("Reducing string length dimension of variable {}".format(var))
        new_dimensions = [d for d in input.variables[var].dimensions if d != reduce_dimension]
        if output:
            output.createVariable(var, str, new_dimensions)
            strings = input.variables[var][:]
            strings = [s.tostring().decode('UTF-8') for s in strings]
            strings = [s.rstrip('\x00') for s in strings]  # remove fillers from fixed-length strings
            shape = tuple([len(input.dimensions[d]) for d in new_dimensions])  # match new shape
            strings = numpy.reshape(strings, shape)
            output.variables[var][:] = strings
    else:
        logger.info("Writing variable {}".format(var))
        if output:
            output.createVariable(var, input.variables[var].dtype, input.variables[var].dimensions)
            output.variables[var][:] = input.variables[var][:]

    if output:
        # variable attributes
        output.variables[var].setncatts(input.variables[var].__dict__)
        outvar = output.variables[var]

        # indicate the id variable
        if id_variable:
            outvar.setncattr('cf_role', 'timeseries_id')
        
        # if this is a data variable, it needs a 'coordinates' attribute
        # containing a list of all the instance variables
        if instance_dim in outvar.dimensions and len(outvar.dimensions) > 1:
            coordinates = ""
            for v in input.variables:
                if is_instance_variable(input, v, instance_dim):
                    coordinates = "{} {}".format(coordinates, v)
            outvar.setncattr('coordinates', coordinates.strip())
            


def remove_time_offset(output):
    '''Corrects files that have a reference date of January 1 0001 by updating
    the time (and time_bnds) variables. Assigns a new reference date in
    time.units, and subtracts an appropriate amount from the values time and
    time_bnds. Done because using a pre-gregorian reference date for data in
    the gregorian era is incorrect.'''

    # find variables that will need updating
    def is_timestamp_variable(var):
        for d in output.variables[var].dimensions:
            if guess_dim_type(d) not in ['bounds', 'T']:
                return False
        return True
    timestamps = find_singular_item(output.variables, is_timestamp_variable, "timestamp variables", False)
    timestamps = listify(timestamps)
    timevar = find_time_variable(output)
    timevar = output.variables[timevar]

    # find the earliest timestamp, which will be the new reference date
    min_stamp = math.floor(min([numpy.min(output.variables[v][:]) for v in timestamps]))

    units_format = r'days since (\d\d?\d?\d?)-(\d\d?)-(\d\d?)( \d\d:\d\d:\d\d)?'
    old_date_match = re.match(units_format, timevar.units)
    old_ref_date = datetime.datetime(int(old_date_match.group(1)),
                                     int(old_date_match.group(2)),
                                     int(old_date_match.group(3)))
    ref_hour = old_date_match[4] if old_date_match[4] else ""
    new_ref_date = add_dates(old_ref_date, min_stamp, timevar.calendar)

    logger.info("Reference date for time dimension is {}".format(old_ref_date))
    new_ref_string = new_ref_date.strftime("%Y-%m-%d")
    logger.info("Normalizing reference date for {} to {}".format(timestamps, new_ref_date))
    output.variables[timevar].units = "days since {}{}".format(new_ref_string, ref_hour)
    for v in timestamps:
        normalized = output.variables[v][:] - min_stamp
        output.variables[v][:] = normalized


# TODO: rewrite find_singular_item so this function isn't needed.
def listify(x):
    'returns a list containing x, or just x if x is already a list'
    return x if isinstance(x, list) else [x]
