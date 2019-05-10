from netCDF4 import Dataset
import numpy
import random, string, logging, re, datetime, os, math

# Set up logging
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s', "%Y-%m-%d %H:%M:%S")
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)  # For testing, overridden by -l when run as a script

# TODO: rename instances of cf_role_variable to id_variable or something.
# TODO: make clear with variable names which functions accept a variable object 
#    and which the name of one. Better yet, be more consistent about it, pass
#    only what's needed.
# TODO: rename a bunch of stuff, less RVIC-centric.

def format_rvic_output(outdir, input_file, hydromodel_files, dry_run, instance_dim, cf_role_var):
    '''Formats a file output by RVIC to match both the CF Standards for 
    Discrete Structured Geometries and the PCIC Standards for Routed
    Streamflow Data. The original file is unchanged; a new file is output.
    
    Needed to meet DSG Standards:
        * Designate outlet_name the timeseries_id for the outlet dimension
          and set its value from the casestr
        * Convert any variables with a character length dimension into
          strings (so they can be proper instance variables with only the
          instance dimensions)
    
    Needed to meet PCIC Standards because RVIC's metadata is a little odd:
        * Add metadata about the hydromodel used to generate the data 
          from the hydromodel file input to RVIC
        * Translate some RVIC metadata into PCIC metadata standards:
            casename -> domain
            history -> creation_date
            model_[start|end]_[year|month|day] -> time.units            
        
    Not associated with any standard, but nice to have:
        * Renamed to a CMOR-style filename
        * outlet_name is usually generated as "p-0" - set it to the  (more unique)
          casename instead
    '''
    
    try:
        rvic = Dataset(input_file, 'r')
        #hydromodel = Dataset(hydromodel_file, 'r') if hydromodel_files else []
        #TODO - parse hydromodel files
        if not hydromodel_files:
            hydromodel_files = []
    
        random_filename = ''.join(random.choice(string.ascii_lowercase) for i in range(8))
        random_filename = "{}/{}.nc".format(outdir, random_filename)
        output = None if dry_run else Dataset(random_filename, "w", format="NETCDF4")
    
        # First, copy over dimensions. Don't copy any string length dimensions - we'll be
        # converting character variables to string variables.    
        if output:
            logger.info("Copying dimensions")
            for d in rvic.dimensions:
                if guess_dim_type(d) != "text":
                    size = None if rvic.dimensions[d].isunlimited() else len(rvic.dimensions[d])
                    output.createDimension(d, size)
                
        # Format variables
        # First determine the instance dimension - this will be the dimension of the number
        # of locations at which data is recorded or calculated. Can be user-specified or 
        # guessed.
        if not instance_dim:
            instance_dim = guess_instance_dimension(rvic)
        logger.info("Instance dimension: {}".format(instance_dim))
    
        # The cf_role variable provides metadata about each location, like a name or unique
        # id number for each. It is required by the CF standards for discrete sampling geometries.
        # The user may specify which variable it is, it may be identified by the cf_role attribute
        # in the input file, or - as a last resort - the script will attempt to guess.
        if not cf_role_var:
            cf_rolevar = guess_cf_role_variable(rvic, instance_dim)
        logger.info("Cf_role variable: {}".format(cf_role_var))
    
        # Copy variables to output file
        for var in rvic.variables:
            write_variable(rvic, output, var, var == cf_role_var)    
    
        # Global metadata
        logger.info("Copying global metadata")
        if output:
            output.setncatts(rvic.__dict__)
    
        # Additional metadata
        # Copies metadata from one or more additional files, optionally with a prefix,
        # as specified by user.  Useful for PCIC metadata standards, where metadata
        # "cascades" through each step of data processing, adding a prefix each time - 
        # this can add missing metadata from a previous step.
        metadata_conflicts = rvic.__dict__
        for file in hydromodel_files:
            logger.info("Adding additional metadata from {}".format(file))
            prefix = file[1] if length(file) > 1 else None
            dest = output if output else metadata_conflicts
            md_file = Dataset(file[0], 'r')
            copy_global_metadata(md_file, prefix, dest)
            nc.close(md_file)
            
        # Check for missing metadata required by the PCIC standards, generate it from RVIC
        # equivalents if possible
        rvic_metadata_to_pcic_metadata(rvic, output, cf_role_var)
    
        #Update history.
        logger.info("Updating history attribute")
    
    except:
        # something went wrong; close the files.
        rvic.close()
        if output:
            logger.info("Cleaning up temporary files after error")
            output.close()
            os.remove(random_filename)
        raise
    #Generate a CMOR-type filename and rename the output file.
    
    #Done!
    
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
    
    
def find_singular_item(list, predicate, description, exception = True):
    '''This function is used when a user hasn't specified which netCDF data object
    (var, dimension, etc) should be used to satisfy the cf standards. It determines
    whether only *one* suitable object exists, and therefore should be defaulted to.
    It accepts a list of data objects and a predicate that returns true for a data
    object meeting the desired criteria.The predicate is run on each data object.
    If only one returns true, it is returned. 
    If more or less than one data object fits the criteria, a warning message
    will be printed using the description argument. If the exception argument is
    true, an exception will be thrown as well to bring the whole process to a halt.'''
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
        
