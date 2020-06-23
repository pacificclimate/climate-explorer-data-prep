#!python
from netCDF4 import Dataset
import numpy as np
import time
import logging

# Set up logging
formatter = logging.Formatter(
    "%(asctime)s %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"
)
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)  # For testing, overridden by -l when run as a script


def log_and_raise_exception(source, err_msg, exc):
    logger.critical(err_msg)
    source.close()
    raise exc(err_msg)


def source_check(source):
    source_file_path = source.filepath()

    if not "lon" in source.dimensions or not "lat" in source.dimensions:
        err_msg = "{} does not have latitude and longitude dimensions".format(
            source_file_path
        )
        log_and_raise_exception(source, err_msg, AttributeError)

    valid_variables = []
    for v in source.variables:
        variable = source.variables[v]
        if (
            hasattr(variable, "dimensions")
            and "lon" in variable.dimensions
            and "lat" in variable.dimensions
        ):
            if np.ma.max(variable[:]) <= 9 and np.ma.min(variable[:]) >= 1:
                valid_variables.append(v)

    if len(valid_variables) == 0:
        err_msg = "{} does not have a valid flow variable".format(source_file_path)
        log_and_raise_exception(source, err_msg, ValueError)


def variable_check(source, variable):
    source_file_path = source.filepath()

    if not variable in source.variables:
        err_msg = "Variable {} is not found in {}".format(variable, source_file_path)
        log_and_raise_exception(source, err_msg, AttributeError)

    flow_variable = source.variables[variable]

    if not "lon" in flow_variable.dimensions or not "lat" in flow_variable.dimensions:
        err_msg = "Variable {} is not associated with a grid".format(variable)
        log_and_raise_exception(source, err_msg, AttributeError)

    if np.ma.max(flow_variable[:]) > 9 or np.ma.min(flow_variable[:]) < 1:
        err_msg = "Variable {} is not a valid flow routing".format(variable)
        log_and_raise_exception(source, err_msg, ValueError)


def decompose_flow_vectors(source, dest_file, variable):
    """
    Process an indexed flow direction netCDF into a vectored netCDF suitable for
    ncWMS display.

    :param source: (netCDF4 Dataset) source netCDF Dataset
    :param dest_file: (str) path to destination netCDF file
    :param variable: (str) netCDF variable describing flow direction
    """
    # create destination file, same grid as original file
    dest = Dataset(dest_file, "w", format="NETCDF4")

    create_graticule_variables("lat", source, dest)
    create_graticule_variables("lon", source, dest)

    eastvec = create_vector_variables("east", dest, variable)
    northvec = create_vector_variables("north", dest, variable)

    generate_vector_component(eastvec, source, dest, variable)
    generate_vector_component(northvec, source, dest, variable)

    # copy global attributes to the new file.
    dest.setncatts(source.__dict__)

    # update history attribute, if present, to include this script
    if "history" in dest.ncattrs():
        dest.history = (
            "{} {} {} {} {}\n".format(
                time.ctime(time.time()),
                "decompose_flow_vectors",
                source.filepath(),
                dest_file,
                variable,
            )
            + dest.history
        )

    source.close()
    dest.close()


def create_graticule_variables(axis, source, dest):
    """
    this function adds a netCDF graticule component variable(latitude/longitude)
    inside the destination file.
    
    :param axis: (str) a griticule component to be created
    :param source: (netCDF4 Dataset) source netCDF Dataset
    :param dest_file: (str) path to destination netCDF file
    """
    dest.createDimension(axis, source.dimensions[axis].size)
    dest.createVariable(axis, "f8", (axis))
    dest.variables[axis].setncatts(source.variables[axis].__dict__)
    dest.variables[axis][:] = source.variables[axis][:]


def create_vector_variables(direction, dest, variable):
    """
    this function adds a netCDF direction vector component variable(eastward/nothward)
    inside the destination file.
    
    :param direction: (str) a direction vector component to be created
    :param dest: (str) path to destination netCDF file
    :param variable: (str) netCDF variable describing flow direction
    """
    dir_vec = "{}ward_{}".format(direction, variable)
    dest.createVariable(dir_vec, "f8", ("lat", "lon"))
    dest.variables[dir_vec].units = "1"
    dest.variables[dir_vec].standard_name = dir_vec  # ncWMS relies on standard names
    dest.variables[
        dir_vec
    ].long_name = "Normalized {}ward vector component of {}".format(direction, variable)

    return dir_vec


def generate_vector_component(dir_vec, source, dest, variable):
    """
    This function converts source file's VIC model vector values to
    destination file's Two-Grid vector values. Basically, it splits 
    off a direction into x-y(eastward-northward) coordinates.

    :param dir_vec: (str) a direction vector component variable to be generated
    :param source: (netCDF4 Dataset) source netCDF Dataset
    :param dest_file: (str) path to destination netCDF file
    :param variable: (str) netCDF variable describing flow direction
    """

    # populate variables with decomposed vectors.
    # indices indicate VIC model vector values
    two_grid_vectors = [
        [0, 0],  # 0 = filler
        [1, 0],  # 1 = N
        [0.7071, 0.7071],  # 2 = NE
        [0, 1],  # 3 = E
        [-0.7071, 0.7071],  # 4 = SE
        [-1, 0],  # 5 = S
        [-0.7071, -0.7071],  # 6 = SW
        [0, -1],  # 7 = W
        [0.7071, -0.7071],  # 8 = NW
        [0, 0],
    ]  # 9 = outlet

    two_grids = {"eastward": 1, "northward": 0}

    grid_dir = dir_vec.split("_")[0]
    logger.info("Generating {} component".format(grid_dir))
    grid_idx = two_grids[grid_dir]

    # vectors_field is consist of VIC Routing Directional Vector Values
    vectors_field = np.ma.copy(source.variables[variable][:])
    # for loop changes the VIC Vectors into Two-Grid Vectors
    for (x, y), dir in np.ndenumerate(vectors_field):
        if dir >= 0 and dir <= 9:
            vectors_field[x][y] = two_grid_vectors[int(dir)][grid_idx]

    dest.variables[dir_vec][:] = vectors_field
