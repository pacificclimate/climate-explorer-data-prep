from pytest import fixture, mark
from pkg_resources import resource_filename
from nchelpers import CFDataset, standard_climo_periods


# helpers
def get_dataset(filename):
    return CFDataset(resource_filename(__name__, "data/tiny_{}.nc").format(filename))


def get_filepath(file_key):
    return resource_filename(__name__, "data/tiny_{}.nc").format(file_key)


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
