"""Unit tests for the core function create_climo_files.

These tests are all parametrized over several test input files, which requires a little trickiness with fixtures.
pytest doesn't directly support parametrizing over fixtures (which here deliver the test input files
and the output of create_climo_files). To get around that, we use indirect fixtures, which are passed a parameter
that they use to determine their behaviour, i.e. what input file to return or process.

The key indirected fixtures are:

    tiny_filepath
        param: (str) selects the input file to be processed by generate_climos
        returns: (str) input file path to be processed by generate_climos
    tiny_dataset
        param: (str) selects the input file to be processed by create_climo_files
        returns: (nchelpers.CFDataset) input file to be processed by create_climo_files
"""
# TODO: Add more test input files:
# - hydromodel from observed data
# - a monthly or seasonal duration variable file (if such a thing even exists)

import os
from datetime import datetime

from netCDF4 import date2num
from dateutil.relativedelta import relativedelta
from pytest import mark, warns
from pytest_mock import mocker
from unittest.mock import ANY

from nchelpers import CFDataset

from dp.units_helpers import Unit
from dp.generate_climos import generate_climos, create_climo_files


# Helper functions


def t_start(year):
    """Returns the start date of a climatological processing period beginning at start of year"""
    return datetime(year, 1, 1)


def t_end(year):
    """Returns the end date of a climatological processing period ending at end of year"""
    return datetime(year, 12, 30)


def basename_components(filepath):
    """Returns the CMOR(ish) components of the basename (filename) of the given filepath."""
    # Slightly tricky because variable names can contain underscores, which separate components.
    # We find the location f of the frequency component in the split and use it to assemble the components properly.
    pieces = os.path.basename(filepath).split("_")
    frequency_options = [
        "msaClim",
        "saClim",
        "aClim",
        "sClim",
        "mClim",
        "msaClimMean",
        "saClimMean",
        "aClimMean",
        "sClimMean",
        "mClimMean",
        "msaClimSD",
        "saClimSD",
        "aClimSD",
        "sClimSD",
        "mClimSD",
    ]
    f = next(i for i, piece in enumerate(pieces) if piece in frequency_options)
    return ["_".join(pieces[:f])] + pieces[f:]


# Tests


@mark.parametrize(
    "tiny_filepath, operation",
    [
        ("downscaled_tasmax", "std"),
        ("downscaled_pr", "mean"),
        ("gdd_seasonal", "std"),
        ("tr_annual", "mean"),
    ],
    indirect=["tiny_filepath"],
)
@mark.parametrize(
    "convert_longitudes, split_vars, split_intervals, resolutions",
    [
        (True, True, True, "yearly"),
        (False, False, False, "seasonal"),
    ],
)
def test_create_climo_files_call(
    mocker,
    outdir,
    tiny_filepath,
    operation,
    convert_longitudes,
    split_vars,
    split_intervals,
    resolutions,
):
    mock_ccf = mocker.patch("dp.generate_climos.create_climo_files")
    generate_climos(
        tiny_filepath,
        outdir,
        operation,
        convert_longitudes=convert_longitudes,
        split_vars=split_vars,
        split_intervals=split_intervals,
        resolutions=resolutions,
    )
    mock_ccf.assert_called_with(
        ANY,
        outdir,
        ANY,
        operation,
        ANY,
        ANY,
        convert_longitudes=convert_longitudes,
        split_vars=split_vars,
        split_intervals=split_intervals,
        output_resolutions=resolutions,
    )


