"""
Tests for party-related methods in SchemaManager
"""

from unittest.mock import MagicMock, patch

import pytest

from graph import SchemaManager
from model.political_entities import Party


@pytest.fixture
def mock_driver():
    """Create a mock Neo4j driver."""
    return MagicMock()


@pytest.fixture
def mock_session():
    """Create a mock Neo4j session."""
    return MagicMock()


@pytest.fixture
def schema_manager(mock_driver):
    """Create a SchemaManager with mocked driver."""
    with patch.object(
        SchemaManager, "__init__", lambda self, uri, user, password: None
    ):
        manager = SchemaManager.__new__(SchemaManager)
        manager.driver = mock_driver
        return manager


@pytest.fixture
def sample_parties():
    """Create sample Party objects for testing."""
    return [
        Party(abbreviation="C", full_name="Centerpartiet"),
        Party(abbreviation="M", full_name="Moderaterna"),
        Party(abbreviation="S", full_name="Socialdemokraterna"),
    ]


class TestSchemaManagerParties:
    """Tests for party-related methods in SchemaManager."""

    def test_upsert_party_success(self, schema_manager, mock_session):
        """Test successful insertion of a single party."""
        party = Party(abbreviation="V", full_name="Vänsterpartiet")

        schema_manager.driver.session.return_value.__enter__.return_value = mock_session

        schema_manager.upsert_party(party)

        # Verify session was used correctly
        schema_manager.driver.session.assert_called_once()

        # Verify the correct Cypher query was executed
        mock_session.run.assert_called_once()
        call_args = mock_session.run.call_args

        # Check the query structure
        query = call_args[0][0]
        assert "MERGE (p:Party {abbreviation: $abbreviation})" in query
        assert "SET p.full_name = $full_name" in query

        # Check the parameters
        params = call_args[1]
        assert params["abbreviation"] == "V"
        assert params["full_name"] == "Vänsterpartiet"

    def test_upsert_parties_bulk_success(
        self, schema_manager, mock_session, sample_parties
    ):
        """Test successful bulk insertion of multiple parties."""
        schema_manager.driver.session.return_value.__enter__.return_value = mock_session

        schema_manager.upsert_parties(sample_parties)

        # Verify session was used correctly
        schema_manager.driver.session.assert_called_once()

        # Verify the correct Cypher query was executed
        mock_session.run.assert_called_once()
        call_args = mock_session.run.call_args

        # Check the query structure
        query = call_args[0][0]
        assert "UNWIND $parties AS party" in query
        assert "MERGE (p:Party {abbreviation: party.abbreviation})" in query
        assert "SET p.full_name = party.full_name" in query

        # Check the parameters - should be a list of party data
        params = call_args[1]
        parties_data = params["parties"]
        assert len(parties_data) == 3

        # Verify specific party data
        party_abbrevs = [p["abbreviation"] for p in parties_data]
        assert "C" in party_abbrevs
        assert "M" in party_abbrevs
        assert "S" in party_abbrevs

        centerpartiet_data = next(p for p in parties_data if p["abbreviation"] == "C")
        assert centerpartiet_data["full_name"] == "Centerpartiet"

    def test_upsert_parties_empty_list(self, schema_manager, mock_session):
        """Test bulk upsert with empty list."""
        schema_manager.driver.session.return_value.__enter__.return_value = mock_session

        schema_manager.upsert_parties([])

        # Should still execute the query with empty data
        schema_manager.driver.session.assert_called_once()
        mock_session.run.assert_called_once()

        call_args = mock_session.run.call_args
        params = call_args[1]
        assert params["parties"] == []

    def test_link_documents_to_parties_success(self, schema_manager, mock_session):
        """Test successful linking of documents to parties."""
        schema_manager.driver.session.return_value.__enter__.return_value = mock_session

        schema_manager.link_documents_to_parties()

        # Verify session was used correctly
        schema_manager.driver.session.assert_called_once()

        # Should make multiple calls - one for each party mapping
        expected_folder_mappings = {
            "centerpartiet": "C",
            "liberalerna": "L",
            "miljopartiet": "MP",
            "moderaterna": "M",
            "socialdemokraterna": "S",
            "sverigedemokraterna": "SD",
            "vansterpartiet": "V",
            "kristdemokraterna": "KD",
        }

        # Verify the number of calls matches the number of mappings
        assert mock_session.run.call_count == len(expected_folder_mappings)

        # Verify each mapping was processed
        all_calls = mock_session.run.call_args_list

        for call_obj in all_calls:
            query = call_obj[0][0]
            params = call_obj[1]

            # Check query structure
            assert "MATCH (d:Document)" in query
            assert "WHERE d.path CONTAINS $folder_pattern" in query
            assert "MATCH (p:Party {abbreviation: $party_abbr})" in query
            assert "MERGE (p)-[:AUTHORED]->(d)" in query

            # Verify folder pattern format
            folder_pattern = params["folder_pattern"]
            party_abbr = params["party_abbr"]

            assert folder_pattern.startswith("/documents/")
            assert folder_pattern.endswith("/")
            assert party_abbr in expected_folder_mappings.values()

    def test_link_documents_to_parties_specific_mappings(
        self, schema_manager, mock_session
    ):
        """Test that specific folder-to-party mappings are correct."""
        schema_manager.driver.session.return_value.__enter__.return_value = mock_session

        schema_manager.link_documents_to_parties()

        # Extract all the parameters used in the calls
        all_calls = mock_session.run.call_args_list
        call_params = [call_obj[1] for call_obj in all_calls]

        # Verify specific mappings
        centerpartiet_call = next(
            params for params in call_params if params["party_abbr"] == "C"
        )
        assert centerpartiet_call["folder_pattern"] == "/documents/centerpartiet/"

        moderaterna_call = next(
            params for params in call_params if params["party_abbr"] == "M"
        )
        assert moderaterna_call["folder_pattern"] == "/documents/moderaterna/"

        miljopartiet_call = next(
            params for params in call_params if params["party_abbr"] == "MP"
        )
        assert miljopartiet_call["folder_pattern"] == "/documents/miljopartiet/"

    def test_upsert_party_special_characters(self, schema_manager, mock_session):
        """Test party with special characters in name."""
        party = Party(abbreviation="MP", full_name="Miljöpartiet de gröna")

        schema_manager.driver.session.return_value.__enter__.return_value = mock_session

        schema_manager.upsert_party(party)

        call_args = mock_session.run.call_args
        params = call_args[1]
        assert params["full_name"] == "Miljöpartiet de gröna"

    def test_schema_manager_driver_error_handling(self, schema_manager, mock_session):
        """Test that database errors are properly propagated."""
        party = Party(abbreviation="KD", full_name="Kristdemokraterna")

        # Mock a database error
        mock_session.run.side_effect = Exception("Database connection failed")
        schema_manager.driver.session.return_value.__enter__.return_value = mock_session

        # Should let the exception propagate (fail-fast principle)
        with pytest.raises(Exception, match="Database connection failed"):
            schema_manager.upsert_party(party)

    def test_upsert_parties_single_party_in_list(self, schema_manager, mock_session):
        """Test bulk upsert with single party in list."""
        party = Party(abbreviation="FP", full_name="Folkpartiet liberalerna")

        schema_manager.driver.session.return_value.__enter__.return_value = mock_session

        schema_manager.upsert_parties([party])

        call_args = mock_session.run.call_args
        params = call_args[1]
        parties_data = params["parties"]

        assert len(parties_data) == 1
        assert parties_data[0]["abbreviation"] == "FP"
        assert parties_data[0]["full_name"] == "Folkpartiet liberalerna"
