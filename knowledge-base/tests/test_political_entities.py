"""
Tests for the Party model in political_entities.py
"""

import numpy as np
import pytest

from model.political_entities import Party


class TestParty:
    """Tests for the Party model."""

    def test_party_creation_basic(self):
        """Test creating a Party with required fields."""
        party = Party(abbreviation="S", full_name="Socialdemokraterna")

        assert party.abbreviation == "S"
        assert party.full_name == "Socialdemokraterna"
        assert party.embedding is None

    def test_party_creation_with_embedding(self):
        """Test creating a Party with an embedding."""
        embedding = np.array([0.1, 0.2, 0.3])
        party = Party(abbreviation="M", full_name="Moderaterna", embedding=embedding)

        assert party.abbreviation == "M"
        assert party.full_name == "Moderaterna"
        assert np.array_equal(party.embedding, embedding)

    def test_party_validation_empty_abbreviation(self):
        """Test that empty abbreviation is not allowed."""
        with pytest.raises(ValueError):
            Party(abbreviation="", full_name="Socialdemokraterna")

    def test_party_validation_empty_full_name(self):
        """Test that empty full_name is not allowed."""
        with pytest.raises(ValueError):
            Party(abbreviation="S", full_name="")

    def test_party_equality(self):
        """Test Party equality comparison."""
        party1 = Party(abbreviation="C", full_name="Centerpartiet")
        party2 = Party(abbreviation="C", full_name="Centerpartiet")
        party3 = Party(abbreviation="M", full_name="Moderaterna")

        assert party1 == party2
        assert party1 != party3

    def test_party_repr(self):
        """Test Party string representation."""
        party = Party(abbreviation="V", full_name="Vänsterpartiet")
        repr_str = repr(party)

        assert "V" in repr_str
        assert "Vänsterpartiet" in repr_str

    def test_party_with_none_embedding(self):
        """Test that None embedding is handled correctly."""
        party = Party(abbreviation="KD", full_name="Kristdemokraterna", embedding=None)

        assert party.embedding is None

    def test_party_with_large_embedding(self):
        """Test Party with a realistic-sized embedding (1536 dimensions like OpenAI)."""
        embedding = np.random.rand(1536)
        party = Party(
            abbreviation="MP", full_name="Miljöpartiet de gröna", embedding=embedding
        )

        assert party.embedding.shape == (1536,)
        assert np.array_equal(party.embedding, embedding)

    def test_party_config_arbitrary_types(self):
        """Test that the arbitrary_types_allowed config works for numpy arrays."""
        # This should not raise an error due to the Config class
        embedding = np.array([1.0, 2.0, 3.0])
        party = Party(
            abbreviation="SD", full_name="Sverigedemokraterna", embedding=embedding
        )

        assert isinstance(party.embedding, np.ndarray)