@mark.slow
@mark.parametrize(
    "period, tiny_dataset, operation, t_start, t_end",
    [
        ("gcm", "gcm", "mean", t_start(1965), t_end(1970)),
        (
            "gcm_360_day_cal",
            "gcm_360_day_cal",
            "std",
            t_start(1965),
            t_end(1970),
        ),  # test date processing
        ("downscaled_tasmax", "downscaled_tasmax", "mean", t_start(1961), t_end(1990)),
        ("downscaled_pr", "downscaled_pr", "std", t_start(1961), t_end(1990)),
        ("hydromodel_gcm", "hydromodel_gcm", "mean", t_start(1984), t_end(1995)),
        (
            "gdd_seasonal",
            "gdd_seasonal",
            "mean",
            t_start(1971),
            t_end(2000),
        ),  # test seasonal-only
        (
            "tr_annual",
            "tr_annual",
            "mean",
            t_start(1961),
            t_end(1990),
        ),  # test annual-only
        ("daily_prsn", "daily_prsn", "mean", t_start(1950), t_end(2100)),
    ],
    indirect=["tiny_dataset", "period"],
)
@mark.parametrize(
    "split_vars",
    [
        False,
        True,
    ],
)
@mark.parametrize(
    "split_intervals",
    [
        False,
        True,
    ],
)
def test_existence(
    period, outdir, tiny_dataset, operation, t_start, t_end, split_vars, split_intervals
):
    """Test that the expected number of files was created and that the filenames returned by
    create_climo_files are those actually created.
    """
    climo_files = create_climo_files(
        period,
        outdir,
        tiny_dataset,
        operation,
        t_start,
        t_end,
        convert_longitudes=True,
        split_vars=split_vars,
        split_intervals=split_intervals,
        output_resolutions={"yearly", "seasonal", "monthly"},
    )
    num_vars = len(tiny_dataset.dependent_varnames())
    num_files = 1
    num_intervals = {"daily": 3, "monthly": 3, "seasonal": 2, "yearly": 1}[
        tiny_dataset.time_resolution
    ]
    if split_vars:
        num_files *= num_vars
    if split_intervals:
        num_files *= num_intervals
    assert len(climo_files) == num_files
    assert len(os.listdir(outdir)) == num_files
    assert set(climo_files) == set(os.path.join(outdir, f) for f in os.listdir(outdir))


@mark.slow
@mark.parametrize(
    "period, tiny_dataset, operation, t_start, t_end",
    [
        ("gcm", "gcm", "std", t_start(1965), t_end(1970)),
        ("downscaled_tasmax", "downscaled_tasmax", "mean", t_start(1961), t_end(1990)),
        ("downscaled_pr", "downscaled_pr", "std", t_start(1961), t_end(1990)),
        ("hydromodel_gcm", "hydromodel_gcm", "mean", t_start(1984), t_end(1995)),
        ("gdd_seasonal", "gdd_seasonal", "mean", t_start(1961), t_end(1990)),
        ("daily_prsn", "daily_prsn", "mean", t_start(1950), t_end(2100)),
    ],
    indirect=["period", "tiny_dataset"],
)
@mark.parametrize(
    "split_vars",
    [
        False,
        True,
    ],
)
@mark.parametrize(
    "split_intervals",
    [
        False,
        True,
    ],
)
def test_filenames(
    period, outdir, tiny_dataset, operation, t_start, t_end, split_vars, split_intervals
):
    """Test that the filenames are as expected. Tests only the following easy-to-test filename components:
    - variable name
    - frequency
    Testing all the components of the filenames would be a lot of work and would duplicate unit tests for
    the filename generator in nchelpers.
    """
    climo_files = create_climo_files(
        period,
        outdir,
        tiny_dataset,
        operation,
        t_start,
        t_end,
        convert_longitudes=True,
        split_vars=split_vars,
        split_intervals=split_intervals,
        output_resolutions={"yearly", "seasonal", "monthly"},
    )
    if split_vars:
        varnames = set(tiny_dataset.dependent_varnames())
    else:
        varnames = {"+".join(sorted(tiny_dataset.dependent_varnames()))}
    assert varnames == set(basename_components(fp)[0] for fp in climo_files)
    for fp in climo_files:
        frequency = basename_components(fp)[1]
        with CFDataset(fp) as cf:
            assert cf.frequency == frequency
        if split_intervals:
            assert (
                frequency
                in "mClim mClimSD mClimMean sClim sClimSD sClimMean aClim aClimSD aClimMean".split()
            )
        else:
            assert (
                frequency
                in "aClim aClimSD aClimMean saClim saClimSD saClimMean msaClim msaClimSD msaClimMean".split()
            )


