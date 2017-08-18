from pytest import fixture, mark
from pkg_resources import resource_filename
from nchelpers import CFDataset


@fixture
def tiny_dataset(request):
    return CFDataset(resource_filename(__name__, 'data/tiny_{}.nc').format(request.param))


@fixture(scope='function')
def outdir(tmpdir_factory):
    return str(tmpdir_factory.mktemp('outdir'))
