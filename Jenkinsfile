@Library('pcic-pipeline-library@1.0.1')_


node {
    stage('Code Collection') {
        collectCode()
    }

    stage('Python Test Suite') {
        def pytestArgs = '-v tests/test_units_helpers.py tests/test_update_metadata.py tests/test_decompose_flow_vectors.py'
        runPythonTestSuite('pcic/geospatial-python', ['requirements.txt'], pytestArgs)
    }

    if (isPypiPublishable()) {
        stage('Push to PYPI') {
            publishPythonPackage('pcic/geospatial-python', 'PCIC_PYPI_CREDS')
        }
    }

    stage('Clean Workspace') {
        cleanWs()
    }
}
