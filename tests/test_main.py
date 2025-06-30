import pytest
from typer.testing import CliRunner
from pathlib import Path
import shutil
from unittest.mock import patch

from swf_testbed_cli.main import app

runner = CliRunner()

@pytest.fixture(scope="function")
def test_environment(tmp_path):
    """Create a temporary directory for testing."""
    # tmp_path is a Path object provided by pytest
    # Change the current working directory to the temporary directory
    # so that the CLI commands run in a clean environment.
    # This is important because the CLI app creates files/dirs in the CWD.
    import os
    cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    # Teardown: clean up by changing back to the original directory
    os.chdir(cwd)

@patch('subprocess.run')
def test_start(mock_run, test_environment):
    """Test the start command."""
    # Arrange
    (test_environment / "supervisord.conf").touch()
    (test_environment / "docker-compose.yml").touch()
    mock_run.return_value.returncode = 0

    # Act
    result = runner.invoke(app, ["start"])

    # Assert
    assert result.exit_code == 0
    assert mock_run.call_count == 2
    mock_run.assert_any_call(["docker", "compose", "up", "-d"])
    mock_run.assert_any_call(["supervisorctl", "-c", "supervisord.conf", "start", "all"])
    assert "Starting testbed services..." in result.stdout

@patch('subprocess.run')
def test_stop(mock_run, test_environment):
    """Test the stop command."""
    # Arrange
    (test_environment / "supervisord.conf").touch()

    # Act
    result = runner.invoke(app, ["stop"])

    # Assert
    assert result.exit_code == 0
    assert mock_run.call_count == 2
    mock_run.assert_any_call(["supervisorctl", "-c", "supervisord.conf", "stop", "all"])
    mock_run.assert_any_call(["docker", "compose", "down"])
    assert "Stopping testbed services..." in result.stdout

@patch('subprocess.run')
def test_status(mock_run, test_environment):
    """Test the status command."""
    # Arrange
    (test_environment / "supervisord.conf").touch()

    # Act
    result = runner.invoke(app, ["status"])

    # Assert
    assert result.exit_code == 0
    assert mock_run.call_count == 2
    mock_run.assert_any_call(["docker", "compose", "ps"])
    mock_run.assert_any_call(["supervisorctl", "-c", "supervisord.conf", "status"])
    assert "--- Docker services status ---" in result.stdout
    assert "--- supervisord services status ---" in result.stdout


@patch('swf_testbed_cli.main._check_activemq_connection', return_value=True)
@patch('swf_testbed_cli.main._check_postgres_connection', return_value=True)
@patch('swf_testbed_cli.main._check_supervisord_running', return_value=False)
@patch('subprocess.run')
def test_start_local_success(mock_run, mock_check_supervisord, mock_check_postgres, mock_check_activemq, test_environment):
    """Test the start-local command when services are running and supervisord is not."""
    # Arrange
    (test_environment / "supervisord.conf").touch()

    # Act
    result = runner.invoke(app, ["start-local"])

    # Assert
    assert result.exit_code == 0
    mock_check_postgres.assert_called_once()
    mock_check_activemq.assert_called_once()
    mock_check_supervisord.assert_called_once()
    assert mock_run.call_count == 2
    mock_run.assert_any_call(["supervisord", "-c", "supervisord.conf"])
    mock_run.assert_any_call(["supervisorctl", "-c", "supervisord.conf", "start", "all"])
    assert "--- Starting supervisord services ---" in result.stdout


@patch('swf_testbed_cli.main._check_activemq_connection', return_value=False)
@patch('swf_testbed_cli.main._check_postgres_connection', return_value=True)
@patch('subprocess.run')
def test_start_local_failure(mock_run, mock_check_postgres, mock_check_activemq, test_environment):
    """Test the start-local command when a service is not running."""
    # Arrange
    (test_environment / "supervisord.conf").touch()

    # Act
    result = runner.invoke(app, ["start-local"])

    # Assert
    assert result.exit_code != 0
    mock_check_postgres.assert_called_once()
    mock_check_activemq.assert_called_once()
    mock_run.assert_not_called()
    assert "Error: One or more background services are not available. Aborting." in result.stdout

@patch('subprocess.run')
def test_stop_local(mock_run, test_environment):
    """Test the stop-local command."""
    # Arrange
    (test_environment / "supervisord.conf").touch()

    # Act
    result = runner.invoke(app, ["stop-local"])

    # Assert
    assert result.exit_code == 0
    mock_run.assert_called_once_with(["supervisorctl", "-c", "supervisord.conf", "stop", "all"])
    assert "--- Stopping local supervisord services ---" in result.stdout


@patch('swf_testbed_cli.main._check_activemq_connection')
@patch('swf_testbed_cli.main._check_postgres_connection')
@patch('swf_testbed_cli.main._check_supervisord_running', return_value=True)
@patch('subprocess.run')
def test_status_local(mock_run, mock_check_supervisord, mock_check_postgres, mock_check_activemq, test_environment):
    """Test the status-local command."""
    # Arrange
    (test_environment / "supervisord.conf").touch()

    # Act
    result = runner.invoke(app, ["status-local"])

    # Assert
    assert result.exit_code == 0
    mock_check_supervisord.assert_called_once()
    mock_check_postgres.assert_called_once()
    mock_check_activemq.assert_called_once()
    mock_run.assert_called_once_with(["supervisorctl", "-c", "supervisord.conf", "status"])
    assert "--- Local services status ---" in result.stdout
