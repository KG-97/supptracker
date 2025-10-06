#!/usr/bin/env python3
"""
Data Validation Script for SuppTracker

Validates data integrity across CSV and JSON files in the data/ directory:
- Schema validation using Pydantic models
- Duplicate detection
- Cross-file consistency checks
- Required field validation
- JSON structure validation

Usage:
    python scripts/validate_data.py

Returns exit code 0 if all validations pass, 1 if any validation fails.
"""

import sys
import json
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict

try:
    from pydantic import BaseModel, Field, field_validator, ValidationError, ConfigDict
except ImportError:
    print("ERROR: pydantic is not installed. Please run: pip install pydantic")
    sys.exit(1)


class Compound(BaseModel):
    """Schema for compounds data"""
    model_config = ConfigDict(populate_by_name=True)
    
    id: str = Field(..., min_length=1, alias='compound_id')
    name: str = Field(..., min_length=1)
    synonyms: Optional[str] = None
    class_: Optional[str] = Field(None, alias='class')
    description: Optional[str] = None
    externalIds: Optional[str] = None
    referenceUrls: Optional[str] = None

    @field_validator('externalIds', 'referenceUrls')
    @classmethod
    def validate_json_fields(cls, v):
        if v and v.strip():
            try:
                json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {e}")
        return v


class Interaction(BaseModel):
    """Schema for interactions data"""
    model_config = ConfigDict(populate_by_name=True)
    
    id: str = Field(..., min_length=1, alias='interaction_id')
    a: str = Field(..., min_length=1, alias='compound1_id')
    b: str = Field(..., min_length=1, alias='compound2_id')
    severity: str = Field(..., pattern=r'^(Severe|Moderate|Mild)$')
    description: Optional[str] = None
    recommendation: Optional[str] = None
    risk_score: Optional[float] = Field(None, ge=0, le=10)
    sources: Optional[str] = Field(None, alias='source_ids')


class Source(BaseModel):
    """Schema for sources data"""
    model_config = ConfigDict(populate_by_name=True)
    
    id: str = Field(..., min_length=1, alias='source_id')
    title: str = Field(..., min_length=1)
    url: Optional[str] = None
    publication_date: Optional[str] = None
    authors: Optional[str] = None


