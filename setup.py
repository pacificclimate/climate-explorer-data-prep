from setuptools import setup

__version__ = (0, 8, 1)

setup(
    name='ce-dataprep',
    description='PCIC Climate Explorer Data Preparation',
    version='.'.join(str(d) for d in __version__),
    author='Rod Glover',
    author_email='rglover@uvic.ca',
    url='https://github.com/pacificclimate/climate-explorer-data-prep',
    keywords='science climate meteorology downscaling modelling climatology',
    zip_safe=True,
    install_requires='''
        python-dateutil
        cdo
        nchelpers
        pint
        PyYAML
    '''.split(),
    packages=['dp'],
    package_data = {
        'dp': [
            'data/*',
            'tests/data/*.nc'
        ]
    },
    include_package_data=True,
    scripts='''
        scripts/generate_climos
        scripts/generate_prsn
        scripts/split_merged_climos
        scripts/update_metadata
	    scripts/decompose_flow_vectors
    '''.split(),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Topic :: Scientific/Engineering',
        'Topic :: Database',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]

)
