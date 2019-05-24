"""Tests for the format-dsg script. Creates netCDF files, attempts to format them,
and deletes them."""

from netCDF4 import Dataset
from dp.format_dsg_timeseries import find_time_variable, find_singular_item, copy_global_metadata, creation_date_from_history, guess_id_variable, guess_instance_dimension,write_variable, add_dates, subtract_dates
import datetime
import os
from pytest import mark

# default values used to generate test netCDFs. Can be modified or overridden as needed
# to test various conditions and errors. Corresponds to a minimal version of an RVIC 
# streamflow output file.
test_dimensions = ("time", "nv", "outlets", "nc_chars")

test_variables = {
    "time": ( "f8", ("time"), {"units": "days since 0001-1-1 0:0:0"} ),
    "time_bnds": ("f8", ("time", "nv"), {}),
    "lon": ("f8", ("outlets"), {"units": "degrees_east"} ),
    "lat": ("f8", ("outlets"), {"units": "degrees_north"}),
    "outlet_name": ("S1", ("outlets", "nc_chars"), {"units": "unitless"} ),
    "streamflow": ("f8", ("time", "outlets"), {"units": "m3/s"} )
    }

test_attributes = {
    "history": "Created: Fri Jan 18 18:48:23 2019",
    "casename": "ASHNO",
    "casestr": "CanESM2.historical+rcp45.r2i1p1"
    }

def create_test_netcdf(filename, dimensions=None, variables=None, attributes=None):
    '''creates a test netCDF file at filename. If any dimensions, variables, or
    attributes are supplied, they override the defaults. Used to generate files to
    test various configurations. 
    
    Dimensions can be supplied as a list of names.
    
    Variables can be supplied as a dictionary of variable names associated with a
       tuple of the form (typestring, (dimensions), {metadata attributes: values}) 
       (Basically the arguments to createVariable in order)
        
    Attributes (global) can be supplied as a dictionary'''
    
    if not dimensions:
        dimensions = test_dimensions
    
    if not variables:
        variables = test_variables
        
    if not attributes:
        attributes = test_attributes
    
    testfile = Dataset(filename, "w", format="NETCDF4")
    for d in dimensions:
        testfile.createDimension(d, 1)
    for v in variables:
        testfile.createVariable(v, variables[v][0], variables[v][1])
        if len(variables[v]) == 3: #set variable attributes if provided
            testfile.variables[v].setncatts(variables[v][2])
    for a in attributes:
        testfile.setncattr(a, attributes[a])
    
    testfile.close()
    

    
def test_file_creation():
    timestamp = datetime.datetime.now().microsecond
    infile = "testinput{}.nc".format(timestamp)
    create_test_netcdf(infile)
    
    os.remove(infile)  

#test determining an instance dimension
@mark.parametrize('dimensions, instance_dimension', [
    (("time", "nv", "outlets", "nc_chars"), "outlets"), #known instance dimension
    (("time", "nv", "monkeys", "nc_chars"), "monkeys"), #unknown instance dimension
    (("time", "nv", "outlets", "monkeys", "nc_chars"), None), #known + unknown
    (("time", "nv", "monkeys", "bananas", "nc_chars"), None), #unknown + unknown
    (("time", "nv", "nc_chars"), None) #no instance dimension
    ])    
def test_guess_instance_dimension(dimensions, instance_dimension):
    timestamp = datetime.datetime.now().microsecond
    infile = "testinput{}.nc".format(timestamp)
    min_variables = {"time": ( "f8", ("time"), {"units": "days since 0001-1-1 0:0:0"} )}
    try:
        create_test_netcdf(infile, dimensions=dimensions, variables=min_variables)
        nc = Dataset(infile)
        id = guess_instance_dimension(nc)
        assert(id == instance_dimension)
        nc.close()
    except:
        assert not instance_dimension #expected error
    os.remove(infile)

#test determining the id_variable
@mark.parametrize('variables, id_variable', [
    ({"outlet_name": ("S1", ("outlets", "nc_chars"), {"units": "unitless"})}, "outlet_name"), #RVIC case
    ({"outlet_name": ("S1", ("outlets", "nc_chars"), {"cf_role": "profile_id"})}, None), #not a timeseries - invalid
    ({"outlet_number": ("f8", ("outlets"), {"units": "unitless"})}, "outlet_number"), # single variable
    ({"outlet_number": ("f8", ("outlets"), {"cf_role": "timeseries_id"}), # predefined
      "outlet_name": ("S1", ("outlets", "nc_chars"), {"units": "unitless"}) }, "outlet_number"),
    ({"outlet_number": ("f8", ("outlets"), {"cf_role": "timeseries_id"}), # 2 predefined - invalid
      "outlet_name": ("S1", ("outlets", "nc_chars"), {"cf_role": "timeseries_id"}) }, None),
    ({"hours": ("f8", ("time"), {"cf_role": "timeseries_id"})}, None), # predefined for wrong dimension - invalid
    ({"outlet_number": ("f8", ("outlets"), {"units": "unitless"}), # 2 available - invalid
      "outlet_name": ("S1", ("outlets", "nc_chars"), {"units": "unitless"}) }, None),
    ])    
