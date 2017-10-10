# TODO: More testing. We're in a hurry. Have tested manually.

import pytest

from dp.update_metadata import normalize_experiment_id, parse_ensemble_code, \
    set_attribute_from_expression, process_updates


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


# Set from expression

@pytest.mark.parametrize('fake_dataset', [
    {
        'attributes': {'foo': 'bar'},
        'dimensions': [('time', 10)],
        'variables': [
            {'name': 'var', 'dimensions': ('time',),
             'attributes': {'baz': 'qux'}},
        ]
    }
], indirect=['fake_dataset'])
class TestSetAttributeFromExpression(object):

    def test_fixture(self, fake_dataset):
        assert fake_dataset.foo == 'bar'
        assert set(fake_dataset.dimensions.keys()) == {'time'}
        assert set(fake_dataset.variables.keys()) == {'var'}
        assert fake_dataset.dependent_varnames() == ['var']
        assert fake_dataset.variables['var'].baz == 'qux'

    @pytest.mark.parametrize('expression, expected', [
        ('1+2', 3),
        ('foo', 'bar'),
        ('filepath()', 'test.nc'),
        ('str(list(dimensions.keys()))', "['time']"),
        ('str(list(variables.keys()))', "['var']"),
        ('str(dependent_varnames())', "['var']"),
        ('variables[dependent_varnames()[0]].baz', 'qux'),
        ('dependent_varname', 'var'),
    ])
    def test_context(self, fake_dataset, expression, expected):
        target = fake_dataset
        set_attribute_from_expression(
            fake_dataset, target, 'test', expression
        )
        assert target.test == expected


# process_updates

@pytest.mark.parametrize('fake_dataset', [
    {
        'dimensions': [('time', 10)],
        'variables': [
            {'name': 'var', 'dimensions': ('time',)}
        ]
    }
], indirect=['fake_dataset'])
@pytest.mark.parametrize('updates, target_name, attr, value', [
    ({'global': {'other': 'whatnot'}}, 'global', 'other', 'whatnot'),
    ({'var': {'other': 'whatnot'}}, 'var', 'other', 'whatnot'),
    ({"='va'+'r'": {'other': 'whatnot'}}, 'var', 'other', 'whatnot'),
    ({"=dependent_varname": {'other': 'whatnot'}},
     'var', 'other', 'whatnot'),
])
def test_process_updates(fake_dataset, updates, target_name, attr, value):
    process_updates(fake_dataset, updates)
    if target_name == 'global':
        target = fake_dataset
    else:
        target = fake_dataset.variables[target_name]
    assert getattr(target, attr) == value
