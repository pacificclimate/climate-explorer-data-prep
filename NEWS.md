# News / Release Notes

## 0.8.7
*2022 Jan 17*

* Replace `pip` with `pipenv` for Python package installation
* Add `black` and `linter` for formatting and styling
* Update `nchelpers` to version 5.5.8 to process CMIP6 data

## 0.8.6
*2021 Jan 11*

* Pin `cdo==1.5.3` library

## 0.8.5
*2020 Jul 21*

* Modify `generate_prsn` not to produce redundant dry_run output file

## 0.8.4
*2020 Jul 15*

* Bugfix in generate_climos script
* Add custom function `dry_run_handler` to handle `generate_climos`'s dry_run
* Add custom function `generate_climos` to handle `generate_climos`'s general run
* Add full CI test with actions

## 0.8.3
*2020 Jun 23*

 * Add ability to check input validities for `decompose_flow_vectors`

## 0.8.2
*2020 Jun 17*

 * Add `decompose_flow_vectors` in dp package
 * Add custom function `update_generate_climos_history` to add ability to update `generate_climos` history attribute

## 0.8.1
*2020 Jun 05*

 * Updates nchelpers version from 5.5.1 to 5.5.6
 * Adds ability to generate prsn for dry run to output to text file instead of logger
 
## 0.8.0
*2020 Feb 27*

* Adds ability to generate climos for extreme indexes calculated as minimumg or maximums over time to generate_climos
* Adds support for streamflow climatologies to generate_climos
* Adds Jenkinsfiles for automatic testing and deployment to pypi

## 0.7.0

*2019 Jun 14*

* Adds two new options to generate_climo script
  * --climo to select a subset of climatological periods
  * --resolutions to select a subset of temporal resolutions

## 0.6.0

*2019 Jun 07*

* Add ncWMS vector formatting script
* Add metadata conversion for downscaled files
* Add variable renaming to update_metadata script
* Bugfix (typo) in process-climo-means.sh script
* Add the abililty to generate monthly climos from monthly data
* Fix the use of nchelpers.CFDataset.dependent_varnames
* Fix unused tests
* Add the ability to compute standard_deviation climatologies
* Add the ability to compute snowfall from temp/precip

## 0.5.2

*2017 Oct 11*

* Fix absent data in source distribution.

## 0.5.1

*2017 Oct 11*

* Fix minor error in ``update_metadata`` script.

## 0.5.0

*2017 Oct 11*

* ``update_metadata``: Enhancements largely in support of 
[correcting attributes of CLIMDEX variables](https://github.com/pacificclimate/climate-explorer-data-prep/issues/31):

  * Add access to variables
  * Add access to dependent variable names
  * Add expression evaluation for keys
  * Add custom functions returning ``cell_methods`` and ``long_name`` for variable ``standard_name``
  for CLIMDEX variables

## 0.4.1

*2017 Oct 06*

* Improve logging in `update_metadata`.
* Add separator normalization to `update_metadata` custom function `normalize_experiment_id`.

## 0.4.0

*2017 Oct 03*

* Add custom function `normalize_experiment_id` for expressions to `update_metadata`.
* Return `numpy.int32` values from custom function `parse_ensemble_code`.

## 0.2.2 (should have been 0.3.0)

*2017 Oct 02*

* Add expression evalution feature to `update_metadata`. See README for details.

## 0.2.1

*2017 Sep 18*

* Fix bug in `update_metadata` delete-attribute feature.

## 0.2.0

*2017 Sep 18*

* Modify `update_metadata` to add ability to specify order of attribute processing. Why? 
  Most of our tools list attributes in storage order in the file, and that order is set by the order 
  in which the update operations are performed. Randomly (re)ordered attribute lists are hard to read.

## 0.1.0

*2017 Aug 17*

* Initial release of data prep scripts as a separate project.
* Previous "releases" were part of [CE backend](https://github.com/pacificclimate/climate-explorer-backend)
  but those releases were not specific to data prep and did not document it.