def test_guess_id_variable(variables, id_variable):
    timestamp = datetime.datetime.now().microsecond
    infile = "testinput{}.nc".format(timestamp)
    try:
        create_test_netcdf(infile, dimensions=None, variables=variables)
        nc = Dataset(infile)
        id_var = guess_id_variable(nc, "outlets")
        assert(id_var == id_variable)
        nc.close()
    except:
        assert not id_variable
    os.remove(infile)

@mark.parametrize('history, date', [
    ("Created: Fri Jan 18 18:48:23 2019", datetime.datetime(2019, 1, 18, 18, 48, 23)),
    ("Banana: Fri Jan 18 18:48:23 2019", None),
    ("Created: Fri Jan 18 18:48:23 2019 Processed: Sat Jan 19 19:49:24 2020", 
     datetime.datetime(2019, 1, 18, 18, 48, 23) ),
    ("Processed: Sat Jan 19 19:49:24 2020 Created: Fri Jan 18 18:48:23 2019", 
     datetime.datetime(2019, 1, 18, 18, 48, 23) )
    ])
def test_creation_date_from_history(history, date):
    assert(creation_date_from_history(history) == date)

#TODO: add test of dry run metadata.
@mark.parametrize('metadata,prefix,postcount', [
    (None, None, 3), # metadata not added - conflicts with existing
    (None, "pref", 6) # no conflicts.
    ])    
def test_copy_global_metadata(metadata, prefix, postcount):
    timestamp = datetime.datetime.now().microsecond
    infile = "testinput{}.nc".format(timestamp)
    mfile = "mfile{}.nc".format(timestamp)
    
    create_test_netcdf(infile)
    nc1 = Dataset(infile, 'r+')
    create_test_netcdf(mfile, None, None, metadata)
    nc2 = Dataset(mfile)
    
    copy_global_metadata(nc2, prefix, nc1)
    assert(len(nc1.__dict__) == postcount)
        
    nc1.close()
    nc2.close()
    os.remove(infile)
    os.remove(mfile)
    
#TODO: doesn't test any error conditions
def test_write_variable():
    timestamp = datetime.datetime.now().microsecond
    infile = "testinput{}.nc".format(timestamp)
    outfile = "testoutput{}.nc".format(timestamp)
    create_test_netcdf(infile)
    nc = Dataset(infile, 'r')
    nc2 = Dataset(outfile, 'w')
    
    for d in nc.dimensions:
        if d != "nc_chars":
            size = None if nc.dimensions[d].isunlimited() else len(nc.dimensions[d])
            nc2.createDimension(d, size)
    for v in nc.variables:
        write_variable(nc, nc2, v, v == 'outlet_name', 'outlets')
    
    #all variables written?    
    assert(len(nc2.variables) == len(nc.variables))
    
    #text dimension reduced?
    assert(len(nc2.variables['outlet_name'].dimensions) == 1)
    
    #coordinates written?
    assert(nc2.variables['streamflow'].getncattr('coordinates') == 'lon lat outlet_name')
    
    #cf_variable marked?
    assert(nc2.variables['outlet_name'].getncattr('cf_role') == 'timeseries_id')
    nc.close()
    nc2.close()
    os.remove(infile)
    os.remove(outfile)
    
@mark.parametrize('edate,calendar,delta,sdate', [
    (datetime.date(2019, 12, 26), "standard", 365, datetime.date(2018, 12, 26)),
    (datetime.date(2019, 12, 26), "360_day", 365, datetime.date(2018, 12, 21)),
    (datetime.date(2016, 12, 26), "standard", 365, datetime.date(2015, 12, 27)),
    (datetime.date(2016, 12, 26), "noleap", 365, datetime.date(2015, 12, 26)),
#    (datetime.date(1945, 1, 1), "standard", 710033, datetime.date(1, 1, 1)),
#    (datetime.date(1946, 1, 1), "standard", 710033, datetime.date(2, 1, 1))
    ])
def test_date_arithmetic(edate, calendar, delta, sdate):
    assert(subtract_dates(edate, delta, calendar) == sdate)
    assert(add_dates(sdate, delta, calendar) == edate)

@mark.parametrize('variables,result', [
    (None, "time"),
    ({"lat": ("f8", ("outlets"), {"units": "degrees_north"})}, []),
    ({"time1": ( "f8", ("time"), {"units": "days since 0001-1-1 0:0:0"} ),
      "time2": ( "f8", ("time"), {"units": "days since 0001-1-1 0:0:0"} )}, ["time1", "time2"])
    ])
def test_find_time_variable(variables, result):
    timestamp = datetime.datetime.now().microsecond
    infile = "testinput{}.nc".format(timestamp)
    create_test_netcdf(infile, None, variables=variables)
    nc = Dataset(infile, 'r')
    assert(find_time_variable(nc) == result)
    nc.close()
    os.remove(infile)
    
@mark.parametrize('list, ex, result', [
    ([1, 2, 3, 4], True, None),
    ([1, 2, 3, 4], False, [1, 2, 3, 4]),
    ([1, 6, 7, 8], True, 1),
    ([1, 6, 7, 8], False, 1),
    ([6, 7, 8], False, []),
    ([6, 7, 8], True, None)
    ])
def test_find_singular_item(list, ex, result):
    try:
        assert(result == find_singular_item(list, lambda n: n < 5, "test", ex))
    except:
        assert result is None
    


#TODO: test determine_reference_date, test 