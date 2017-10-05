"""Module supporting update_metadata script"""

import logging
import re
import sys

import numpy as np
import six


rename_prefix = '<-'  # Or some other unlikely sequence of characters
expression_prefix = '='


formatter = logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s', "%Y-%m-%d %H:%M:%S")
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)  # overridden by -l when run as a script


# Custom functions for use in the ``=expression`` syntax.

# Decorator to catalogue custom functions
custom_functions = {}
def custom_function(fun):
    custom_functions[fun.__name__] = fun
    return fun


@custom_function
def normalize_experiment_id(experiment_id):
    experiment_id = re.sub(r'historical', r'historical', experiment_id,
                           flags=re.IGNORECASE)
    experiment_id = re.sub(r'rcp(\d)\.?(\d)', r'rcp\1\2', experiment_id,
                           flags=re.IGNORECASE)
    return experiment_id


@custom_function
def parse_ensemble_code(ensemble_code):
    match = re.match(r'r(\d+)i(\d+)p(\d+)', ensemble_code)
    if match:
        return {
            'realization': np.int32(match.group(1)),
            'initialization_method': np.int32(match.group(2)),
            'physics_version': np.int32(match.group(3)),
        }
    raise ValueError("Could not parse '{}' as an ensemble code"
                     .format(ensemble_code))


def delete_attribute(target, name):
    if hasattr(target, name):
        delattr(target, name)
        logger.info("\t'{}': Deleted".format(name))


def rename_attribute(target, name, value):
    old_name = value[len(rename_prefix):]
    if hasattr(target, old_name):
        setattr(target, name, getattr(target, old_name))
        delattr(target, old_name)
        logger.info("\t'{}': Renamed from '{}'".format(name, old_name))


def set_attribute_from_expression(target, name, value):
    expression = value[len(expression_prefix):]
    try:
        ncattrs = {name: getattr(target, name) for name in target.ncattrs()}
        result = eval(expression, custom_functions, ncattrs)
        setattr(target, name, result)
        logger.info("\t'{}': Set to value of expression '{}' = {}"
                    .format(name, expression, result))
    except Exception:
        logger.error(
            "\t'{}': Exception during evaluation of expression '{}':\n\t{}"
            .format(target, name, sys.exc_info()[0])
        )


def set_attribute(target, name, value):
    setattr(target, name, value)
    logger.info("\t'{}': Set to '{}'".format(name, value))


def modify_attribute(target, name, value):
    if value is None:
        return delete_attribute(target, name)

    if (isinstance(value, six.string_types)
          and value.startswith(rename_prefix)):
        return rename_attribute(target, name, value)

    if (isinstance(value, six.string_types)
          and value.startswith(expression_prefix)):
        return set_attribute_from_expression(target, name, value)

    return set_attribute(target, name, value)


def process(target, item):
    if isinstance(item, tuple) and len(item) == 2:
        modify_attribute(target, *item)
    elif isinstance(item, list):
        for element in item:
            process(target, element)
    elif isinstance(item, dict):
        for element in item.items():
            process(target, element)
    else:
        logger.error('Cannot process {}', item)
