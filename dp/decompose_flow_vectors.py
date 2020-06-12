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


def decompose_flow_vectors(source, dest_file, variable):
    #create destination file, same grid as original file
    dest = Dataset(dest_file, "w", format="NETCDF4")  

    def create_graticule_variables(axis):
        dest.createDimension(axis, source.dimensions[axis].size)
        dest.createVariable(axis, "f8", (axis))
        dest.variables[axis].setncatts(source.variables[axis].__dict__)
        dest.variables[axis][:] = source.variables[axis][:]

    create_graticule_variables("lat")
    create_graticule_variables("lon")

    def create_vector_variables(direction):
        dir_vec = "{}ward_{}".format(direction, variable)
        dest.createVariable(dir_vec, "f8", ("lat", "lon"))
        dest.variables[dir_vec].units = "1"
        dest.variables[dir_vec].standard_name = dir_vec #ncWMS relies on standard names
        dest.variables[dir_vec].long_name = "Normalized {}ward vector component of {}".format(direction, variable)

        return dir_vec

    eastvec = create_vector_variables("east") 
    northvec = create_vector_variables("north")

    #populate variables with decomposed vectors.
    directions = [[0,0], #0 = filler
                [1, 0], # 1 = N
                [.7071, .7071], #2 = NE
                [0, 1], #3 = E
                [-.7071, .7071], #4 = SE
                [-1, 0], #5 = S
                [-.7071, -.7071], #6 = SW
                [0, -1], #7 = W
                [.7071, -.7071], #8 = NW
                [0, 0]] #9 = outlet

    dir_axis ={"eastward": 1, "northward": 0}

    def generate_vector_component(dir_vec, direction):
        logger.info("Generating {} component".format(direction))
        axis_idx = dir_axis[direction]
        vector_components = np.ma.copy(source.variables[variable][:])
        for (x, y), dir in np.ndenumerate(vector_components):
            if dir >= 0 and dir <= 9:
                vector_components[x][y] = directions[int(dir)][axis_idx]
        dest.variables[dir_vec][:] = vector_components

    generate_vector_component(eastvec, "eastward")
    generate_vector_component(northvec, "northward")

    #copy global attributes to the new file.        
    dest.setncatts(source.__dict__)

    #update history attribute, if present, to include this script
    if "history" in dest.ncattrs():
        dest.history ="{} {} {} {} {}\n".format(time.ctime(time.time()), "decompose_flow_vectors", source.filepath(), dest_file, variable) + dest.history

    source.close()
    dest.close()