@mark.slow
@mark.parametrize(
    "period, tiny_dataset, operation, t_start, t_end",
    [
        ("gcm", "gcm", "std", t_start(1965), t_end(1970)),
        ("downscaled_tasmax", "downscaled_tasmax", "mean", t_start(1961), t_end(1990)),
        ("downscaled_pr", "downscaled_pr", "std", t_start(1961), t_end(1990)),
        ("hydromodel_gcm", "hydromodel_gcm", "mean", t_start(1984), t_end(1995)),
        ("gdd_seasonal", "gdd_seasonal", "mean", t_start(1981), t_end(2010)),
        ("tr_annual", "tr_annual", "std", t_start(1960), t_end(1970)),
        ("daily_prsn", "daily_prsn", "mean", t_start(1950), t_end(2100)),
    ],
    indirect=["period", "tiny_dataset"],
)
@mark.parametrize(
    "split_vars",
    [
        False,
        True,
    ],
)
@mark.parametrize(
    "split_intervals",
    [
        False,
        True,
    ],
)
def test_climo_metadata(
    period, outdir, tiny_dataset, operation, t_start, t_end, split_vars, split_intervals
):
    """Test that the correct climo-specific metadata has been added/updated."""
    climo_files = create_climo_files(
        period,
        outdir,
        tiny_dataset,
        operation,
        t_start,
        t_end,
        convert_longitudes=True,
        split_vars=split_vars,
        split_intervals=split_intervals,
        output_resolutions={"yearly", "seasonal", "monthly"},
    )
    frequencies = set()

    def history_items(hist_str):
        '''returns components of hist_str separated by ": "'''
        return hist_str.split(": ")

    for fp in climo_files:
        with CFDataset(fp) as cf:
            frequencies.add(cf.frequency)
            assert cf.is_multi_year
            # In Python2.7, datetime.datime.isoformat does not take params telling it how much precision to
            # provide in its output; standard requires 'seconds' precision, which means the first 19 characters.
            assert cf.climo_start_time == t_start.isoformat()[:19] + "Z"
            assert cf.climo_end_time == t_end.isoformat()[:19] + "Z"
            assert getattr(cf, "climo_tracking_id", None) == getattr(
                tiny_dataset, "tracking_id", None
            )

            # Tests for history metadata updates
            assert cf.history
            hist_lines = cf.history.split("\n")
            end_items = history_items(hist_lines[0])
            assert (
                end_items[-1].split(" ")[0] == "generate_climos"
                and end_items[-2] == "end"
            )
            found_start = False
            for idx, h in enumerate(hist_lines):
                h_items = history_items(h)
                if (
                    h_items[-2] == "start"
                    and h_items[-1].split(" ")[0] == "generate_climos"
                ):
                    found_start = True
                    break
            assert found_start
            original_hist = hist_lines[idx + 1 :]
            assert "\n".join(original_hist) == tiny_dataset.history

    suffix = {
        "std": "SD",
        "mean": "Mean",
    }[operation]

    if split_intervals:
        assert (
            frequencies
            == {
                "daily": {"mClim" + suffix, "sClim" + suffix, "aClim" + suffix},
                "monthly": {"mClim" + suffix, "sClim" + suffix, "aClim" + suffix},
                "seasonal": {"sClim" + suffix, "aClim" + suffix},
                "yearly": {"aClim" + suffix},
            }[tiny_dataset.time_resolution]
        )
    else:
        assert (
            frequencies
            == {
                "daily": {"msaClim" + suffix},
                "monthly": {"msaClim" + suffix},
                "seasonal": {"saClim" + suffix},
                "yearly": {"aClim" + suffix},
            }[tiny_dataset.time_resolution]
        )


