from pytest import fixture, mark
from pkg_resources import resource_filename
from nchelpers import CFDataset


# helpers
def get_dataset(filename):
    return CFDataset(resource_filename(__name__, 'data/tiny_{}.nc').format(filename))


@fixture
def tiny_dataset(request):
    return CFDataset(resource_filename(__name__, 'data/tiny_{}.nc').format(request.param))


@fixture(scope='function')
def outdir(tmpdir_factory):
    return str(tmpdir_factory.mktemp('outdir'))


@fixture(scope='function')
def datasets():
    return [get_dataset('daily_pr'),
            get_dataset('daily_tasmin'),
            get_dataset('daily_tasmax')]


@fixture
def fake_dataset(request, tmpdir_factory):
    fn = tmpdir_factory.mktemp('testdata').join('test.nc')
    with CFDataset(fn, mode='w') as dataset:
        try:
            dataset.setncatts(request.param['attributes'])
        except KeyError:
            pass

        try:
            dimensions = request.param['dimensions']
        except KeyError:
            dimensions = []
        for dim_name, size in dimensions:
            dataset.createDimension(dim_name, size)

        try:
            variables = request.param['variables']
        except KeyError:
            variables = []
        for spec in variables:
            variable = dataset.createVariable(
                spec['name'], 'f', spec['dimensions'])
            try:
                variable.setncatts(spec['attributes'])
            except KeyError:
                pass

        yield dataset
