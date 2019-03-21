import pytest
import os

import numpy as np
from tempfile import NamedTemporaryFile

from nchelpers import CFDataset
from dp.generate_prsn import unique_shape, is_unique_value, \
    determine_freezing, create_prsn_netcdf_from_source


@pytest.mark.parametrize('arrays', [
    ([np.arange(10).reshape(2, 5), np.arange(10).reshape(2, 5)]),
    ([np.arange(100).reshape(2, 5, 10), np.arange(100).reshape(2, 5, 10)])
])
def test_unique_shape(arrays):
    assert unique_shape(arrays)


@pytest.mark.parametrize('arrays', [
    ([np.arange(10).reshape(2, 5), np.arange(10).reshape(10, 1)]),
    ([np.arange(100).reshape(2, 5, 10), np.arange(100).reshape(10, 10)])
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
    ('degreeC', 0.0),
    ('k', 273.15),
    ('K', 273.15)
])
def test_determine_freezing(unit, expected):
    assert determine_freezing(unit) == expected


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