@mark.parametrize(
    "period, tiny_dataset, comparison",
    [
        ("gdd_seasonal", "gdd_seasonal", "greatermean"),
        ("fd_monthly", "fd_monthly", "greatermean"),
        ("txx_monthly", "txx_monthly", "greatermin"),
        ("tnn_monthly", "tnn_monthly", "lessermax"),
    ],
    indirect=["period", "tiny_dataset"],
)
@mark.parametrize(
    "t_start, t_end", [(t_start(1971), t_end(2000)), (t_start(2010), t_end(2039))]
)
def test_variable_aggregation(period, outdir, tiny_dataset, comparison, t_start, t_end):
    """Test that the values for variables aggregated within a year are
    in the expected range. For these variables, the value of a year is
    *not* the mean of the monthly or seasonal values. Checks to make
    sure the distribution of values in seasonal or annual data varies
    from the distribution of monthly data in the expected direction by
    comparing output mins, means, or maxes, to input mins, means, or maxes.
    Note that there is possible weirdness to comparing the *entire* input
    timeseries to a specific output time period: a variable whose range
    shifts dramatically over time could possibly have false failures
    if used for this test.
    When aggregated from monthly or seasonal scale to yearly scale:
     - Counted variables should have larger means, minimums, and maximums.
     - Maximum variables should have larger minimums and means but similar
       maximums.
     - Minimum variables should have smaller maximums and means but similar
       minimums."""
    test = {
        "greatermean": lambda a, b: a.mean() > b.mean(),
        "greatermin": lambda a, b: a.min() > b.min(),
        "lessermax": lambda a, b: a.max() < b.max(),
    }[comparison]
    climo_files = create_climo_files(
        period,
        outdir,
        tiny_dataset,
        "mean",
        t_start,
        t_end,
        convert_longitudes=True,
        split_vars=False,
        split_intervals=True,
        output_resolutions={"yearly", "seasonal", "monthly"},
    )
    for cf in climo_files:
        for var in tiny_dataset.dependent_varnames():
            invar = tiny_dataset.variables[var][:]
            with CFDataset(cf) as out:
                outvar = out.variables[var][:]
                timeres_ordinality = {
                    "daily": 1,
                    "monthly": 2,
                    "seasonal": 3,
                    "yearly": 4,
                }
                inres = timeres_ordinality[tiny_dataset.time_resolution]
                outres = timeres_ordinality[out.time_resolution]
                if outres > inres:
                    assert test(outvar, invar)


@mark.parametrize(
    "period, tiny_dataset, operation, t_start, t_end",
    [
        ("wsdi_annual", "wsdi_annual", "mean", t_start(2010), t_end(2039)),
        ("wsdi_annual", "wsdi_annual", "std", t_start(1961), t_end(1990)),
    ],
    indirect=["period", "tiny_dataset"],
)
def test_duration_variable_resolutions(
    period, outdir, tiny_dataset, operation, t_start, t_end
):
    """Datasets with duration variables (values measuring the number of
    consecutive days something happens) cannot be aggregated into coarser
    time values. Test that output resolution matches input resolution."""
    climo_files = create_climo_files(
        period,
        outdir,
        tiny_dataset,
        operation,
        t_start,
        t_end,
        convert_longitudes=True,
        split_vars=False,
        split_intervals=False,
        output_resolutions={"yearly", "seasonal", "monthly"},
    )
    for cf in climo_files:
        with CFDataset(cf) as output:
            assert tiny_dataset.time_resolution == output.time_resolution


