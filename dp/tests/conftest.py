import sys
from importlib import resources

from pytest import fixture, mark
from nchelpers import CFDataset, standard_climo_periods


# helpers
def get_dataset(filename):
    path = get_filepath(filename)
    with CFDataset(path) as nc:
        yield nc


def get_filepath(file_key):
    if sys.version_info >= (3, 9):
        ref = resources.files("dp") / f"tests/data/tiny_{file_key}.nc"
        with resources.as_file(ref) as path:
            return str(path)
    else:
        # fall back to using pkg_resources
        pass


@fixture
def tiny_filepath(request):
    return get_filepath(request.param)


@fixture
def tiny_dataset(request):
    return CFDataset(get_filepath(request.param))


@fixture(scope="function")
def outdir(tmpdir_factory):
    return str(tmpdir_factory.mktemp("outdir"))


@fixture(scope="function")
def period(request):
    input_dataset = get_dataset(request.param)
    if len(input_dataset.climo_periods.keys()) > 0:
        return list(
            input_dataset.climo_periods.keys() & standard_climo_periods().keys()
        )[0]
    else:
        return ""


@fixture(scope="function")
def datasets():
    return {
        "pr": get_dataset("daily_pr"),
        "tasmin": get_dataset("daily_tasmin"),
        "tasmax": get_dataset("daily_tasmax"),
    }


@fixture
def fake_dataset(request, tmpdir_factory):
    fn = tmpdir_factory.mktemp("testdata").join("test.nc")
    with CFDataset(fn, mode="w") as dataset:
        try:
            dataset.setncatts(request.param["attributes"])
        except KeyError:
            pass

        try:
            dimensions = request.param["dimensions"]
        except KeyError:
            dimensions = []
        for dim_name, size in dimensions:
            dataset.createDimension(dim_name, size)

        try:
            variables = request.param["variables"]
        except KeyError:
            variables = []
        for spec in variables:
            variable = dataset.createVariable(spec["name"], "f", spec["dimensions"])
            try:
                variable.setncatts(spec["attributes"])
            except KeyError:
                pass

        yield dataset
