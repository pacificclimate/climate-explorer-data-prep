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
    '''
    Process an indexed flow direction netCDF into a vectored netCDF suitable for
    ncWMS display.

    :param source: (netCDF4 Dataset) source netCDF Dataset
    :param dest_file: (str) path to destination netCDF file
    :param position: (str) netCDF variable describing flow direction
    '''

    def create_graticule_variables(axis, dest):
        '''
        this function adds a netCDF graticule component variable(latitude/longitude)
        inside the destination file.
        
        :param axis: (str) a griticule component to be created
        :param dest: (str) path to destination netCDF file
        '''
        dest.createDimension(axis, source.dimensions[axis].size)
        dest.createVariable(axis, "f8", (axis))
        dest.variables[axis].setncatts(source.variables[axis].__dict__)
        dest.variables[axis][:] = source.variables[axis][:]

    def create_vector_variables(direction, dest):
        '''
        this function adds a netCDF direction vector component variable(eastward/nothward)
        inside the destination file.
        
        :param direction: (str) a direction vector component to be created
        :param dest: (str) path to destination netCDF file
        '''
        dir_vec = "{}ward_{}".format(direction, variable)
        dest.createVariable(dir_vec, "f8", ("lat", "lon"))
        dest.variables[dir_vec].units = "1"
        dest.variables[dir_vec].standard_name = dir_vec #ncWMS relies on standard names
        dest.variables[dir_vec].long_name = "Normalized {}ward vector component of {}".format(direction, variable)

        return dir_vec

    #create destination file, same grid as original file
    dest = Dataset(dest_file, "w", format="NETCDF4") 
 
    create_graticule_variables("lat", dest)
    create_graticule_variables("lon", dest)

    eastvec = create_vector_variables("east", dest) 
    northvec = create_vector_variables("north", dest)

    def generate_vector_component(dir_vec, two_grid_vectors, two_grids, grid_dir, dest):
        '''
        This function converts source file's VIC model vector values to
        destination file's Two-Grid vector values. Basically, it splits 
        off a direction into x-y(eastward-northward) coordinates.

        :param dir_vec: (str) a direction vector component variable to be generated
        :param two_grid_vectors: (list) a list of Two-Grid vectors corresponding to VIC model vector values
        :param two_grids: (dictionary) keys are grid directions and values are correspoding indices
        :param grid_dir: (str) a grid direction that decides which vector component to be generated
        :param dest: (str) path to destination netCDF file
        '''
        logger.info("Generating {} component".format(grid_dir))
        grid_idx = two_grids[grid_dir]

        # vectors_field is consist of VIC Routing Directional Vector Values
        vectors_field = np.ma.copy(source.variables[variable][:])
        # for loop changes the VIC Vectors into Two-Grid Vectors
        for (x, y), dir in np.ndenumerate(vectors_field):
            if dir >= 0 and dir <= 9:
                vectors_field[x][y] = two_grid_vectors[int(dir)][grid_idx]

        dest.variables[dir_vec][:] = vectors_field

    # populate variables with decomposed vectors.
    # indices indicate VIC model vector values
    two_grid_vectors = [[0,0], #0 = filler
                        [1, 0], # 1 = N
                        [.7071, .7071], #2 = NE
                        [0, 1], #3 = E
                        [-.7071, .7071], #4 = SE
                        [-1, 0], #5 = S
                        [-.7071, -.7071], #6 = SW
                        [0, -1], #7 = W
                        [.7071, -.7071], #8 = NW
                        [0, 0]] #9 = outlet

    two_grids ={"eastward": 1, "northward": 0}

    generate_vector_component(eastvec, two_grid_vectors, two_grids, "eastward", dest)
    generate_vector_component(northvec, two_grid_vectors, two_grids, "northward", dest)

    #copy global attributes to the new file.        
    dest.setncatts(source.__dict__)

    #update history attribute, if present, to include this script
    if "history" in dest.ncattrs():
        dest.history ="{} {} {} {} {}\n".format(time.ctime(time.time()), "decompose_flow_vectors", source.filepath(), dest_file, variable) + dest.history

    source.close()
    dest.close()