def guess_cf_role_variable(nc, instance_dim):
    '''Returns the cf_role variable of a dataset.
    It may already be specified via the cf_role metadata attribute.
    If not, and there's only one variable that qualifies (has a single
    dimension, the instance dimension), return it.'''
    
    # checks whether a variable is an "instance variable" - has only the instance dimension.
    # text dimensions don't count.
    def possible_cf_role_var(var):
        for d in nc.variables[var].dimensions:
            print("dimension: {}".format(d))
            if d != instance_dim and guess_dim_type(d) != 'text':
                return False
        return True
    
    #first check whether one variable is already specified
    def is_cf_role_variable(var):
        v = nc.variables[var]
        if 'cf_role' in v.__dict__ and possible_cf_role_var(v.name):
            if v.getncattr('cf_role') == "timeseries_id":
                return True
            else:
                raise Exception("This script only works for timeseries discrete structured datasets")
        return False
    variables = find_singular_item(nc.variables, is_cf_role_variable, "predefined id variable", False)
    variables = [variables] if not isinstance(variables, list) else variables #TODO - declumsify this.
    if len(variables) == 0: 
        #no pre-defined id variable. see if we can determine a suitable one
        return find_singular_item(nc.variables, possible_cf_role_var, "cf_role_variable")
    elif(len(variables) == 1):
        return variables[0]
    else:
        #multiple pre-defined id variables: not allowed under CF standards
        raise Exception("Multiple variables have a cf_role metadata attribute: {}".format(variables))
    
def text_dimension(var):
    '''Returns the name of this variable's text dimension, or None if the variable
    doesn't have a text dimension. Throws an error if the variable has more than one
    text dimension or has a string length dimension but isn't a character .'''
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
    '''This function attemps to extract a creation date from the 'history' metadata
    attribute. So far, it only understands RVIC's history format, which looks like:
        "Created: Fri Jan 18 18:48:23 2019" 
    If this script is used for data output by other systems (or if RVIC upgrades), this
    function should be updated.'''
    date = re.search(r'Created: (Sun|Mon|Tue|Wed|Thu|Fri|Sat) (.{3} \d{2} \d{2}:\d{2}:\d{2} \d{4})', hist)
    if date:
        return datetime.datetime.strptime(date[2], '%b %d %H:%M:%S %Y')
    else:
        logger.warning("Don't understand date format of history metadata")
        return None

#TODO: convert to general "find dimension variable" function?
def find_time_variable(input):
    def is_time_variable(var):
        return len(input.variables[var].dimensions) == 1 and guess_dim_type(input.variables[var].dimensions[0]) == 'T'
    return find_singular_item(input.variables, is_time_variable, "time variable", False)
    
def determine_reference_date(input, output):
    '''This function attempts to determine what the reference date for the time variable
    is, which will be used in the units of the time variable, like 
    "days since 1950-01-01 0:0:0" It checks for various possible metadata attributes,
    but falls back on (ugh) parsing the filename if none of them are present'''
    #find time variable:    
    time_var = find_time_variable(input)
    if time_var:
        #check metadata attributes
        if input.getncattr('title') == 'RVIC history file':
            #this rvic history file has the end date in the filename, if it hasn't been renamed.
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

