import csv
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api.risk_api as app_module


def test_resolve_compound(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "COMPOUNDS",
        {"caffeine": {"id": "caffeine", "name": "Caffeine", "synonyms": ["coffee"]}},
    )
    app_module.build_compound_indexes()
    assert app_module.resolve_compound("coffee") == "caffeine"
    assert app_module.resolve_compound("unknown") is None


def test_resolve_compound_alias(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "COMPOUNDS",
        {
            "caffeine": {
                "id": "caffeine",
                "name": "Caffeine",
                "synonyms": [],
                "aliases": ["Guarana"],
            }
        },
    )
    app_module.build_compound_indexes()
    assert app_module.resolve_compound("Guarana") == "caffeine"
    assert app_module.resolve_compound("guarana") == "caffeine"
    assert app_module.resolve_compound("CAFFEINE") == "caffeine"


def test_resolve_compound_with_comma_synonyms(tmp_path, monkeypatch):
    csv_content = (
        "id,name,synonyms,externalIds,referenceUrls\n"
        "st_johns_wort,St. John's Wort,\"St. John's Wort, Hypericum\",,\n"
    )
    (tmp_path / "compounds.csv").write_text(csv_content)

    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    compounds = app_module.load_compounds()
    monkeypatch.setattr(app_module, "COMPOUNDS", compounds)
    app_module.build_compound_indexes()

    assert compounds["st_johns_wort"]["synonyms"] == ["St. John's Wort", "Hypericum"]
    assert app_module.resolve_compound("hypericum") == "st_johns_wort"


def test_load_compounds_includes_external_metadata(tmp_path, monkeypatch):
    csv_content = (
        "id,name,synonyms,externalIds,referenceUrls\n"
        'caffeine,Caffeine,coffee;tea,"{""pubchem"":""2519""}","{""pubchem"":""https://pubchem.ncbi.nlm.nih.gov/compound/2519""}"\n'
    )
    (tmp_path / "compounds.csv").write_text(csv_content)

    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    compounds = app_module.load_compounds()

    assert compounds["caffeine"]["externalIds"] == {"pubchem": "2519"}
    assert compounds["caffeine"]["referenceUrls"] == {
        "pubchem": "https://pubchem.ncbi.nlm.nih.gov/compound/2519"
    }


def test_load_compounds_parses_external_links(tmp_path, monkeypatch):
    csv_content = (
        "id,name,synonyms,external_links\n"
        'creatine,Creatine,creatine;monohydrate,"[{""label"":""Examine"",""url"":""https://example.com/creatine""}]"\n'
    )
    (tmp_path / "compounds.csv").write_text(csv_content, encoding="utf-8")

    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    compounds = app_module.load_compounds()

    record = compounds["creatine"]
    assert record["externalLinks"] == [
        {"label": "Examine", "url": "https://example.com/creatine"}
    ]
    assert "external_links" not in record


def test_parse_mapping_handles_iterables():
    import api.risk_api as app_module

    payload = [
        {"pubchem": 2519},
        ("drugbank", "DB01234"),
        ["rxnorm", 123],
        "wikidata=Q271",
        "chembl:CHEMBL25",
        ["ignored"],
        {"empty": ""},
    ]

    result = app_module._parse_mapping(payload)

    assert result == {
        "pubchem": "2519",
        "drugbank": "DB01234",
        "rxnorm": "123",
        "wikidata": "Q271",
        "chembl": "CHEMBL25",
    }


def test_parse_mapping_handles_json_string_sequences():
    import api.risk_api as app_module

    payload = json.dumps(
        [
            ["pubchem", 2519],
            {"drugbank": "DB01234"},
            ["rxnorm", "123", "ignored"],
        ]
    )

    result = app_module._parse_mapping(payload)

    assert result == {
        "pubchem": "2519",
        "drugbank": "DB01234",
        "rxnorm": "123",
    }
def test_resolve_compound_matches_aliases_and_external_ids(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "COMPOUNDS",
        {
            "caffeine": {
                "id": "caffeine",
                "name": "Caffeine",
                "synonyms": ["coffee"],
                "aliases": ["1,3,7-trimethylxanthine"],
                "externalIds": {"pubchem": "2519"},
            }
        },
    )

    assert app_module.resolve_compound("caffeine") == "caffeine"
    assert app_module.resolve_compound("Caffeine") == "caffeine"
    assert app_module.resolve_compound("coffee") == "caffeine"
    assert app_module.resolve_compound("1,3,7-TRIMETHYLXANTHINE") == "caffeine"
    assert app_module.resolve_compound("2519") == "caffeine"


