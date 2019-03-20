import pytest
import numpy as np

from dp.generate_prsn import unique_shape

@pytest.mark.parametrize('shapes', [
    ([np.arange(10).reshape(2, 5), np.arange(10).reshape(2, 5)])
])
def test_unique_shape(shapes):
    assert unique_shape(shapes)


@pytest.mark.parametrize('shapes', [
    ([np.arange(10).reshape(2, 5), np.arange(10).reshape(10, 1)])
])
def test_unique_shape_different_shape(shapes):
    assert not unique_shape(shapes)