#TODO: combine date arithmetic functions
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
    or from a file to a dictionary, optionally prefixing the attribute names with 
    a prefix and two underscores. It does not overwrite existing attributes.
    For dry run purposes, it can be run with just a dictionary, not a real netCDF
    file.'''
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
    
    
    
def rvic_metadata_to_pcic_metadata(input, output, cf_role_var):
    '''RVIC and PCIC have different metadata standards. This function checks for 
    attributes required by the PCIC metadata standards, and if they are missing
    or incorrect, generate them from equivalent RVIC metadata.'''
    
    # Fix time units - RVIC files are sometimes generated with time.units 
    #   "days since 0001-1-1 00:00:00"
    # This occurs for two reasons, which require different fixes:
    #    1. No reference date at all was set, default supplied
    #    2. The dodgy pre-gregorian reference date was intended.
    
    zeroed_time_units = [ #update these as new weird reference dates show up in the data
        "days since 0001-1-1 0:0:0",
        "days since 1-01-01"
        ]
    time_var = find_time_variable(input)
    if input.variables[time_var].units in zeroed_time_units:
        logger.info("Invalid time units found")
        if input.variables[time_var][0] == 0: # no reference date set, try to find one in metadata attributes
            ref_date = determine_reference_date(input, output)
            if output and ref_date:
                output.variables[time_var].units = 'days since {}'.format(ref_date.strftime('%Y-%m-%d %H:%M:%S'))
        elif input.variables[time_var][0] > 577460: # pre-gregorian ref date used for gregorian-era data
            logger.warn("Correcting pre-gregorian reference dates is not implemented yet.")
            #remove_time_offset(output) #update data to a post-gregorian ref date
        else:
            raise Exception("Can't handle date mapping in this dataset")
            
    
    # PCIC metadata standards require a creation date; parse it from RVIC's history.
    if not 'creation_date' in input.__dict__ and 'history' in input.__dict__:
        logger.info("Generating .creation_date from .history")
        cdate = creation_date_from_history(input.getncattr('history'))
        if output and cdate:
            output.setncattr('history', 'cdate')
    
    # casename, in the RVIC model, is a short alphanumeric code for the location being 
    # simulated. If the datafile is missing a domain attribute but has a casename,
    # set the domain equal to the casename.
    if 'casename' in input.__dict__:
        if not 'domain' in input.__dict__:
            logger.info("Generating .domain from .casename: {}".format(input.getncattr('casename')))
            if output:
                output.setncattr('domain', input.getncattr('casename'))
        # the default outlet names generated by RVIC are unhelpfully 'p-0', 'p-1', etc. 
        # If the outlet name is 'p-0' and this file contains only a single outlet,
        # set the outlet name equal to the casename attribute.
        if 'outlet_name' in input.variables and cf_role_var == 'outlet_name' and \
           'outlets' in input.dimensions and len(input.dimensions['outlets']) == 1:
            if output.variables['outlet_name'][0] == 'p-0':
                logger.info("Setting outlet name to casename {}".format(input.getncattr('casename')))
                if output:
                    output.variables['outlet_name'][0] = input.getncattr('casename')
    
def write_variable(input, output, var, cf_variable):
    '''Copies a variable from the input netCDF to the output netCDF, making the 
    following two changes as necessary:
      * character variables with a string length dimension will be redone as vlen variables
      * variables designated the cf_variable will get a cf_role: timeseries_id attribute
    '''
    reduce_dimension = text_dimension(input.variables[var])
    if reduce_dimension:
        logger.info("Reducing string length dimension of variable {}".format(var))
        new_dimensions = [d for d in input.variables[var].dimensions if d != reduce_dimension]
        if output:
            output.createVariable(var, str, new_dimensions)
            strings = input.variables[var][:]
            strings = [s.tostring().decode('UTF-8') for s in strings]
            strings = [s.rstrip('\x00') for s in strings] # remove fillers from fixed-length strings
            shape = tuple([len(input.dimensions[d]) for d in new_dimensions]) #match new shape
            strings = numpy.reshape(strings, shape)
            output.variables[var][:] = strings
            
    else:
        logger.info("Writing variable {}".format(var))
        if output:
            output.createVariable(var, input.variables[var].dtype, input.variables[var].dimensions)
            output.variables[var][:] = input.variables[var][:]

    if output:
        #variable attributes
        output.variables[var].setncatts(input.variables[var].__dict__)
        
        #indicate the cf_role variable
        if cf_variable:
            output.variables[var].setncattr('cf_role', 'timeseries_id')
            
def remove_time_offset(output):
    '''Corrects files that have a reference date of January 1 0001 by updating
    the time (and time_bnds) variables. Assigns a new reference date in time.units,
    and subtracts an appropriate amount from the values time and time_bnds.
    Done because using a pre-gregorian reference date for data in the gregorian
    error is incorrect.'''
    
    #find variables that will need updating
    def is_timestamp_variable(var):
        for d in output.variables[var].dimensions:
            if guess_dim_type(d) not in ['bounds', 'T']:
                return False
        return True
    timestamps = find_singular_item(output.variables, is_timestamp_variable, "timestamp variables", False)
    timestamps = [timestamps] if not isinstance(timestamps, list) else timestamps
    timevar = find_time_variable(output)
        
    #find the earliest timestamp, which will be the new reference date
    min_stamp = math.floor(min([numpy.min(output.variables[v][:]) for v in timestamps]))
    
    units_format = r'days since (\d\d?\d?\d?)-(\d\d?)-(\d\d?)( \d\d:\d\d:\d\d)?'
    old_date_match = re.match(units_format, output.variables[timevar].units)
    old_ref_date = datetime.datetime(int(old_date_match.group(1)), int(old_date_match.group(2)), int(old_date_match.group(3)))
    ref_hour = old_date_match[4] if old_date_match[4] else ""
    new_ref_date = add_dates(old_ref_date, min_stamp, output.variables[timevar].calendar)
    
    logger.info("Reference date for time dimension is {}".format(old_ref_date))
    logger.info("Normalizing reference date for {} to {}".format(timestamps, new_ref_date))
    
    output.variables[timevar].units = "days since {}{}".format(new_ref_date.strftime("%Y-%m-%d"), ref_hour)
    for v in timestamps:
        normalized = output.variables[v][:] - min_stamp
        output.variables[v][:] = normalized