def test_compute_risk_returns_float():
    inter = {"severity": "Mild", "evidence": "C", "mechanism": []}
    score = app_module.compute_risk(inter)
    assert isinstance(score, float)


def test_loaders_handle_missing_files(tmp_path, monkeypatch):
    app_module.reset_health_state()
    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))

    assert app_module.load_compounds() == {}
    assert app_module.load_interactions() == []
    assert app_module.load_sources() == {}

    health = app_module.get_health_state()
    assert health["status"] == "degraded"
    sources = {issue["source"] for issue in health["issues"]}
    assert {"compounds.csv", "interactions.csv", "sources.csv"}.issubset(sources)
    app_module.reset_health_state()


def test_load_compounds_merges_multiple_sources(tmp_path, monkeypatch):
    fieldnames = ["id", "name", "synonyms", "aliases", "externalIds", "referenceUrls"]
    csv_path = tmp_path / "compounds.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "id": "creatine",
                "name": "Creatine",
                "synonyms": "creatine monohydrate",
                "aliases": "Creapure",
                "externalIds": json.dumps({"rxnorm": "123"}),
                "referenceUrls": "",
            }
        )

    json_payload = [
        {
            "id": "creatine",
            "aliases": ["Cr", "Creapure"],
            "externalIds": {"wikidata": "Q173354"},
            "referenceUrls": {"wikipedia": "https://example.com/creatine"},
        },
        {
            "id": "magnesium",
            "name": "Magnesium",
            "synonyms": ["Mg"],
            "externalIds": {"pubchem": "123"},
            "referenceUrls": {"nih": "https://example.com/magnesium"},
        },
    ]
    (tmp_path / "compounds.json").write_text(json.dumps(json_payload), encoding="utf-8")

    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    compounds = app_module.load_compounds()

    assert set(compounds.keys()) == {"creatine", "magnesium"}
    assert compounds["creatine"]["externalIds"] == {"rxnorm": "123", "wikidata": "Q173354"}
    assert "creatine monohydrate" in compounds["creatine"]["synonyms"]
    assert compounds["creatine"]["aliases"] == ["Creapure", "Cr"]
    assert compounds["magnesium"]["referenceUrls"]["nih"] == "https://example.com/magnesium"
    assert compounds["magnesium"].get("aliases", []) == []


def test_load_interactions_merges_duplicates(tmp_path, monkeypatch):
    fieldnames = [
        "id",
        "a",
        "b",
        "bidirectional",
        "mechanism",
        "severity",
        "evidence",
        "effect",
        "action",
        "sources",
    ]
    csv_path = tmp_path / "interactions.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "id": "caf-asp",
                "a": "caffeine",
                "b": "aspirin",
                "bidirectional": "false",
                "mechanism": "pharmacodynamic",
                "severity": "Moderate",
                "evidence": "B",
                "effect": "Increased side effects",
                "action": "Monitor",
                "sources": "source_csv",
            }
        )

    json_payload = [
        {
            "a": "caffeine",
            "b": "aspirin",
            "bidirectional": True,
            "severity": "Moderate",
            "evidence": "B",
            "effect": "Increased side effects",
            "sources": ["source_json"],
        },
        {
            "a": "creatine",
            "b": "magnesium",
            "severity": "Low",
            "evidence": "C",
            "effect": "Synergistic support",
            "sources": ["stack_source"],
        },
    ]
    (tmp_path / "interactions.json").write_text(json.dumps(json_payload), encoding="utf-8")

    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    interactions = app_module.load_interactions()

    assert len(interactions) == 2
    merged = next(item for item in interactions if {item["a"], item["b"]} == {"caffeine", "aspirin"})
    assert set(merged["sources"]) == {"source_csv", "source_json"}
    assert merged["bidirectional"] is True


def test_load_sources_merges_entries(tmp_path, monkeypatch):
    fieldnames = ["id", "citation", "url", "pmid", "doi", "date"]
    csv_path = tmp_path / "sources.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "id": "src1",
                "citation": "Original citation",
                "url": "",
                "pmid": "111",
                "doi": "",
                "date": "2020-01-01",
            }
        )

    json_payload = [
        {"id": "src1", "url": "https://example.com"},
        {"id": "src2", "citation": "Another source"},
    ]
    (tmp_path / "sources.json").write_text(json.dumps(json_payload), encoding="utf-8")

    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    sources = app_module.load_sources()

    assert set(sources.keys()) == {"src1", "src2"}
    assert sources["src1"]["url"] == "https://example.com"
    assert sources["src1"]["citation"] == "Original citation"
    assert sources["src2"]["citation"] == "Another source"

