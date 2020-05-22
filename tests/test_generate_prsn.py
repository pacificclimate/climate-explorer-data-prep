import pytest
import os

import numpy as np
from tempfile import NamedTemporaryFile
from pkg_resources import resource_filename

from nchelpers import CFDataset
from conftest import get_dataset
from dp.generate_prsn import unique_shape, is_unique_value, \
    pr_freezing_from_units, create_prsn_netcdf_from_source, \
    create_filepath_from_source, has_required_vars, matching_datasets, \
    check_pr_units, process_to_prsn, convert_temperature_units
from pint import UnitRegistry

ureg = UnitRegistry()
Q_ = ureg.Quantity

@pytest.mark.parametrize('arrays', [
    ({'shape1': np.arange(10).reshape(2, 5), 'shape2': np.arange(10).reshape(2, 5)}),
    ({'shape1': np.arange(100).reshape(2, 5, 10), 'shape2': np.arange(100).reshape(2, 5, 10)})
])
def test_unique_shape(arrays):
    assert unique_shape(arrays)


@pytest.mark.parametrize('arrays', [
    ({'shape1': np.arange(10).reshape(2, 5), 'shape2': np.arange(10).reshape(10, 1)}),
    ({'shape1': np.arange(100).reshape(2, 5, 10), 'shape2': np.arange(100).reshape(10, 10)})
])
def test_unique_shape_different_shape(arrays):
    assert not unique_shape(arrays)


@pytest.mark.parametrize('values', [
    ([1, 1, 1]),
    ([True, True, True]),
    (['a', 'a', 'a'])
])
def test_is_unique_value(values):
    assert is_unique_value(values)


@pytest.mark.parametrize('values', [
    ([1, 1, 'not_matching']),
    ([True, True, 'not_matching']),
    (['a', 'a', 'not_matching'])
])
def test_is_unique_value_not_unique(values):
    assert not is_unique_value(values)


@pytest.mark.parametrize('unit, expected', [
    ('degC', 0.0),
    ('K', 273.15)
])
def test_pr_freezing_from_units(unit, expected):
    assert pr_freezing_from_units(unit) == expected


@pytest.mark.parametrize('tiny_dataset', [
    ('downscaled_pr')
], indirect=['tiny_dataset'])
@pytest.mark.parametrize('fake_dataset', [
    {}  # empty fake dataset
], indirect=['fake_dataset'])
def test_create_prsn_netcdf_from_source(tiny_dataset, fake_dataset):
    create_prsn_netcdf_from_source(tiny_dataset, fake_dataset)
    assert fake_dataset.dependent_varnames() == ['prsn']
    assert np.shape(fake_dataset.variables['prsn']) == (11688, 4, 2)
    assert fake_dataset.variables['prsn'].standard_name == 'snowfall_flux'
    assert fake_dataset.variables['prsn'].long_name == 'Precipitation as Snow'
    assert fake_dataset.variables['prsn'].units == 'g cm-2 s-1'

@pytest.mark.parametrize('tiny_dataset, new_var, expected', [
    ('downscaled_pr', 'prsn', 'prsn_day_BCCAQ2_ACCESS1-0_ACCESS1-0+historical+rcp45+r1i1p1_r1i1p1_19600101-19911231.nc'),
    ('downscaled_pr', 'tasmin', 'tasmin_day_BCCAQ2_ACCESS1-0_ACCESS1-0+historical+rcp45+r1i1p1_r1i1p1_19600101-19911231.nc'),
    ('downscaled_pr', 'tasmax', 'tasmax_day_BCCAQ2_ACCESS1-0_ACCESS1-0+historical+rcp45+r1i1p1_r1i1p1_19600101-19911231.nc')
], indirect=['tiny_dataset'])
def test_create_filepath_from_source(tiny_dataset, new_var, outdir, expected):
    assert create_filepath_from_source(tiny_dataset, new_var, outdir) == \
        outdir + '/' + expected


@pytest.mark.parametrize('required_vars', [
    (['pr', 'tasmin', 'tasmax']),
    (['pr', 'tasmin'])
])
def test_has_required_vars(required_vars, datasets):
    assert has_required_vars(datasets, required_vars)


@pytest.mark.parametrize('required_vars', [
    (['pr', 'tasmin', 'tasmax', 'missing_var'])
])
def test_has_required_vars_missing_vars(required_vars, datasets):
    assert not has_required_vars(datasets, required_vars)


def test_matching_datasets(datasets):
    assert matching_datasets(datasets)


@pytest.mark.parametrize('tiny_dataset', [
    ('downscaled_pr')
], indirect=['tiny_dataset'])
def test_matching_datasets_not_matching(tiny_dataset, datasets):
    datasets.update({'tiny': tiny_dataset})
    assert not matching_datasets(datasets)


@pytest.mark.parametrize('tiny_dataset', [
    ('downscaled_pr'),
    ('downscaled_pr_packed'),
    ('daily_pr')
], indirect=['tiny_dataset'])
def test_check_pr_units(tiny_dataset):
    assert check_pr_units(tiny_dataset.variables['pr'].units)


@pytest.mark.parametrize('fake_dataset', [
    {
        'dimensions': [('time', 10)],
        'variables': [
            {'name': 'pr', 'dimensions': ('time',),
             'attributes': {'units': 'kg'}},
        ]
    }
], indirect=['fake_dataset'])
def test_check_pr_units_bad_unit(fake_dataset):
    assert not check_pr_units(fake_dataset.variables['pr'].units)


@pytest.mark.parametrize('pr, tasmin, tasmax', [
    ('daily_pr', 'daily_tasmin', 'daily_tasmax')
])
@pytest.mark.parametrize('fake_dataset', [
    {}
], indirect=['fake_dataset'])
def test_process_to_prsn(pr, tasmin, tasmax, fake_dataset):
    pr_dataset = get_dataset(pr)
    create_prsn_netcdf_from_source(pr_dataset, fake_dataset)

    variables = {
        'pr': pr_dataset.variables['pr'],
        'tasmin': get_dataset(tasmin).variables['tasmin'],
        'tasmax': get_dataset(tasmax).variables['tasmax']
    }

    process_to_prsn(variables, fake_dataset, 1000)

    result = fake_dataset.variables['prsn'][:]
    result = np.where(result != 0)
    for array in result:
        assert len(array) == 0

    # Test conversion from mm to cm
    pr_mm = pr_dataset.variables['pr'][:]
    pr_units_from = ureg.parse_units('kg/m^2/s')
    pr_units_to = ureg.parse_units('g/cm^2/s')
    pr_cm = pr_mm * Q_(1.0, pr_units_from).to(pr_units_to).magnitude
    assert pr_cm == pytest.approx(pr_mm/10.0)


@pytest.mark.parametrize('units_from, units_to, expected', [
    ('degC', 'K', 273.15),
    ('K', 'degC', -273.15)
])
def test_convert_temperature_units(units_from, units_to, expected):
    zeros = np.zeros((10, 5))
    result = convert_temperature_units(zeros, units_from, units_to)
    assert (result == expected).all()
