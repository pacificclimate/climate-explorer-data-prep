import mock 
import pytest
import os
import imp
from pytest_mock import mocker 

gc = imp.load_source('generate_climos', 'scripts/generate_climos')

def test_main(mocker):
    assert gc.main