# TODO: Most testing. We're in a hurry. Have tested manually.

import pytest

from dp.update_metadata import normalize_experiment_id, parse_ensemble_code


# Custom functions

@pytest.mark.parametrize('input_, expected', [
    ('', ''),
    ('historical', 'historical'),
    ('HistorIcaL', 'historical'),
    ('rcp85', 'rcp85'),
    ('rcp8.5', 'rcp85'),
    ('RCP8.5', 'rcp85'),
    ('Historical, RCP8.5', 'historical, rcp85'),
    ('one,two ,three,   four  ,  five, six', 'one, two, three, four, five, six'),
])
def test_normalize_experiment_id(input_, expected):
    assert normalize_experiment_id(input_) == expected


@pytest.mark.parametrize('input_, expected', [
    ('r1i2p3', {
        'realization': 1,
        'initialization_method': 2,
        'physics_version': 3,
    }),
])
def test_parse_ensemble_code(input_, expected):
    assert parse_ensemble_code(input_) == expected
