"""
Tests for party processing functionality in main.py
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from graph import SchemaManager
from main import process_party_entities


@pytest.fixture
def mock_schema_manager():
    """Create a mock SchemaManager for testing."""
    mock_manager = MagicMock(spec=SchemaManager)
    return mock_manager


@pytest.fixture
def sample_parties_json():
    """Create a temporary parties.json file for testing."""
    parties_data = {
        "description": "Test parties mapping",
        "extractedAt": "2025-01-01T00:00:00.000Z",
        "totalParties": 4,
        "source": "Test data",
        "parties": {
            "C": "Centerpartiet",
            "M": "Moderaterna",
            "S": "Socialdemokraterna",
            "-": "Partilös",  # Should be skipped
            "SD": "Sverigedemokraterna",
        },
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(parties_data, f)
        return Path(f.name)


class TestProcessPartyEntities:
    """Tests for the process_party_entities function."""

    def test_process_party_entities_success(
        self, mock_schema_manager, sample_parties_json
    ):
        """Test successful processing of party entities."""
        # Read the actual JSON data from the temp file
        with open(sample_parties_json) as f:
            parties_data = json.load(f)

        with patch("main.Path") as mock_path_class:
            # Mock the parties.json path
            mock_parties_path = MagicMock()
            mock_parties_path.exists.return_value = True
            mock_path_class.return_value = mock_parties_path

            # Mock json.load to return our test data
            with patch("json.load", return_value=parties_data):
                with patch("builtins.open", mock=MagicMock()):
                    process_party_entities(mock_schema_manager)

            # Verify that upsert_parties was called
            mock_schema_manager.upsert_parties.assert_called_once()

            # Verify that link_documents_to_parties was called
            mock_schema_manager.link_documents_to_parties.assert_called_once()

            # Check the parties that were passed to upsert_parties
            called_parties = mock_schema_manager.upsert_parties.call_args[0][0]
            assert len(called_parties) == 4  # Should exclude "Partilös" (-)

            # Verify specific parties
            party_abbrevs = [p.abbreviation for p in called_parties]
            assert "C" in party_abbrevs
            assert "M" in party_abbrevs
            assert "S" in party_abbrevs
            assert "SD" in party_abbrevs
            assert "-" not in party_abbrevs  # Should be excluded

    def test_process_party_entities_file_not_found(self, mock_schema_manager, caplog):
        """Test behavior when parties.json file is not found."""
        with patch("main.Path") as mock_path_class:
            mock_parties_path = MagicMock()
            mock_parties_path.exists.return_value = False
            mock_path_class.return_value = mock_parties_path

            with pytest.raises(FileNotFoundError):
                process_party_entities(mock_schema_manager)

            # Verify no database operations were performed
            mock_schema_manager.upsert_parties.assert_not_called()
            mock_schema_manager.link_documents_to_parties.assert_not_called()

            # Check that error was logged
            assert "Parties file not found" in caplog.text

    def test_process_party_entities_creates_correct_party_objects(
        self, mock_schema_manager, sample_parties_json
    ):
        """Test that correct Party objects are created from JSON data."""
        # Read the actual JSON data from the temp file
        with open(sample_parties_json) as f:
            parties_data = json.load(f)

        with patch("main.Path") as mock_path_class:
            mock_parties_path = MagicMock()
            mock_parties_path.exists.return_value = True
            mock_path_class.return_value = mock_parties_path

            with patch("json.load", return_value=parties_data):
                with patch("builtins.open", mock=MagicMock()):
                    process_party_entities(mock_schema_manager)

            called_parties = mock_schema_manager.upsert_parties.call_args[0][0]

            # Find specific party and verify attributes
            centerpartiet = next(p for p in called_parties if p.abbreviation == "C")
            assert centerpartiet.full_name == "Centerpartiet"
            assert centerpartiet.embedding is None

            moderaterna = next(p for p in called_parties if p.abbreviation == "M")
            assert moderaterna.full_name == "Moderaterna"

    def test_process_party_entities_empty_parties_dict(self, mock_schema_manager):
        """Test behavior with empty parties dictionary."""
        empty_parties_data = {"description": "Empty parties", "parties": {}}

        with patch("main.Path") as mock_path_class:
            mock_parties_path = MagicMock()
            mock_parties_path.exists.return_value = True
            mock_path_class.return_value = mock_parties_path

            with patch("builtins.open", mock=MagicMock()) as mock_open:
                mock_file = MagicMock()
                mock_file.read.return_value = json.dumps(empty_parties_data)
                mock_open.return_value.__enter__.return_value = mock_file

                with patch("json.load", return_value=empty_parties_data):
                    process_party_entities(mock_schema_manager)

            # Should still call upsert_parties with empty list
            mock_schema_manager.upsert_parties.assert_called_once_with([])
            mock_schema_manager.link_documents_to_parties.assert_called_once()

    def test_process_party_entities_malformed_json(self, mock_schema_manager, caplog):
        """Test behavior with malformed JSON file."""
        with patch("main.Path") as mock_path_class:
            mock_parties_path = MagicMock()
            mock_parties_path.exists.return_value = True
            mock_path_class.return_value = mock_parties_path

            with patch("builtins.open", mock=MagicMock()) as mock_open:
                mock_file = MagicMock()
                mock_file.read.return_value = "invalid json"
                mock_open.return_value.__enter__.return_value = mock_file

                with patch(
                    "json.load", side_effect=json.JSONDecodeError("Invalid JSON", "", 0)
                ):
                    # Should let the exception propagate (fail-fast principle)
                    with pytest.raises(json.JSONDecodeError):
                        process_party_entities(mock_schema_manager)

            # No database operations should have been performed
            mock_schema_manager.upsert_parties.assert_not_called()
            mock_schema_manager.link_documents_to_parties.assert_not_called()

    @patch("main.logger")
    def test_process_party_entities_logging(
        self, mock_logger, mock_schema_manager, sample_parties_json
    ):
        """Test that appropriate log messages are generated."""
        # Read the actual JSON data from the temp file
        with open(sample_parties_json) as f:
            parties_data = json.load(f)

        with patch("main.Path") as mock_path_class:
            mock_parties_path = MagicMock()
            mock_parties_path.exists.return_value = True
            mock_path_class.return_value = mock_parties_path

            with patch("json.load", return_value=parties_data):
                with patch("builtins.open", mock=MagicMock()):
                    process_party_entities(mock_schema_manager)

            # Verify logging calls
            mock_logger.info.assert_any_call("Processing party entities...")
            mock_logger.info.assert_any_call("Created 4 party nodes")
            mock_logger.info.assert_any_call(
                "Linked parties to their authored documents"
            )
