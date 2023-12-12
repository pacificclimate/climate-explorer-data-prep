"""Tests for the decompose_flow_vectors script. Create a small netCDF
   file, run the script, and check its output."""

from netCDF4 import Dataset
import pytest
import datetime
import subprocess
import os
import numpy as np
import numpy.ma as ma
import pkg_resources


def create_routing_file(name, numlats, numlons, routes):
    """Creates a simple netCDF file with latlon and flows.
    Requires numlats and numlons to be divisors of 15."""
    testfile = Dataset(name, "w", format="NETCDF4")

    lat = testfile.createDimension("lat", numlats)
    lon = testfile.createDimension("lon", numlons)

    lats = testfile.createVariable("lat", "f8", ("lat"))
    lons = testfile.createVariable("lon", "f8", ("lon"))
    flows = testfile.createVariable("flow", "f8", ("lat", "lon"))
    wrong_flows = testfile.createVariable("wrong_flow", "f8", ("lat", "lon"))

    lats[:] = range(45, 60, int(15 / numlats))
    lons[:] = range(-125, -110, int(15 / numlons))
    flows[:] = np.reshape(routes, (numlats, numlons))
    wrong_flows[:] = np.reshape(
        [100, -25, 358, 14, 5, 68, -7, -128, 15], (numlats, numlons)
    )

    testfile.close()


def test_decomposition():
    timestamp = datetime.datetime.now().microsecond
    infile = "testinput{}.nc".format(timestamp)
    outfile = "testoutput{}.nc".format(timestamp)
    create_routing_file(infile, 3, 3, [1, 2, 3, 4, 5, 6, 7, 8, 9])

    subprocess.call(["decompose_flow_vectors", infile, outfile, "flow"])

    output = Dataset(outfile, "r", format="NETCDF4")
    north = output.variables["northward_flow"][:]
    east = output.variables["eastward_flow"][:]

    assert np.array_equal(
        north,
        np.array([[1.0, 0.7071, 0.0], [-0.7071, -1.0, -0.7071], [0.0, 0.7071, 0.0]]),
    )
    assert np.array_equal(
        east, np.array([[0, 0.7071, 1], [0.7071, 0, -0.7071], [-1, -0.7071, 0]])
    )

    output.close()
    os.remove(infile)
    os.remove(outfile)


def test_missing_data():
    timestamp = datetime.datetime.now().microsecond
    infile = "testinput{}.nc".format(timestamp)
    outfile = "testoutput{}.nc".format(timestamp)

    arr = np.array([1.0, 2, 3, 4, 5, 6, 7, 8, 9])
    marr = ma.masked_array(arr, mask=[0, 0, 0, 1, 0, 0, 0, 0, 0])
    create_routing_file(infile, 3, 3, marr)

    subprocess.call(["decompose_flow_vectors", infile, outfile, "flow"])

    output = Dataset(outfile, "r", format="NetCDF4")
    north = output.variables["northward_flow"][:]
    assert np.ma.is_masked(north[1][0])

    east = output.variables["eastward_flow"][:]
    assert np.ma.is_masked(east[1][0])

    output.close()
    os.remove(infile)
    os.remove(outfile)


def assert_SystemExit_code(infile, outfile, variable, expected):
    with pytest.raises(subprocess.CalledProcessError) as e:
        subprocess.check_call(
            [
                "decompose_flow_vectors",
                infile,
                outfile,
                variable,
            ]
        )
    assert e.value.returncode == expected


def test_source_check():
    timestamp = datetime.datetime.now().microsecond
    infile = "testinput{}.nc".format(timestamp)
    outfile = "testoutput{}.nc".format(timestamp)
    create_routing_file(infile, 3, 3, [1, 2, 3, 4, 5, 6, 7, 8, 15])

    assert_SystemExit_code(infile, outfile, "flow", 1)

    os.remove(infile)


def test_variable_check():
    timestamp = datetime.datetime.now().microsecond
    infile = "testinput{}.nc".format(timestamp)
    outfile = "testoutput{}.nc".format(timestamp)
    create_routing_file(infile, 3, 3, [1, 2, 3, 4, 5, 6, 7, 8, 9])

    assert_SystemExit_code(infile, outfile, "lat", 2)
    assert_SystemExit_code(infile, outfile, "invalid_variable_name", 2)
    assert_SystemExit_code(infile, outfile, "wrong_flow", 2)

    os.remove(infile)
