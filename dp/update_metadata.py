"""Module supporting update_metadata script"""

import logging
import re
import sys
import csv
from pkg_resources import resource_filename
from functools import partial

import six
import yaml
import numpy as np
from nchelpers import CFDataset


rename_prefix = "<-"  # Or some other unlikely sequence of characters
expression_prefix = "="


formatter = logging.Formatter(
    "%(asctime)s %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"
)
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)  # overridden by -l when run as a script


# Load data files for later use


def load_variable_info():
    filepath = resource_filename(__name__, "data/variable information.csv")
    with open(filepath) as file:
        reader = csv.DictReader(file)
        return {row["standard_name"]: row for row in reader}


variable_info = load_variable_info()

# Custom functions for use in the ``=expression`` syntax.

# Decorator to catalogue custom functions
custom_functions = {}


def custom_function(fun):
    custom_functions[fun.__name__] = fun
    return fun


@custom_function
def normalize_experiment_id(experiment_id):
    experiment_id = re.sub(
        r"historical", r"historical", experiment_id, flags=re.IGNORECASE
    )
    experiment_id = re.sub(
        r"rcp(\d)\.?(\d)", r"rcp\1\2", experiment_id, flags=re.IGNORECASE
    )
    experiment_id = ", ".join(re.split(r"\s*,\s*", experiment_id))
    return experiment_id


@custom_function
def parse_ensemble_code(ensemble_code):
    match = re.match(r"r(\d+)i(\d+)p(\d+)", ensemble_code)
    if match:
        return {
            "realization": np.int32(match.group(1)),
            "initialization_method": np.int32(match.group(2)),
            "physics_version": np.int32(match.group(3)),
        }
    raise ValueError("Could not parse '{}' as an ensemble code".format(ensemble_code))


def info_for_var(var_name, item):
    try:
        return variable_info[var_name][item]
    except KeyError:
        raise ValueError("'{}' is not a known variable name")


@custom_function
def long_name_for_var(var_name):
    return info_for_var(var_name, "long_name")


@custom_function
def cell_methods_for_var(var_name):
    return info_for_var(var_name, "cell_methods")


# Helper functions


def is_string_and_starts_with(prefix, thing):
    return isinstance(thing, six.string_types) and thing.startswith(prefix)


is_rename = partial(is_string_and_starts_with, rename_prefix)
is_expression = partial(is_string_and_starts_with, expression_prefix)


def strip_prefix(prefix, string):
    return string[len(prefix) :].strip()


strip_rename_prefix = partial(strip_prefix, rename_prefix)
strip_expression_prefix = partial(strip_prefix, expression_prefix)


def evaluate_expression(dataset, expression):
    """
    Evaluate an expression in a context determined by the content of
    the dataset.

    The context contains selected items copied from ``dataset``. It contains
    all global attributes and selected CFDataset properties/methods.
    """
    context = {}
    context.update({key: getattr(dataset, key) for key in dataset.ncattrs()})
    context.update(
        {
            key: getattr(dataset, key)
            for key in """
            filepath
            dimensions
            variables
            dependent_varnames
        """.split()
        }
    )
    context.update({"dependent_varname": sorted(dataset.dependent_varnames())[0]})

    return eval(expression, custom_functions, context)


def evaluate_string(dataset, string):
    if is_expression(string):
        expression = strip_expression_prefix(string)
        return evaluate_expression(dataset, expression)
    else:
        return string


# Functions for modifying attributes


def delete_attribute(target, name):
    if hasattr(target, name):
        delattr(target, name)
        logger.info("\t'{}': Deleted".format(name))


def rename_attribute(dataset, target, name, old_name):
    old_name = evaluate_string(dataset, old_name)
    if hasattr(target, old_name):
        setattr(target, name, getattr(target, old_name))
        delattr(target, old_name)
        logger.info("\t'{}': Renamed from '{}'".format(name, old_name))


def set_attribute_from_expression(dataset, target, name, expression):
    try:
        result = evaluate_expression(dataset, expression)
        setattr(target, name, result)
        logger.info(
            "\t'{}': Set to value of expression {}".format(name, repr(expression))
        )
        logger.debug("\t\t= {}".format(repr(result)))
    except Exception as e:
        logger.error(
            "\t'{}': Exception during evaluation of expression '{}'".format(
                name, expression
            )
        )
        logger.error(e, exc_info=True)


def set_attribute(target, name, value):
    setattr(target, name, value)
    logger.info("\t'{}': Set".format(name))
    logger.debug("\t\t= {}".format(repr(value)))


def modify_attribute(dataset, target, name, value):
    if value is None:
        return delete_attribute(target, name)

    if is_rename(value):
        old_name = strip_rename_prefix(value)
        return rename_attribute(dataset, target, name, old_name)

    if is_expression(value):
        expression = strip_expression_prefix(value)
        return set_attribute_from_expression(dataset, target, name, expression)

    return set_attribute(target, name, value)


def apply_attribute_updates(dataset, target, attr_updates):
    if isinstance(attr_updates, tuple) and len(attr_updates) == 2:
        modify_attribute(dataset, target, *attr_updates)
    elif isinstance(attr_updates, list):
        for element in attr_updates:
            apply_attribute_updates(dataset, target, element)
    elif isinstance(attr_updates, dict):
        for element in attr_updates.items():
            apply_attribute_updates(dataset, target, element)
    else:
        logger.error("Cannot process {}", attr_updates)


# Modify variables


def rename_variable(dataset, target_name, old_name):
    old_name = evaluate_string(dataset, old_name)
    if old_name in dataset.variables and target_name not in dataset.variables:
        dataset.renameVariable(old_name, target_name)
        logger.info("\tVariable '{}': renamed from '{}'".format(target_name, old_name))


def process_updates(dataset, updates):
    for target_key, update in updates.items():
        # Evaluate key
        target_name = evaluate_string(dataset, target_key)

        # Apply update
        if target_name == "global":
            target = dataset
            logger.info("Global attributes:")
            apply_attribute_updates(dataset, target, update)
        else:
            if is_rename(update):
                old_name = strip_rename_prefix(update)
                rename_variable(dataset, target_name, old_name)
            else:
                target = dataset.variables[target_name]
                logger.info("Attributes of variable '{}':".format(target_name))
                if target_name != target_key:
                    logger.debug("\t\tfrom expression {}".format(repr(target_key)))
                apply_attribute_updates(dataset, target, update)


def main(args):
    with open(args.updates) as ud:
        updates = yaml.safe_load(ud)

    logger.info("Processing file: {}".format(args.ncfile))
    with CFDataset(args.ncfile, mode="r+") as dataset:
        process_updates(dataset, updates)