@mark.slow
@mark.parametrize(
    "period, tiny_dataset, operation, t_start, t_end, var",
    [
        ("downscaled_pr", "downscaled_pr", "mean", t_start(1965), t_end(1970), "pr"),
        (
            "downscaled_pr_packed",
            "downscaled_pr_packed",
            "std",
            t_start(1965),
            t_end(1970),
            "pr",
        ),
        ("daily_prsn", "daily_prsn", "mean", t_start(1950), t_end(2100), "prsn"),
    ],
    indirect=["period", "tiny_dataset"],
)
@mark.parametrize(
    "split_vars",
    [
        False,
        True,
    ],
)
@mark.parametrize(
    "split_intervals",
    [
        False,
        True,
    ],
)
def test_pr_units_conversion(
    period,
    outdir,
    tiny_dataset,
    operation,
    t_start,
    t_end,
    var,
    split_vars,
    split_intervals,
):
    """Test that units conversion for 'pr' variable is performed properly, for both packed and unpacked files.
    Test for unpacked file is pretty elementary: check pr units.
    Test for packed checks that packing params are modified correctly.
    """
    climo_files = create_climo_files(
        period,
        outdir,
        tiny_dataset,
        operation,
        t_start,
        t_end,
        convert_longitudes=True,
        split_vars=split_vars,
        split_intervals=split_intervals,
        output_resolutions={"yearly", "seasonal", "monthly"},
    )

    assert var in tiny_dataset.dependent_varnames()
    input_pr_var = tiny_dataset.variables[var]
    assert Unit.from_udunits_str(input_pr_var.units) in [
        Unit("kg/m**2/s"),
        Unit("mm/s"),
    ]
    seconds_per_day = 86400
    for fp in climo_files:
        with CFDataset(fp) as cf:
            if var in cf.dependent_varnames():
                output_pr_var = cf.variables[var]
                assert Unit.from_udunits_str(output_pr_var.units) in [
                    Unit("kg/m**2/day"),
                    Unit("mm/day"),
                ]
                if hasattr(input_pr_var, "scale_factor") or hasattr(
                    input_pr_var, "add_offset"
                ):
                    try:
                        assert (
                            output_pr_var.scale_factor
                            == seconds_per_day * input_pr_var.scale_factor
                        )
                    except AttributeError:
                        assert output_pr_var.scale_factor == seconds_per_day * 1.0
                    try:
                        assert (
                            output_pr_var.add_offset
                            == seconds_per_day * input_pr_var.add_offset
                        )
                    except AttributeError:
                        assert output_pr_var.add_offset == 0.0


@mark.slow
@mark.parametrize(
    "period, tiny_dataset, operation, t_start, t_end",
    [
        ("gcm", "gcm", "std", t_start(1965), t_end(1970)),
        ("downscaled_tasmax", "downscaled_tasmax", "mean", t_start(1961), t_end(1990)),
        ("downscaled_pr", "downscaled_pr", "std", t_start(1961), t_end(1990)),
        ("hydromodel_gcm", "hydromodel_gcm", "mean", t_start(1984), t_end(1995)),
        ("gdd_seasonal", "gdd_seasonal", "mean", t_start(1971), t_end(2000)),
    ],
    indirect=["period", "tiny_dataset"],
)
@mark.parametrize(
    "split_vars",
    [
        False,
        True,
    ],
)
@mark.parametrize(
    "split_intervals",
    [
        False,
        True,
    ],
)
def test_dependent_variables(
    period, outdir, tiny_dataset, operation, t_start, t_end, split_vars, split_intervals
):
    """Test that the output files contain the expected dependent variables"""
    climo_files = create_climo_files(
        period,
        outdir,
        tiny_dataset,
        operation,
        t_start,
        t_end,
        convert_longitudes=True,
        split_vars=split_vars,
        split_intervals=split_intervals,
        output_resolutions={"yearly", "seasonal", "monthly"},
    )
    dependent_varnames_in_cfs = set()
    for fp in climo_files:
        with CFDataset(fp) as cf:
            dependent_varnames_in_cfs.update(cf.dependent_varnames())
            if split_vars:
                # There should be one dependent variable from the input file
                assert len(cf.dependent_varnames()) == 1
    # All the input dependent variables should be covered by all the output files
    assert dependent_varnames_in_cfs == set(tiny_dataset.dependent_varnames())


