#!python
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


def decompose_flow_vectors(source, dest, variable):

    dest.createDimension("lat", source.dimensions["lat"].size)
    dest.createVariable("lat", "f8", ("lat"))
    dest.variables["lat"].setncatts(source.variables["lat"].__dict__)
    dest.variables["lat"][:] = source.variables["lat"][:]

    dest.createDimension("lon", source.dimensions["lon"].size)
    dest.createVariable("lon", "f8", ("lon"))
    dest.variables["lon"].setncatts(source.variables["lon"].__dict__)
    dest.variables["lon"][:] = source.variables["lon"][:]

    #create the vector variables
    eastvec = "eastward_{}".format(variable)
    dest.createVariable(eastvec, "f8", ("lat", "lon"))
    dest.variables[eastvec].units = "1"
    dest.variables[eastvec].standard_name = eastvec #ncWMS relies on standard names
    dest.variables[eastvec].long_name = "Normalized eastward vector component of {}".format(variable)

    northvec = "northward_{}".format(variable)
    dest.createVariable(northvec, "f8", ("lat", "lon"))
    dest.variables[northvec].units = "1"
    dest.variables[northvec].standard_name = northvec #ncWMS relies on standard names
    dest.variables[northvec].long_name = "Normalized northward vector component of {}".format(variable)

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

    logger.info("Generating eastward component")
    east = np.ma.copy(source.variables[variable][:])
    for (x, y), dir in np.ndenumerate(east):
        if dir >= 0 and dir <= 9:
            east[x][y] = directions[int(dir)][1]
    dest.variables[eastvec][:] = east

    logger.info("Generating northward component")
    north = np.ma.copy(source.variables[variable][:])
    for (x, y), dir in np.ndenumerate(north):
        if dir >= 0 and dir <= 9:
            north[x][y] = directions[int(dir)][0]
    dest.variables[northvec][:] = north

    #copy global attributes to the new file.        
    dest.setncatts(source.__dict__)

    #update history attribute, if present, to include this script
    if "history" in dest.ncattrs():
        dest.history ="{} {} {} {} {}\n".format(time.ctime(time.time()), "decompose_flow_vectors", source.filepath(), dest.filepath(), variable) + dest.history

    source.close()
    dest.close()