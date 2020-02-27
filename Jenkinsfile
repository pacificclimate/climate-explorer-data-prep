@Library('pcic-pipeline-library@1.0.1')_


node {
    stage('Code Collection') {
        collectCode()
    }

    stage('Python Test Suite') {
        def options = [aptPackages: ['cdo']]
        def pytestArgs = '-v --ignore=tests/test_decompose_flow_vectors.py'
        parallel "Python 3.6": {
            runPythonTestSuite('pcic/crmprtd-test-env:python-3.6',
                               ['requirements.txt'], pytestArgs, options)
        },
        "Python 3.7": {
            runPythonTestSuite('pcic/crmprtd-test-env:python-3.7',
                               ['requirements.txt'], pytestArgs, options)
        }
    }

    if (isPypiPublishable()) {
        stage('Push to PYPI') {
            publishPythonPackage('pcic/crmprtd-test-env:python-3.6',
                                 'PCIC_PYPI_CREDS')
        }
    }

    stage('Clean Workspace') {
        cleanWs()
    }
}
