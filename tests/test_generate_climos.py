import imp
from dp.generate_climos import create_climo_files
from nchelpers import standard_climo_periods
from pytest_mock import mocker

gc = imp.load_source("generate_climos", "scripts/generate_climos")


class ArgumentParserMocker:
    def __init__(
        self,
        filepaths,
        operation,
        outdir,
        dry_run=False,
        loglevel="INFO",
        convert_longitudes=True,
        split_vars=True,
        split_intervals=True,
        climo=None,
        resolutions=None,
    ):
        self.filepaths = filepaths
        self.operation = operation
        self.outdir = outdir
        self.dry_run = dry_run
        self.loglevel = loglevel
        self.convert_longitudes = convert_longitudes
        self.split_vars = split_vars
        self.split_intervals = split_intervals
        if not climo:
            self.climo = standard_climo_periods().keys()
        if not resolutions:
            self.resolutions = ["yearly", "seasonal", "monthly"]

def test_create_climo_files_call(mocker):
    mock = mocker.patch("dp.generate_climos.create_climo_files")

    args = ArgumentParserMocker(["./tests/data/tiny_daily_pr.nc"], "mean", "output")
    gc.main(args)

    mock.assert_any_call()