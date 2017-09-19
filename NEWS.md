# News / Release Notes

## 0.2.1

*2017 Sep 18*

* Fix bug in ``update_metadata`` delete attribute.

## 0.2.0

*2017 Sep 18*

* Modify ``update_metadata`` to add ability to specify order of attribute processing. Why? 
  Most of our tools list attributes in storage order in the file, and that order is set by the order 
  in which the update operations are performed. Randomly (re)ordered attribute lists are hard to read.

## 0.1.0

*2017 Aug 17*

* Initial release of data prep scripts as a separate project.
* Previous "releases" were part of [CE backend](https://github.com/pacificclimate/climate-explorer-backend)
  but those releases were not specific to data prep and did not document it.