@mark.slow
@mark.parametrize(
    "period, tiny_dataset, operation, t_start, t_end",
    [
        ("gcm", "gcm", "mean", t_start(1965), t_end(1970)),
        ("downscaled_tasmax", "downscaled_tasmax", "mean", t_start(1961), t_end(1990)),
        # No need to repleat with downscaled_pr
        ("hydromodel_gcm", "hydromodel_gcm", "mean", t_start(1984), t_end(1995)),
    ],
    indirect=["period", "tiny_dataset"],
)
@mark.parametrize(
    "split_vars",
    [
        False,
        True,
    ],
)
@mark.parametrize(
    "split_intervals",
    [
        False,
        True,
    ],
)
def test_time_and_climo_bounds_vars(
    period, outdir, tiny_dataset, operation, t_start, t_end, split_vars, split_intervals
):
    """Test that the climo output files contain the expected time values and climo bounds."""
    climo_files = create_climo_files(
        period,
        outdir,
        tiny_dataset,
        operation,
        t_start,
        t_end,
        convert_longitudes=True,
        split_vars=split_vars,
        split_intervals=split_intervals,
        output_resolutions={"yearly", "seasonal", "monthly"},
    )

    for fp in climo_files:
        with CFDataset(fp) as cf:
            expected_num_time_values = {
                "mClim": 12,
                "sClim": 4,
                "aClim": 1,
                "saClim": 5,
                "msaClim": 17,
                "mClimMean": 12,
                "sClimMean": 4,
                "aClimMean": 1,
                "saClimMean": 5,
                "msaClimMean": 17,
                "mClimSD": 12,
                "sClimSD": 4,
                "aClimSD": 1,
                "saClimSD": 5,
                "msaClimSD": 17,
            }[cf.frequency]

            assert cf.time_var
            assert cf.time_var.climatology == "climatology_bnds"
            climo_bnds_var = cf.variables[cf.time_var.climatology]
            assert climo_bnds_var

            assert len(cf.time_var) == expected_num_time_values
            assert len(climo_bnds_var) == expected_num_time_values

            climo_year = (t_start.year + t_end.year + 1) / 2
            time_steps = (t for t in cf.time_steps["datetime"])
            climo_bnds = (cb for cb in climo_bnds_var)

            def d2n(date):
                return date2num(date, cf.time_var.units, cf.time_var.calendar)

            # Test monthly timesteps and climo bounds
            if cf.frequency in {"mClim", "msaClim", "mClimSD", "msaClimSD"}:
                for month in range(1, 13):
                    t = next(time_steps)
                    assert (t.year, t.month, t.day) == (climo_year, month, 15)
                    cb = next(climo_bnds)
                    assert len(cb) == 2
                    assert cb[0] == d2n(datetime(t_start.year, month, 1))
                    assert cb[1] == d2n(
                        datetime(t_end.year, month, 1) + relativedelta(months=1)
                    )

            # Test seasonal timesteps and climo bounds
            if cf.frequency in {"sClim", "msaClim", "sClimSD", "msaClimSD"}:
                for month in [1, 4, 7, 10]:  # center months of seasons
                    t = next(time_steps)
                    assert (t.year, t.month, t.day) == (climo_year, month, 16)
                    cb = next(climo_bnds)
                    assert cb[0] == d2n(
                        datetime(t_start.year, month, 1) + relativedelta(months=-1)
                    )
                    assert cb[1] == d2n(
                        datetime(t_end.year, month, 1) + relativedelta(months=2)
                    )

            # Test annual timestep and climo bounds
            if cf.frequency in {"aClimSD", "msaClimSD"}:
                t = next(time_steps)
                assert (t.year, t.month, t.day) == (climo_year, 7, 2)
                cb = next(climo_bnds)
                assert cb[0] == d2n(t_start)
                assert cb[1] == d2n(datetime(t_end.year + 1, 1, 1))


