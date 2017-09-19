from setuptools import setup

__version__ = (0, 2, 1)

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
        'dp': ['tests/data/*.nc']
    },
    scripts='''
        scripts/generate_climos
        scripts/split_merged_climos
        scripts/update_metadata
    '''.split(),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Scientific/Engineering',
        'Topic :: Database',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]

)