class DataValidator:
    """Main data validation class"""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.compounds: Dict[str, Dict[str, Any]] = {}
        self.interactions: Dict[str, Dict[str, Any]] = {}
        self.sources: Dict[str, Dict[str, Any]] = {}

    def validate_all(self) -> bool:
        """Run all validation checks"""
        print("\n" + "="*60)
        print("Starting Data Validation for SuppTracker")
        print("="*60 + "\n")

        # Validate CSV files
        self.validate_csv('compounds.csv', Compound, self.compounds, 'id')
        self.validate_csv('interactions.csv', Interaction, self.interactions, 'id')
        self.validate_csv('sources.csv', Source, self.sources, 'id')

        # Validate JSON files
        self.validate_json('compounds.json', 'id')
        self.validate_json('interactions.json', 'id')
        self.validate_json('sources.json', 'id')

        # Check cross-file consistency
        self.check_referential_integrity()

        # Print results
        self.print_results()

        return len(self.errors) == 0

    def validate_csv(self, filename: str, model: type[BaseModel], storage: Dict, id_field: str) -> None:
        """Validate a CSV file against a Pydantic model"""
        filepath = self.data_dir / filename
        print(f"Validating {filename}...")

        if not filepath.exists():
            self.errors.append(f"{filename}: File not found")
            return

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if not rows:
                self.warnings.append(f"{filename}: File is empty")
                return

            # Check for duplicates
            seen_ids: Set[str] = set()

            for row_num, row in enumerate(rows, start=2):  # Start at 2 (header is 1)
                # Validate schema
                try:
                    validated = model(**row)
                    row_id = row.get(id_field)

                    # Check for duplicates
                    if row_id in seen_ids:
                        self.errors.append(
                            f"{filename}:row {row_num}: Duplicate {id_field} '{row_id}'"
                        )
                    else:
                        seen_ids.add(row_id)
                        storage[row_id] = row

                except ValidationError as e:
                    for error in e.errors():
                        field = '.'.join(str(x) for x in error['loc'])
                        msg = error['msg']
                        self.errors.append(
                            f"{filename}:row {row_num}:{field}: {msg}"
                        )

            print(f"  ✓ Validated {len(seen_ids)} unique records")

        except Exception as e:
            self.errors.append(f"{filename}: Error reading file - {str(e)}")

    def validate_json(self, filename: str, id_field: str) -> None:
        """Validate JSON file structure and check for duplicates"""
        filepath = self.data_dir / filename
        print(f"Validating {filename}...")

        if not filepath.exists():
            self.errors.append(f"{filename}: File not found")
            return

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, list):
                self.errors.append(f"{filename}: Root element must be an array")
                return

            if not data:
                self.warnings.append(f"{filename}: File contains empty array")
                return

            # Check for duplicates
            seen_ids: Set[str] = set()
            for idx, item in enumerate(data):
                if not isinstance(item, dict):
                    self.errors.append(f"{filename}:item {idx}: Must be an object")
                    continue

                if id_field not in item:
                    self.errors.append(f"{filename}:item {idx}: Missing '{id_field}' field")
                    continue

                item_id = item[id_field]
                if item_id in seen_ids:
                    self.errors.append(
                        f"{filename}:item {idx}: Duplicate {id_field} '{item_id}'"
                    )
                else:
                    seen_ids.add(item_id)

            print(f"  ✓ Validated {len(seen_ids)} unique records")

        except json.JSONDecodeError as e:
            self.errors.append(f"{filename}: Invalid JSON - {str(e)}")
        except Exception as e:
            self.errors.append(f"{filename}: Error reading file - {str(e)}")

    def check_referential_integrity(self) -> None:
        """Check cross-file references are valid"""
        print("\nChecking referential integrity...")

        # Check interactions reference valid compounds
        for interaction_id, interaction in self.interactions.items():
            compound1_id = interaction.get('a')
            compound2_id = interaction.get('b')

            if compound1_id and compound1_id not in self.compounds:
                self.errors.append(
                    f"interactions.csv:{interaction_id}: References unknown compound 'a' (compound1_id) '{compound1_id}'"
                )

            if compound2_id and compound2_id not in self.compounds:
                self.errors.append(
                    f"interactions.csv:{interaction_id}: References unknown compound 'b' (compound2_id) '{compound2_id}'"
                )

            # Check source references
            source_ids = interaction.get('sources', '')
            if source_ids:
                for source_id in source_ids.split(';'):
                    source_id = source_id.strip()
                    if source_id and source_id not in self.sources:
                        self.warnings.append(
                            f"interactions.csv:{interaction_id}: References unknown source_id '{source_id}'"
                        )

        print("  ✓ Referential integrity checked")

    def print_results(self) -> None:
        """Print validation results"""
        print("\n" + "="*60)
        print("Validation Results")
        print("="*60 + "\n")

        if self.warnings:
            print(f"⚠️  {len(self.warnings)} Warning(s):\n")
            for warning in self.warnings:
                print(f"  • {warning}")
            print()

        if self.errors:
            print(f"❌ {len(self.errors)} Error(s):\n")
            for error in self.errors:
                print(f"  • {error}")
            print()
            print("VALIDATION FAILED\n")
        else:
            print("✅ All validations passed!\n")


def main():
    """Main entry point"""
    # Determine data directory
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    data_dir = repo_root / 'data'

    if not data_dir.exists():
        print(f"ERROR: Data directory not found: {data_dir}")
        sys.exit(1)

    # Run validation
    validator = DataValidator(data_dir)
    success = validator.validate_all()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
