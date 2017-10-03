# News / Release Notes

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
