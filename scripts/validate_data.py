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
    from pydantic import BaseModel, Field, ValidationError, validator
except ImportError:
    print("ERROR: pydantic is not installed. Please run: pip install pydantic")
    sys.exit(1)


class Compound(BaseModel):
    """Schema for compounds.csv"""

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    synonyms: Optional[str] = None
    class_: Optional[str] = Field(None, alias='class')
    route: Optional[str] = None
    dose: Optional[str] = None
    qt_risk: Optional[str] = None
    notes: Optional[str] = None
    examine_slug: Optional[str] = None
    external_links: Optional[str] = None

    @validator('external_links', pre=True)
    def validate_external_links(cls, v: Optional[str]) -> Optional[str]:
        if v and v.strip():
            if not isinstance(v, str):
                raise TypeError("external_links must be a string")
            try:
                json.loads(v)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON: {exc}")
        return v


class Interaction(BaseModel):
    """Schema for interactions.csv"""

    compound_a: str = Field(..., min_length=1)
    compound_b: str = Field(..., min_length=1)
    severity: str = Field(..., pattern=r'^(Severe|Moderate|Mild|None)$')
    evidence_grade: Optional[str] = None
    mechanism: str = Field(..., min_length=1)
    effect: str = Field(..., min_length=1)
    risk_level: str = Field(..., pattern=r'^(Low|Moderate|High|Unknown)$')
    mechanism_tags: Optional[str] = None
    source_ids: Optional[str] = None
    action: Optional[str] = None

    @validator('evidence_grade', pre=True)
    def validate_evidence_grade(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if isinstance(v, str) and v.strip():
            allowed = {"A", "B", "C", "D"}
            if v.upper() not in allowed:
                raise ValueError(f"evidence_grade must be one of {sorted(allowed)}")
            return v.upper()
        return None


class Source(BaseModel):
    """Schema for sources data"""
    id: str = Field(..., min_length=1)
    title: Optional[str] = None
    citation: str = Field(..., min_length=1)
    identifier: Optional[str] = None
    date: Optional[str] = None
    extra: Optional[str] = None

    @validator('extra', pre=True)
    def validate_extra(cls, v: Optional[str]) -> Optional[str]:
        if v and v.strip():
            try:
                json.loads(v)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON: {exc}")
        return v


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
        self.validate_csv('interactions.csv', Interaction, self.interactions, None)
        self.validate_csv('sources.csv', Source, self.sources, 'id')

        # Validate JSON files (but skip if not critical)
        self.validate_json_optional('compounds.json', 'id')
        self.validate_json_optional('interactions.json', 'id')
        self.validate_json_optional('sources.json', 'id')

        # Check cross-file consistency
        self.check_referential_integrity()

        # Print results
        self.print_results()

        return len(self.errors) == 0

    def validate_csv(self, filename: str, model: type[BaseModel], storage: Dict, id_field: Optional[str]) -> None:
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
                    if id_field:
                        row_id = row.get(id_field)

                        # Check for duplicates
                        if row_id in seen_ids:
                            self.errors.append(
                                f"{filename}:row {row_num}: Duplicate {id_field} '{row_id}'"
                            )
                        else:
                            seen_ids.add(row_id)
                            storage[row_id] = row
                    else:
                        storage[row_num] = row

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

    def validate_json_optional(self, filename: str, id_field: str) -> None:
        """Validate JSON file structure (optional - warnings only for missing ID field)"""
        filepath = self.data_dir / filename
        print(f"Validating {filename}...")

        if not filepath.exists():
            self.warnings.append(f"{filename}: File not found")
            return

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, list):
                self.warnings.append(f"{filename}: Root element should be an array")
                return

            if not data:
                self.warnings.append(f"{filename}: File contains empty array")
                return

            # Check for duplicates (only if id field exists)
            seen_ids: Set[str] = set()
            has_id_field = False
            for idx, item in enumerate(data):
                if not isinstance(item, dict):
                    self.warnings.append(f"{filename}:item {idx}: Should be an object")
                    continue

                if id_field in item:
                    has_id_field = True
                    item_id = item[id_field]
                    if item_id in seen_ids:
                        self.warnings.append(
                            f"{filename}:item {idx}: Duplicate {id_field} '{item_id}'"
                        )
                    else:
                        seen_ids.add(item_id)

            if has_id_field:
                print(f"  ✓ Validated {len(seen_ids)} unique records")
            else:
                print(f"  ✓ Validated {len(data)} records (no id field)")

        except json.JSONDecodeError as e:
            self.warnings.append(f"{filename}: Invalid JSON - {str(e)}")
        except Exception as e:
            self.warnings.append(f"{filename}: Error reading file - {str(e)}")

    def check_referential_integrity(self) -> None:
        """Check cross-file references are valid"""
        print("\nChecking referential integrity...")

        # Check interactions reference valid compounds
        for row_key, interaction in self.interactions.items():
            row_label = row_key if isinstance(row_key, int) else f"id={row_key}"
            compound_a = (interaction.get('compound_a') or '').strip()
            compound_b = (interaction.get('compound_b') or '').strip()

            if compound_a and compound_a not in self.compounds:
                self.errors.append(
                    f"interactions.csv:row {row_label}: References unknown compound_a '{compound_a}'"
                )

            if compound_b and compound_b not in self.compounds:
                self.errors.append(
                    f"interactions.csv:row {row_label}: References unknown compound_b '{compound_b}'"
                )

            # Check source references
            source_ids = interaction.get('source_ids', '')
            if source_ids:
                for source_id in source_ids.split(';'):
                    source_id = source_id.strip()
                    if source_id and source_id not in self.sources:
                        self.warnings.append(
                            f"interactions.csv:row {row_label}: References unknown source_id '{source_id}'"
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