@mark.slow
@mark.parametrize(
    "period, tiny_dataset, operation, t_start, t_end",
    [
        ("gcm", "gcm", "std", t_start(1965), t_end(1970)),
        ("downscaled_tasmax", "downscaled_tasmax", "mean", t_start(1961), t_end(1990)),
        # No need to repleat with downscaled_pr
        ("hydromodel_gcm", "hydromodel_gcm", "std", t_start(1984), t_end(1995)),
    ],
    indirect=["period", "tiny_dataset"],
)
@mark.parametrize(
    "split_vars",
    [
        False,
        True,
    ],
)
@mark.parametrize(
    "split_intervals",
    [
        False,
        True,
    ],
)
@mark.parametrize(
    "convert_longitudes",
    [
        False,
        True,
    ],
)
def test_convert_longitudes(
    period,
    outdir,
    tiny_dataset,
    operation,
    t_start,
    t_end,
    split_vars,
    split_intervals,
    convert_longitudes,
):
    """Test that longitude conversion is performed correctly."""
    climo_files = create_climo_files(
        period,
        outdir,
        tiny_dataset,
        operation,
        t_start,
        t_end,
        split_vars=split_vars,
        split_intervals=split_intervals,
        convert_longitudes=convert_longitudes,
        output_resolutions={"yearly", "seasonal", "monthly"},
    )
    input_lon_var = tiny_dataset.lon_var[:]
    for fp in climo_files:
        with CFDataset(fp) as output_file:
            output_lon_var = output_file.lon_var[:]
            check_these = [(input_lon_var, output_lon_var)]
            if hasattr(input_lon_var, "bounds"):
                check_these.append(
                    (
                        tiny_dataset.variables[input_lon_var.bounds],
                        output_file.variables[output_lon_var.bounds],
                    )
                )
            for input_lon_var, output_lon_var in check_these:
                if convert_longitudes:
                    assert all(
                        -180 <= lon < 180 for _, lon in enumerate(output_lon_var)
                    )
                    assert all(
                        output_lon_var[i] == input_lon
                        if input_lon < 180
                        else input_lon - 360
                        for i, input_lon in enumerate(input_lon_var)
                    )
                else:
                    assert all(
                        -180 <= lon < 360 for _, lon in enumerate(output_lon_var)
                    )
                    assert all(
                        output_lon_var[i] == input_lon
                        for i, input_lon in enumerate(input_lon_var)
                    )


@mark.parametrize(
    ("resolutions"),
    [
        {"yearly"},
        {"yearly", "seasonal"},
        {"yearly", "seasonal", "monthly"},
        {"monthly", "daily"},  # Daily does not exist
        set(),
    ],
)
@mark.parametrize(("split_intervals"), [True, False])
def test_resolution_filter(outdir, datasets, resolutions, split_intervals):
    tiny_dataset = datasets["tasmax"]
    climo_files = create_climo_files(
        "",
        outdir,
        tiny_dataset,
        "mean",
        t_start(1965),
        t_end(1970),
        split_vars=False,
        split_intervals=split_intervals,
        convert_longitudes=False,
        output_resolutions=resolutions,
    )
    # Only these resolutions are supported as aggregation targets
    if split_intervals:
        resolutions = resolutions.intersection({"yearly", "seasonal", "monthly"})
        assert len(climo_files) == len(resolutions)
    else:
        assert len(climo_files) == min(1, len(resolutions))


@mark.parametrize(
    ("period, tiny_dataset"),
    [("tr_annual", "tr_annual")],
    indirect=["period", "tiny_dataset"],
)
def test_resolution_warning(period, outdir, tiny_dataset):
    """If we try to compute a monthly climo from an annual file
    there should be zero output files and a warning issued
    """
    with warns(Warning) as record:
        climo_files = create_climo_files(
            period,
            outdir,
            tiny_dataset,
            "mean",
            t_start(1965),
            t_end(1971),
            split_vars=True,
            split_intervals=True,
            convert_longitudes=True,
            output_resolutions={"monthly"},
        )

    def contains_warning(record):
        for warning in record:
            if "None of the selected output resolutions" in str(warning.message):
                return True

        return False

    assert climo_files == []
    assert contains_warning(record)
