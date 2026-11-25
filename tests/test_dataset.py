"""
tests/test_dataset.py - Tests for dataset generation and idempotency
"""
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_dataset_generation_and_idempotency(tmp_path, monkeypatch):
    """Test generating all dataset files, validating them, and running twice without duplicates."""
    import config
    from scripts import generate_dataset

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "PROPERTIES_CSV", data_dir / "properties.csv")
    monkeypatch.setattr(config, "KNOWLEDGE_TXT", data_dir / "company_knowledge.txt")
    monkeypatch.setattr(config, "SAMPLE_CUSTOMERS_CSV", data_dir / "sample_customers.csv")
    monkeypatch.setattr(config, "DATABASE_PATH", data_dir / "test_dreamhome.db")

    # First run creates everything
    assert generate_dataset.generate_all(load_db=True) is True
    assert config.PROPERTIES_CSV.exists()
    assert config.KNOWLEDGE_TXT.exists()
    assert config.SAMPLE_CUSTOMERS_CSV.exists()
    assert config.DATABASE_PATH.exists()

    with open(config.PROPERTIES_CSV, encoding="utf-8") as f:
        props = list(csv.DictReader(f))
    assert len(props) >= 20
    prop_types = {p["property_type"] for p in props}
    assert {"Apartment", "Independent House", "Villa"}.issubset(prop_types)

    from backend import database as db
    first_customers = len(db.list_customers())
    first_leads = len(db.list_leads())
    assert first_customers >= 5
    assert first_leads >= 5

    # Second run must not create duplicate rows
    assert generate_dataset.generate_all(load_db=True) is True
    assert len(db.list_customers()) == first_customers
    assert len(db.list_leads()) == first_leads
