"""Helper functions for parsing and manipulating streamflow files."""

from nchelpers import CFDataset, CFAttributeError
import re
import time
import logging
from dp.generate_climos import logger

def split_casestr(nc):
    """Reads a netCDF file with a 'casestr' global attribute, such as:
    
    casestr = "ACCESS1-0.historical+rcp45.r1i1p1" ;
    
    and attempts to interpret the string as MODEL.SCENARIO.RUN and 
    populate global attributes model_id, experiment_id, and the 
    ensemble attributes (realization, initialization_method, and physics_version) 
    accordingly, with some minimal validation. Modifies the dataset
    passed to it by adding the three global attributes.
    
    This is a useful shortcut for functions with missing metadata, but starting with
    complete metadata is a better idea."""

    known_models = [#GCMs we've used
                    "CanESM2", "MRI-CGCM3", "CNRM-CM5", 
                     "MIROC5", "inmcm4", "HadGEM2-ES",
                     "GFDL-ESM2G", "CCSM4", "ACCESS1-0",
                     "HadGEM2-CC", "MPI-ESM-LR", "CSIRO-Mk3-6-0",
                     "HadGEM2-ES", "NCEP1", "CCSM3", "CGSM3", 
                     "ECHAM5", "CSIRO35", "GFDL2.1", "HadCM", 
                     "HadGEM1", "MIROC3.2", "BASE", 
                     #RCMs we've used
                     "CSIRO", "HADCM", "HADGEM1"]
    
    scenarios = ["rcp26", "rcp45", "rcp60", "rcp85"]
    
    overwrites = ["model_id", "experiment_id", "realization", "initialization_method", "physics_version"]

    if not "casestr" in nc.ncattrs():
        raise CFAttributeError("{} does not have a casestr global attribute".format(nc.getfilepath()))
    
    logger.info("Populating missing metadata from casestr {}".format(nc.casestr))
    
    values = nc.casestr.split(".")
    if len(values) != 3:
        raise ValueError("Expected casestr attribute to have format MODEL.SCENARIO.RUN, found {}"
                         .format(nc.casestr))
    
    [model, scenario, run] = values

    if not model in known_models:
        raise ValueError("Unrecognized model in casestr: {}".format(model))
    
    if (not scenario in scenarios) and (scenario != "historical") and (not scenario in list(map(lambda s:"historical+" +s, scenarios))):
        raise ValueError("Unrecognized scenarios in casestr: {}".format(scenario))
    
    run_regex = re.match(r'r(\d*)i(\d*)p(\d*)', run)
    if not run_regex:
        raise ValueError("Couldn't parse ensemble member identifier {}".format(run))
    
    for att in overwrites:
        if att in nc.ncattrs():
            raise CFAttributeError("{} attribute already present in file, cannot populate from casestr".format(att))    
    
    nc.model_id = model
    nc.experiment_id = scenario
    nc.realization = run_regex.group(1)
    nc.initialization_method = run_regex.group(2)
    nc.physics_version = run_regex.group(3)
    
    update_history_attribute(nc, "split_casestr {}".format(nc.filepath()))
    
def post_cdo_restore_dimension_names(source, dest, ignoreDimensions = []):    
    """Older versions of CDO automatically rename dimensions to 'canonical' names.
    This function detects renamed dimensions between source and destination files and 
    restores their original names from the source file.
    
    CDO is designed to handled grid input, and assumes input files contain a grid, 
    and will determine which dimensions are spatial dimensions and rename them 
    accordingly. This is misleading when dealing with station-based datasets like streamflow 
    data, which have a non-spatial "instance dimension" such as 'outlet', 'station',
    or 'location'. Older versions of CDO will interpret these dimensions as spatial 
    grid dimensions and assign canonical names like "x", "lat", or "gsize".
    
    This function is conservative and raises an error if it notices anything 
    complicated, such as a genuinely new dimension with no correspondence in 
    the original. An optional list of dimension to ignore can be provided."""    
    changes = []
    changed = False
    logger.info("Checking for dimensions renamed by CDO")
    
    for ddim in dest.dimensions:
        if ddim not in source.dimensions and ddim not in ignoreDimensions:
            #Try to match the new dimension up with an original dimension based on size,
            #ignoring all dimensions already present in the destination file.
            candidates = []
            for sdim in source.dimensions:
                if (source.dimensions[sdim].isunlimited() == dest.dimensions[ddim].isunlimited()) \
                and(source.dimensions[sdim].size == dest.dimensions[ddim].size) \
                and(sdim not in dest.dimensions):
                    candidates.append(sdim)
            
            if len(candidates) == 1:
                changes.append((ddim, candidates[0]))
            else :
                if len(candidates == 0):
                    raise Error("Could not find an original dimension for {}".format(ddim))
                elif len(candidates > 1):
                    raise Error("Can not resolve multiple possible original dimensions for {}. Possibilities: {}".format(ddim, candidates))

    for change in changes:
        changed = True
        logger.info("Renaming dimension {} to original name {}".format(change[0], change[1]))
        dest.renameDimension(change[0], change[1])
    
    if changed:
        update_history_attribute(dest, "post_cdo_restore_dimension_names {} {} {}".format(source.filepath(), dest.filepath(), ignoreDimensions))
    
def post_cdo_restore_text_variables(source, dest, instance = None):
    """Given a source file and a destination file produced by CDO, this function copies
    text variables (and any dimensions they require) from the source file to the destination.
    
    Older versions of CDO drop all text variables from any file it produces. CDO's rationale 
    is that text variables don't represent data, and CDO is only concerned with data. However, 
    the CF standards allow using text variables as "station variables" to describe
    individual stations or study sites. For station-based datasets, we'd like to retain those 
    variables.
    
    A text variable may either have the string data type (NetCDF 4+), or may have the char data
    type and a string length dimension (classic NetCDF). In the latter case, CDO will have deleted
    the string length dimension along with the text variables; unused dimensions are deleted.

    If an instance variable is given, only "station variables" corresponding to it will be restored.
    This function should be run after post_cdo_restore_dimension_names(); it assumes dimension
    names correspond to the original file (IE, for detecting missing string length dimensions.)

    A notice will be displayed for any deleted variables or dimensions that aren't strings or
    station variables, but nothing will be done about them."""
    
    logger.info("Checking for variables dropped by CDO")
    
    for svar in source.variables:
        changed = False
        if svar not in dest.variables:
            logger.info("Variable {} is missing from destination file.".format(svar, source.variables[svar].datatype))
            if(not instance or instance in source.variables[svar].dimensions)\
            and (source.variables[svar].dtype == '|S1'): #TODO: support NC4 string types
                for vdim in source.variables[svar].dimensions:
                    if vdim not in dest.dimensions:
                        logger.info("Creating dimension {}, required by variable {}".format(vdim, svar))
                        dest.createDimension(vdim, source.dimensions[vdim].size)

                dest.createVariable(svar, source.variables[svar].datatype, source.variables[svar].dimensions)
                dest.variables[svar][:] = source.variables[svar][:]
                dest.variables[svar].setncatts(source.variables[svar].__dict__)
                logger.info("Restoring variable {}".format(svar))
                changed = True
            else:
                logger.warn("Variable {} variable missing in output, unable to automatically restore".format(svar))
        if changed:
            update_history_attribute(dest, "post_cdo_restore_text_variables {} {}".format(source.filepath(), dest.filepath()))

def update_history_attribute(file, text):
    """Prepends the specified text, with a datestamp, to the global history attribute.
    Creates history if there isn't one."""
    file.history = "{}: {}\n".format(time.ctime(time.time()), text) + (file.history if "history" in file.ncattrs() else "")