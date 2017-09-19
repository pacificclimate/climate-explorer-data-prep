# PCIC Climate Explorer Data Preparation Tools

[![Build Status](https://travis-ci.org/pacificclimate/climate-explorer-data-prep.svg?branch=master)](https://travis-ci.org/pacificclimate/climate-explorer-data-prep)
[![Code Climate](https://codeclimate.com/github/pacificclimate/climate-explorer-data-prep/badges/gpa.svg)](https://codeclimate.com/github/pacificclimate/climate-explorer-data-prep)

## Historical note

Prior to 2017 Aug 17, these scripts were part of the 
[Climate Explorer backend](https://github.com/pacificclimate/climate-explorer-backend).

These scripts are now a separate project with their own repository (this one).
A full commit history of the data prep scripts was retained during the migration to this repo. 
Most (but, mysteriously, not quite all) of the commit history for non-data prep code was pruned during migration.

No releases in the original CE backend specifically related to or documented changes to these scripts, 
so this project starts with release version 0.1.0.

## Installation

Clone the repo onto the target machine.

If installing on a PCIC compute node, you must load the environment modules that data prep depends on
_before_ installing the Python modules:

```bash
$ module load netcdf-bin
$ module load cdo-bin
```

Python installation should be done in a virtual environment. We recommend a Python3 virtual env, created and activated
as follows:

```bash
$ python3 -m venv venv
$ source venv/bin/activate
(venv) $ pip install -U pip setuptools wheel  # why are setuptools and wheel necessary?
(venv) $ pip install -i https://pypi.pacificclimate.org/simple/ -r requirements.txt
(venv) $ pip install .  # or pip install -e .
```

This installs the scripts described below.
To make their command-line invocation a little nicer, the script files lack the `.py` extension.
They are, however, Python scripts.

## Development

### Testing

Very regrettably, it is prohibitively difficult to install `cdo` 
([Climate Data Operators](https://code.mpimet.mpg.de/projects/cdo/wiki/Cdo%7Brbpy%7D))
in the Travis CI environment. 
(NetCDF support isn't built into the debian cdo pacakges. Installing NetCDF proved very hard. Argh.)
That said, `.travis.yml` is configured with commented out portions in anticipation of the day we can really run these
tests in Travis.

We can and MUST, however, run the tests on our development machines. It's as simple as

```bash
pytest
```

(Oh, the unintended punning!)

### Releasing

To create a versioned release:

1. Increment `__version__` in `setup`
2. Summarize the changes from the last release in `NEWS.md`
3. Commit these changes, then tag the release:

  ```bash
git add setup NEWS.md
git commit -m"Bump to version x.x.x"
git tag -a -m"x.x.x" x.x.x
git push --follow-tags
  ```
  
## Scripts

### `generate_climos`: Generate climatological means

#### Purpose

To generate files containing climatological means from input files of daily, monthly, or yearly data that adhere to the 
[PCIC metadata standard ](https://pcic.uvic.ca/confluence/display/CSG/PCIC+metadata+standard+for+downscaled+data+and+hydrology+modelling+data) 
(and consequently to CMIP5 and CF standards).

Means are formed over the time dimension; the spatial dimensions are preserved.

Output can optionally be directed into separate files for each variable and/or each averaging interval 
(month, season, year).

This script:

1. Opens an existing NetCDF file

2. Determines what climatological periods to generate

3. For each climatological period:

    a. Aggregates the daily data for the period into a new climatological output file.
    
    b. Revises the time variable of the output file to meet CF1.6/CMIP5 specification.
    
    c. Adds a climatology_bounds variable to the output file match climatological period.
    
    d. Optionally splits the climatology file into one file per dependent variable in the input file.
    
    e. Uses PCIC standards-compliant filename(s) for the output file(s).

All input file metadata is obtained from standard metadata attributes in the netCDF file. 
No metadata is deduced from the filename or path.

All output files contain PCIC standard metadata attributes appropriate to climatology files.

#### Usage

```bash
# Dry run
generate_climos --dry-run -o outdir files...

# Use defaults:
generate_climos -o outdir files...

# Split output into separate files per dependent variable and per averaging interval 
generate_climos --split-vars --split-intervals -o outdir files...
```

Usage is further detailed in the script help information: `generate_climos -h`

#### PCIC Job Queueing tool for processing many / large files

For several reasons -- file copying, computation time, record-keeping, etc. -- it's inadvisable to run 
`generate_climos` from the command line for many and/or large input files. 
Fortunately there is a tool to support this kind of processing and record-keeping: 
[PCIC Job Queueing](https://github.com/pacificclimate/jobqueueing).

### `split_merged_climos`: Split climo means files into per-interval files (month, season, year)

#### Purpose

Early versions of the `generate_climos` script (and its R predecessor) created output files containing
means for all intervals (month, season, year) concatenated into a single file. This is undesirable
for a couple of reasons: 

* Pragmatic: `ncWMS2` rejects NetCDF files with non-monotonic dimensions. 
  Merged files have a non-monotonic time dimension.
  
* Formal: The 3 different means, i.e., means over 3 different intervals (month, season, year), 
  are formally different estimates of random variables with different time dimensions. 
  We could represent this easily enough in a single NetCDF file, with 3 distinct variables 
  each with a distinct time dimension, but judged it as introducing too much complication. 
  We prefer to have a separate file per averaging interval, with one time dimension per file.
  
This script takes as input one or more climo means files and splits each into separate files,
one file per mean interval (month, season, year) in the input file.

The input file is not modified.
  
#### Usage

```bash
split_merged_climos -o outdir files...
```

Filenames are automatically generated for the split files.
These filenames conform to the extended CMOR syntax defined in the
[PCIC metadata standard ](https://pcic.uvic.ca/confluence/display/CSG/PCIC+metadata+standard+for+downscaled+data+and+hydrology+modelling+data).

If the input file is named according to standard, then the new filenames are the same as the input filename, 
with the `<frequency>` component (typically `msaClim`) 
replaced with the values `mClim` (monthly means), `sClim` (seasonal means), `aClim` (annual means).

Output files are placed in the directory specified in the `-o` argument. 
This directory is created if it does not exist.

### `update_metadata`: Update metadata in a NetCDF file

Some NetCDF files have improper metadata: missing, invalid, or incorrectly named global or variable metadata
attributes. There are no really convenient tools for updating metadata, so we rolled our own, `update_metadata`.

#### Usage

```bash
# update metadata in ncfile according to instructions in updates
update_metadata -u updates ncfile
```

`update_metadata` takes an option (`-u`) and an argument: 

* `-u`: the filepath of an updates file that specifies what to do to the metdata it finds in the NetCDF file
* argument: the filepath of a NetCDF file to update

#### Updates file: specifying updates to make

`update_metadata` can update the global attributes and/or the attributes of variables in a NetCDF file. 
Three update operations are available (detailed below): delete attribute, set attribute value, rename attribute.

Updates to be made are specified in a separate updates file.
It uses a simple, human-readable data format called [YAML](https://en.wikipedia.org/wiki/YAML).
You only need to know a couple of things about YAML and how we employ it to use this script:

* Updates are specified with `key: value` syntax. A space must separate the colon from the value.
* Indentation matters (see next item). Indentation must be consistent within a block.
* There are two levels of indentation. 
  * The first (unindented) level specifies what group of attributes is to be updated. 
    * The key `global` specifies global attributes. 
    * Any other key is assumed to be the name of a variable whose attributes are to be updated.
    * The *value* for a first-level key is the indented block below it.
  * The second (indented) level specifies the attribute and the change to be made to it.
    See below for details.
    * If you care about the order that attributes are processed in (and will appear in any naive
      listing of the attributes), prefix all of the second-level items with a dash (-). This causes
      the attributes to be processed in order the order listed in the updates file.

##### Delete attribute

Delete the attribute named `name`.

```yaml
global-or-variable-name:
    name:
```

or (to process in order)

```yaml
global-or-variable-name:
    - name:
```


##### Set attribute value

Set the value of the attribute `name` to `value`. If the attribute does not yet exist, it is created.

```yaml
global-or-variable-name:
    name: value
```

or (to process in order)

```yaml
global-or-variable-name:
    - name: value
```

Note: This script is clever (courtesy of YAML cleverness) about the data type of the value specified. 

* If you provide a value that looks like an integer, it is interpreted as an integer.
* If you provide a value that looks like a float, it is interpreted as a float.
* Otherwise it is treated as a string.
  If you need to force a numeric-looking value to be a string, enclose it in single or double quotes (e.g., `'123'`).

More details on the [Wikipedia YAML page](https://en.wikipedia.org/wiki/YAML#Advanced_components).

##### Rename attribute

Rename the attribute named `oldname` to `newname`. Value is unchanged.

```yaml
global-or-variable-name:
    newname: <-oldname
```

or (to process in order)

```yaml
global-or-variable-name:
    - newname: <-oldname
```

Note: The special sequence `<-` after the colon indicates renaming. 
This means that you can't set an attribute with a value that begins with `<-`. Sorry.

##### Example updates file:

```yaml
global:
    foo: 
    bar: 42
    baz: <-qux

temperature:
    units: degrees_C
```

or (to process in order)

```yaml
global:
    - foo: 
    - bar: 42
    - baz: <-qux

temperature:
    - units: degrees_C
```

This file causes a NetCDF file to be updated in the following way:

Global attributes: 
* delete global attribute `foo`
* set global attribute `bar` to (integer) `42`
* rename global attribute `qux` to `baz`

Attributes of variable named `temperature`:
* set attribute `units` to (string) `degrees_C`

## Indexing climatological output files

Indexing is done using scripts in the [modelmeta](https://github.com/pacificclimate/modelmeta) package.

