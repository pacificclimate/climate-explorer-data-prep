"""Tests for the decompose_flow_vectors script. Create a small netCDF
   file, run the script, and check its output."""
   
from netCDF4 import Dataset
import datetime
import subprocess
import os
import numpy as np
import numpy.ma as ma


def create_routing_file(name, numlats, numlons, routes):
    """Creates a simple netCDF file with latlon and flows.
    Requires numlats and numlons to be divisors of 15."""
    testfile = Dataset(name, "w", format="NETCDF4")
    
    lat = testfile.createDimension("lat", numlats)
    lon = testfile.createDimension("lon", numlons)
    
    lats = testfile.createVariable("lat", "f8", ("lat"))
    lons = testfile.createVariable("lon", "f8", ("lon"))
    flows = testfile.createVariable("flow", "f8", ("lat", "lon"))
    
    lats[:] = range(45, 60, int(15 / numlats))
    lons[:] = range(-125, -110, int(15 / numlons))
    flows[:] = routes
    
    testfile.close()

def test_decomposition():
    timestamp = datetime.datetime.now().microsecond
    infile = "testinput{}.nc".format(timestamp)
    outfile = "testoutput{}.nc".format(timestamp)
    create_routing_file(infile, 3, 3, [1, 2, 3, 4, 5, 6, 7, 8, 9])
    
    subprocess.call(["python", "./scripts/decompose_flow_vectors", infile, outfile, "flow"])
    
    output = Dataset(outfile, "r", format = "NETCDF4")
    north = output.variables["northward_flow"][:]
    east = output.variables["eastward_flow"][:]
    
    assert(np.array_equal(north, np.array([[1., 0.7071, 0.], [-.7071, -1., -.7071], [0., .7071, 0.]])))
    assert(np.array_equal(east, np.array([[0, 0.7071, 1], [.7071, 0, -.7071], [-1, -.7071, 0]])))
    
    output.close()
    os.remove(infile)
    os.remove(outfile)

def test_missing_data():
    timestamp = datetime.datetime.now().microsecond
    infile = "testinput{}.nc".format(timestamp)
    outfile = "testoutput{}.nc".format(timestamp)
    
    arr = np.array([1., 2, 3, 4, 5, 6, 7, 8, 9])
    marr = ma.masked_array(arr, mask=[0, 0, 0, 1, 0, 0, 0, 0, 0] )
    create_routing_file(infile, 3, 3, marr)
    
    subprocess.call(["python", "./scripts/decompose_flow_vectors", infile, outfile, "flow"])
    
    output = Dataset(outfile, "r", format="NetCDF4")
    north = output.variables["northward_flow"][:]
    assert(np.ma.is_masked(north[1][0]))
    
    east = output.variables["eastward_flow"][:]
    assert(np.ma.is_masked(east[1][0]))
    
    output.close()
    os.remove(infile)
    os.remove(outfile)

    