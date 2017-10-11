# TODO: More testing. We're in a hurry. Have tested manually.

import pytest

from dp.update_metadata import \
    variable_info, \
    long_name_for_var, cell_methods_for_var, \
    normalize_experiment_id, \
    parse_ensemble_code, \
    set_attribute_from_expression, \
    process_updates


# Data loading

def test_variable_info():
    assert all(
        key in variable_info for key in '''
            altcddETCCDI
            altcsdiETCCDI
            altcwdETCCDI
            altwsdiETCCDI
            cddETCCDI
            csdiETCCDI
            cwdETCCDI
            dtrETCCDI
            fdETCCDI
            gslETCCDI
            idETCCDI
            prcptotETCCDI
            r10mmETCCDI
            r1mmETCCDI
            r20mmETCCDI
            r95pETCCDI
            r99pETCCDI
            rx1dayETCCDI
            rx1dayETCCDI
            rx5dayETCCDI
            rx5dayETCCDI
            sdiiETCCDI
            suETCCDI
            tn10pETCCDI
            tn90pETCCDI
            tnnETCCDI
            tnxETCCDI
            trETCCDI
            tx10pETCCDI
            tx90pETCCDI
            txnETCCDI
            txxETCCDI
            wsdiETCCDI
        '''.split()
    )

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


@pytest.mark.parametrize('func, arg, result', [
    (cell_methods_for_var,
     'tnnETCCDI', 'time: minimum within days time: minimum over months'),
    (long_name_for_var,
     'tnnETCCDI', 'Monthly Minimum of Daily Minimum Temperature'),
])
def test_variable_info_functions(func, arg, result):
    assert func(arg) == result


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
@pytest.mark.parametrize('target_key, target_name', [
    ('global', 'global'),
    ('var', 'var'),
    ("='va'+'r'", 'var'),
    ("=dependent_varname", 'var'),
])
def test_process_updates(fake_dataset, target_key, target_name):
    updates = {
        target_key: {'yow': '=1+2'}
    }
    process_updates(fake_dataset, updates)
    if target_name == 'global':
        target = fake_dataset
    else:
        target = fake_dataset.variables[target_name]
    assert target.yow == 3
