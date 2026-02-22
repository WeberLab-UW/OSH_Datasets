"""Tests for the shared BOM parser module."""

from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest

from osh_datasets.bom_parser import (
    coalesce_cols,
    infer_quantity,
    normalize_bom_df,
    parse_bom_file,
    safe_float_str,
    safe_int_str,
)
from osh_datasets.db import (
    init_db,
    insert_bom_file_path,
    open_connection,
    transaction,
    upsert_project,
)
from osh_datasets.enrichment.bom_files import (
    _build_branch_lookup,
    _parse_repo_url,
    enrich_bom_files,
)


class TestSafeIntStr:
    """Tests for safe_int_str parsing."""

    def test_valid_int(self) -> None:
        """Should parse a plain integer string."""
        assert safe_int_str("42") == 42

    def test_float_truncated(self) -> None:
        """Should truncate a float string to int."""
        assert safe_int_str("3.7") == 3

    def test_comma_separated(self) -> None:
        """Should handle comma-formatted numbers."""
        assert safe_int_str("1,234") == 1234

    def test_whitespace(self) -> None:
        """Should strip whitespace."""
        assert safe_int_str("  10  ") == 10

    def test_none(self) -> None:
        """Should return None for None input."""
        assert safe_int_str(None) is None

    def test_empty(self) -> None:
        """Should return None for empty string."""
        assert safe_int_str("") is None

    def test_garbage(self) -> None:
        """Should return None for non-numeric strings."""
        assert safe_int_str("abc") is None


class TestSafeFloatStr:
    """Tests for safe_float_str parsing."""

    def test_valid_float(self) -> None:
        """Should parse a decimal string."""
        assert safe_float_str("3.14") == pytest.approx(3.14)

    def test_dollar_sign(self) -> None:
        """Should strip dollar signs."""
        assert safe_float_str("$12.50") == pytest.approx(12.50)

    def test_comma_separated(self) -> None:
        """Should handle comma-formatted numbers."""
        assert safe_float_str("1,234.56") == pytest.approx(1234.56)

    def test_none(self) -> None:
        """Should return None for None input."""
        assert safe_float_str(None) is None

    def test_empty(self) -> None:
        """Should return None for empty string."""
        assert safe_float_str("") is None

    def test_garbage(self) -> None:
        """Should return None for non-numeric strings."""
        assert safe_float_str("N/A") is None


class TestInferQuantity:
    """Tests for infer_quantity."""

    def test_explicit_quantity(self) -> None:
        """Should use explicit quantity when available."""
        assert infer_quantity("R1", "5") == 5

    def test_comma_separated_refs(self) -> None:
        """Should count comma-separated designators when qty missing."""
        assert infer_quantity("R1, R2, R3", None) == 3

    def test_single_ref_no_qty(self) -> None:
        """Should return 1 for single reference with no quantity."""
        assert infer_quantity("C1", None) == 1

    def test_no_ref_no_qty(self) -> None:
        """Should return None when both are missing."""
        assert infer_quantity(None, None) is None

    def test_explicit_overrides_ref_count(self) -> None:
        """Should prefer explicit quantity over ref count."""
        assert infer_quantity("R1, R2, R3", "4") == 4


class TestCoalesceCols:
    """Tests for coalesce_cols expression builder."""

    def test_first_match_wins(self) -> None:
        """Should prefer earlier columns in candidate list."""
        df = pl.DataFrame({
            "Ref": ["R1"],
            "Reference": ["R2"],
        })
        result = df.select(
            coalesce_cols(df, ("ref", "reference"), "out")
        )
        assert result["out"][0] == "R1"

    def test_skips_empty_strings(self) -> None:
        """Should skip empty strings and use next column."""
        df = pl.DataFrame({
            "Ref": [""],
            "Reference": ["R2"],
        })
        result = df.select(
            coalesce_cols(df, ("ref", "reference"), "out")
        )
        assert result["out"][0] == "R2"

    def test_no_matching_columns(self) -> None:
        """Should return null when no candidate columns exist."""
        df = pl.DataFrame({"other": ["x"]})
        result = df.select(
            coalesce_cols(df, ("ref", "reference"), "out")
        )
        assert result["out"][0] is None

    def test_case_insensitive(self) -> None:
        """Should match columns regardless of case."""
        df = pl.DataFrame({
            "REFERENCE": ["R1"],
            "VALUE": ["10k"],
        })
        result = df.select(
            coalesce_cols(df, ("reference",), "out")
        )
        assert result["out"][0] == "R1"


class TestNormalizeBomDf:
    """Tests for normalize_bom_df."""

    def test_normalizes_standard_bom(self) -> None:
        """Should map variant columns to canonical names."""
        df = pl.DataFrame({
            "Designator": ["R1", "C1"],
            "Value": ["10k", "100nF"],
            "Qty": ["2", "1"],
            "Manufacturer": ["Yageo", "Murata"],
            "MPN": ["RC0402", "GCM155"],
        })
        result = normalize_bom_df(df)
        assert "reference" in result.columns
        assert "footprint" in result.columns
        assert result.height == 2
        assert result["reference"][0] == "R1"
        assert result["part_number"][1] == "GCM155"

    def test_drops_all_null_rows(self) -> None:
        """Should drop rows where all BOM fields are null."""
        df = pl.DataFrame({
            "unrelated": ["x", "y"],
        })
        result = normalize_bom_df(df)
        assert result.is_empty()

    def test_case_insensitive_columns(self) -> None:
        """Should match all-uppercase column headers."""
        df = pl.DataFrame({
            "REFERENCE": ["R1"],
            "VALUE": ["10k"],
            "QTY": ["2"],
            "MANUFACTURER": ["Yageo"],
        })
        result = normalize_bom_df(df)
        assert result.height == 1
        assert result["reference"][0] == "R1"
        assert result["component_name"][0] == "10k"
        assert result["quantity_raw"][0] == "2"

    def test_footprint_column(self) -> None:
        """Should capture footprint data."""
        df = pl.DataFrame({
            "Reference": ["R1"],
            "Value": ["10k"],
            "Footprint": ["R_0805_2012Metric"],
        })
        result = normalize_bom_df(df)
        assert result["footprint"][0] == "R_0805_2012Metric"

    def test_ods_column_mapping(self) -> None:
        """Should map Refs and Man. P/N columns."""
        df = pl.DataFrame({
            "Refs": ["R1, R2"],
            "Value": ["10k"],
            "Num used": ["2"],
            "Supplier": ["Digi-Key"],
            "Man. P/N": ["RC0402FR"],
            "Price": ["0.05"],
        })
        result = normalize_bom_df(df)
        assert result.height == 1
        assert result["reference"][0] == "R1, R2"
        assert result["manufacturer"][0] == "Digi-Key"
        assert result["part_number"][0] == "RC0402FR"
        assert result["unit_cost_raw"][0] == "0.05"

    def test_jlcpcb_columns(self) -> None:
        """Should map JLCPCB/LCSC column names."""
        df = pl.DataFrame({
            "Designator": ["C1"],
            "Comment": ["100nF"],
            "Qty": ["1"],
            "LCSC": ["C14663"],
            "Footprint": ["C_0402"],
        })
        result = normalize_bom_df(df)
        assert result["part_number"][0] == "C14663"
        assert result["footprint"][0] == "C_0402"

    def test_digikey_columns(self) -> None:
        """Should map Digi-Key export column names."""
        df = pl.DataFrame({
            "Customer Reference": ["R1"],
            "Description": ["10k 0805 1%"],
            "Quantity": ["2"],
            "Manufacturer": ["Yageo"],
            "Digi-Key Part Number": ["311-10.0KCRCT-ND"],
            "Unit Price": ["0.10"],
        })
        result = normalize_bom_df(df)
        assert result["reference"][0] is None  # "customer reference" not mapped
        assert result["component_name"][0] == "10k 0805 1%"
        assert result["part_number"][0] == "311-10.0KCRCT-ND"
        assert result["unit_cost_raw"][0] == "0.10"


class TestParseBomFile:
    """Tests for parse_bom_file."""

    def test_csv(self) -> None:
        """Should parse a CSV BOM file."""
        csv_data = (
            b"Reference,Value,Qty,Manufacturer,MPN\n"
            b"R1,10k,2,Yageo,RC0402\n"
            b"C1,100nF,1,Murata,GCM155\n"
        )
        result = parse_bom_file(csv_data, "bom.csv")
        assert result is not None
        assert result.height == 2

    def test_tsv(self) -> None:
        """Should parse a TSV BOM file."""
        tsv_data = (
            b"Reference\tValue\tQty\n"
            b"R1\t10k\t2\n"
        )
        result = parse_bom_file(tsv_data, "bom.tsv")
        assert result is not None
        assert result.height == 1

    def test_unsupported_format(self) -> None:
        """Should return None for unsupported formats."""
        result = parse_bom_file(b"%PDF-1.4", "bom.pdf")
        assert result is None

    def test_empty_csv(self) -> None:
        """Should return None for empty files."""
        result = parse_bom_file(b"", "bom.csv")
        assert result is None

    def test_no_bom_columns(self) -> None:
        """Should return None when no BOM columns are recognized."""
        csv_data = b"foo,bar,baz\n1,2,3\n"
        result = parse_bom_file(csv_data, "data.csv")
        assert result is None

    def test_csv_with_comment_header(self) -> None:
        """Should skip comment lines starting with #."""
        csv_data = (
            b"##########\n"
            b"# Generated by Tool v2\n"
            b"##########\n"
            b"REF,Value,Qty\n"
            b"R1,10k,2\n"
            b"C1,100nF,1\n"
        )
        result = parse_bom_file(csv_data, "bom.csv")
        assert result is not None
        assert result.height == 2
        assert result["reference"][0] == "R1"

    def test_false_positive_node_modules(self) -> None:
        """Should skip files in node_modules."""
        csv_data = b"Reference,Value\nR1,10k\n"
        result = parse_bom_file(
            csv_data,
            "root/node_modules/npm/bom.csv",
        )
        assert result is None

    def test_false_positive_gost_template(self) -> None:
        """Should skip Inventor GOST template files."""
        result = parse_bom_file(
            b"<fake/>",
            "Blue/Inventor/Design Data/GOST/de-DE/PartsListGroup1.xls",
        )
        assert result is None

    def test_kicad_export_xml(self) -> None:
        """Should parse KiCad export XML format."""
        xml_data = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<export version="D">
  <components>
    <comp ref="R1">
      <value>10k</value>
      <manufacturer>Yageo</manufacturer>
      <mpn>RC0402</mpn>
    </comp>
    <comp ref="C1">
      <value>100nF</value>
    </comp>
  </components>
</export>"""
        result = parse_bom_file(xml_data, "bom.xml")
        assert result is not None
        assert result.height == 2
        assert result["reference"][0] == "R1"
        assert result["component_name"][0] == "10k"
        assert result["part_number"][0] == "RC0402"

    def test_kicad_export_with_fields(self) -> None:
        """Should extract MPN/manufacturer from <fields> elements."""
        xml_data = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<export version="E">
  <components>
    <comp ref="R1">
      <value>10k</value>
      <footprint>Resistor_SMD:R_0805</footprint>
      <fields>
        <field name="MPN">RC0805FR-0710KL</field>
        <field name="Manufacturer">Yageo</field>
      </fields>
    </comp>
    <comp ref="C1">
      <value>100nF</value>
      <footprint>Capacitor_SMD:C_0402</footprint>
      <fields>
        <field name="LCSC">C14663</field>
      </fields>
    </comp>
  </components>
</export>"""
        result = parse_bom_file(xml_data, "bom.xml")
        assert result is not None
        assert result.height == 2
        assert result["part_number"][0] == "RC0805FR-0710KL"
        assert result["manufacturer"][0] == "Yageo"
        assert result["footprint"][0] == "Resistor_SMD:R_0805"
        # LCSC field should map to part_number for C1
        assert result["part_number"][1] == "C14663"

    def test_flat_xml(self) -> None:
        """Should parse flat schematic XML format."""
        xml_data = b"""\
<schematic>
  <component>
    <Reference>C10</Reference>
    <Value>1uF</Value>
    <Count>1</Count>
    <MPN>GCM155</MPN>
    <Manufacturer>Murata</Manufacturer>
  </component>
  <component>
    <Reference>R1</Reference>
    <Value>10k</Value>
    <Count>2</Count>
  </component>
</schematic>"""
        result = parse_bom_file(xml_data, "bom.xml")
        assert result is not None
        assert result.height == 2
        assert result["reference"][0] == "C10"
        assert result["quantity_raw"][0] == "1"
        assert result["part_number"][0] == "GCM155"

    def test_xml_unrecognized_format(self) -> None:
        """Should return None for non-BOM XML."""
        xml_data = b'<PartsList Version="2"><Style/></PartsList>'
        result = parse_bom_file(xml_data, "partslist.xml")
        assert result is None

    def test_eagle_xml(self) -> None:
        """Should parse Eagle schematic XML format."""
        xml_data = b"""\
<?xml version="1.0" encoding="utf-8"?>
<eagle version="9.6.2">
  <drawing>
    <schematic>
      <parts>
        <part name="R1" library="rcl" deviceset="R-US_" device="R0805"
              value="10k">
          <attribute name="MPN" value="RC0805FR-0710KL"/>
          <attribute name="MANUFACTURER" value="Yageo"/>
        </part>
        <part name="C1" library="rcl" deviceset="C-US" device="C0402"
              value="100nF"/>
      </parts>
    </schematic>
  </drawing>
</eagle>"""
        result = parse_bom_file(xml_data, "bom.xml")
        assert result is not None
        assert result.height == 2
        assert result["reference"][0] == "R1"
        assert result["component_name"][0] == "10k"
        assert result["footprint"][0] == "R0805"
        assert result["part_number"][0] == "RC0805FR-0710KL"
        assert result["manufacturer"][0] == "Yageo"

    def test_spreadsheetml_xml(self) -> None:
        """Should parse XML Spreadsheet 2003 (SpreadsheetML) format."""
        xml_data = b"""\
<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
  <Worksheet ss:Name="BOM">
    <Table>
      <Row>
        <Cell><Data ss:Type="String">Designator</Data></Cell>
        <Cell><Data ss:Type="String">Description</Data></Cell>
        <Cell><Data ss:Type="String">Quantity</Data></Cell>
        <Cell><Data ss:Type="String">Manufacturer</Data></Cell>
      </Row>
      <Row>
        <Cell><Data ss:Type="String">R1, R2</Data></Cell>
        <Cell><Data ss:Type="String">10k 0805</Data></Cell>
        <Cell><Data ss:Type="Number">2</Data></Cell>
        <Cell><Data ss:Type="String">Yageo</Data></Cell>
      </Row>
      <Row>
        <Cell><Data ss:Type="String">C1</Data></Cell>
        <Cell><Data ss:Type="String">100nF 0402</Data></Cell>
        <Cell><Data ss:Type="Number">1</Data></Cell>
        <Cell><Data ss:Type="String">Murata</Data></Cell>
      </Row>
    </Table>
  </Worksheet>
</Workbook>"""
        result = parse_bom_file(xml_data, "bom.xml")
        assert result is not None
        assert result.height == 2
        assert result["reference"][0] == "R1, R2"
        assert result["component_name"][0] == "10k 0805"
        assert result["manufacturer"][1] == "Murata"


class TestSeparatorAndEncoding:
    """Tests for separator auto-detection and encoding handling."""

    def test_semicolon_csv(self) -> None:
        """Semicolon-delimited CSV files are parsed correctly."""
        data = (
            b'"Id";"Designator";"Package";"Quantity";"Designation"\n'
            b'1;"C1";"C_0402";1;"100nF"\n'
        )
        result = parse_bom_file(data, "bom.csv")
        assert result is not None
        assert result.height == 1
        assert result["reference"][0] == "C1"

    def test_utf16_le_csv(self) -> None:
        """UTF-16 LE encoded files are decoded and parsed."""
        content = (
            "ID\tName\tDesignator\tFootprint\tQuantity\n"
            "1\t100nF\tC1\tC0402\t1\n"
        )
        data = b"\xff\xfe" + content.encode("utf-16-le")
        result = parse_bom_file(data, "bom.csv")
        assert result is not None
        assert result.height == 1
        assert result["reference"][0] == "C1"

    def test_kicad_csv_preamble(self) -> None:
        """KiCad CSV preamble lines are skipped."""
        data = (
            b'"Source:","/path/to/sch.kicad_sch"\n'
            b'"Date:","2024-01-15"\n'
            b'"Tool:","KiCad 7.0"\n'
            b'"Generator:",""\n'
            b'""\n'
            b'"Reference","Value","Footprint","Datasheet","Qty"\n'
            b'"C1","100nF","C_0402","","1"\n'
            b'"R1","10k","R_0603","","1"\n'
        )
        result = parse_bom_file(data, "bom.csv")
        assert result is not None
        assert result.height == 2
        assert result["reference"][0] == "C1"
        assert result["footprint"][1] == "R_0603"

    def test_whitespace_column_names(self) -> None:
        """Column names with leading/trailing whitespace are matched."""
        data = (
            b"S.No, Part Number, Manufacturer, "
            b"Reference designator, Part Value, Qty\n"
            b"1, RC0603, Yageo, R1, 10k, 1\n"
        )
        result = parse_bom_file(data, "bom.csv")
        assert result is not None
        assert result.height == 1
        assert result["part_number"][0] is not None
        assert result["manufacturer"][0] is not None


class TestParseRepoUrl:
    """Tests for _parse_repo_url."""

    def test_standard_url(self) -> None:
        """Should extract owner and repo from a standard URL."""
        result = _parse_repo_url(
            "https://github.com/owner/repo"
        )
        assert result == ("owner", "repo")

    def test_trailing_slash(self) -> None:
        """Should handle trailing slashes."""
        result = _parse_repo_url(
            "https://github.com/owner/repo/"
        )
        assert result == ("owner", "repo")

    def test_non_github_url(self) -> None:
        """Should return None for non-GitHub URLs."""
        result = _parse_repo_url("https://gitlab.com/x/y")
        assert result is None


class TestBuildBranchLookup:
    """Tests for _build_branch_lookup."""

    def test_reads_jsonl(self, tmp_path: Path) -> None:
        """Should build lookup from JSONL file."""
        import orjson

        record = {
            "repository": {
                "owner": "alice",
                "name": "myrepo",
                "default_branch": "develop",
            },
        }
        jsonl = tmp_path / "repos.jsonl"
        jsonl.write_bytes(orjson.dumps(record) + b"\n")

        lookup = _build_branch_lookup(jsonl)
        assert lookup["alice/myrepo"] == "develop"

    def test_missing_file(self, tmp_path: Path) -> None:
        """Should return empty dict for missing file."""
        lookup = _build_branch_lookup(tmp_path / "missing.jsonl")
        assert lookup == {}


class TestEnrichBomFiles:
    """Integration tests for the full enrichment pipeline."""

    @pytest.fixture()
    def db_path(self, tmp_path: Path) -> Path:
        """Create a temporary database with a project and BOM path."""
        path = tmp_path / "test.db"
        init_db(path)
        with transaction(path) as conn:
            upsert_project(
                conn,
                source="hackaday",
                source_id="123",
                name="Test Project",
                repo_url="https://github.com/testowner/testrepo",
            )
            insert_bom_file_path(
                conn, 1,
                "https://github.com/testowner/testrepo",
                "hardware/bom.csv",
            )
        return path

    def test_downloads_and_inserts(
        self, db_path: Path, tmp_path: Path,
    ) -> None:
        """Should download, parse, and insert BOM components."""
        import orjson

        # Create JSONL for branch lookup
        jsonl = tmp_path / "repos.jsonl"
        record = {
            "repository": {
                "owner": "testowner",
                "name": "testrepo",
                "default_branch": "main",
            },
        }
        jsonl.write_bytes(orjson.dumps(record) + b"\n")

        # Mock the download
        csv_data = (
            b"Reference,Value,Qty,Manufacturer,MPN\n"
            b"R1,10k,2,Yageo,RC0402FR\n"
            b"C1,100nF,1,Murata,GCM155R71C\n"
        )

        with patch(
            "osh_datasets.enrichment.bom_files._download_file",
            return_value=csv_data,
        ):
            total = enrich_bom_files(
                db_path=db_path,
                jsonl_path=jsonl,
            )

        assert total == 2

        conn = open_connection(db_path)

        # Verify components inserted
        components = conn.execute(
            "SELECT reference, component_name, quantity, "
            "manufacturer, part_number "
            "FROM bom_components WHERE project_id = 1 "
            "ORDER BY reference"
        ).fetchall()
        assert len(components) == 2
        assert tuple(components[0]) == (
            "C1", "100nF", 1, "Murata", "GCM155R71C",
        )
        assert tuple(components[1]) == (
            "R1", "10k", 2, "Yageo", "RC0402FR",
        )

        # Verify processed flag set
        bfp = conn.execute(
            "SELECT processed, component_count "
            "FROM bom_file_paths WHERE id = 1"
        ).fetchone()
        assert bfp is not None
        assert bfp[0] == 1  # processed
        assert bfp[1] == 2  # component_count

        conn.close()

    def test_skips_already_processed(
        self, db_path: Path, tmp_path: Path,
    ) -> None:
        """Should skip rows already marked as processed."""
        # Mark as processed
        conn = open_connection(db_path)
        conn.execute(
            "UPDATE bom_file_paths SET processed = 1 WHERE id = 1"
        )
        conn.commit()
        conn.close()

        jsonl = tmp_path / "repos.jsonl"
        jsonl.write_bytes(b"")

        total = enrich_bom_files(
            db_path=db_path,
            jsonl_path=jsonl,
        )
        assert total == 0

    def test_handles_download_failure(
        self, db_path: Path, tmp_path: Path,
    ) -> None:
        """Should mark row as processed with 0 components on failure."""
        import orjson

        jsonl = tmp_path / "repos.jsonl"
        record = {
            "repository": {
                "owner": "testowner",
                "name": "testrepo",
                "default_branch": "main",
            },
        }
        jsonl.write_bytes(orjson.dumps(record) + b"\n")

        with patch(
            "osh_datasets.enrichment.bom_files._download_file",
            return_value=None,
        ):
            total = enrich_bom_files(
                db_path=db_path,
                jsonl_path=jsonl,
            )

        assert total == 0

        conn = open_connection(db_path)
        bfp = conn.execute(
            "SELECT processed, component_count "
            "FROM bom_file_paths WHERE id = 1"
        ).fetchone()
        assert bfp is not None
        assert bfp[0] == 1
        assert bfp[1] == 0
        conn.close()

    def test_dedup_prevents_duplicates(
        self, db_path: Path, tmp_path: Path,
    ) -> None:
        """Should not insert duplicate components on re-run."""
        import orjson

        jsonl = tmp_path / "repos.jsonl"
        record = {
            "repository": {
                "owner": "testowner",
                "name": "testrepo",
                "default_branch": "main",
            },
        }
        jsonl.write_bytes(orjson.dumps(record) + b"\n")

        csv_data = (
            b"Reference,Value,Qty,Manufacturer,MPN\n"
            b"R1,10k,2,Yageo,RC0402FR\n"
        )

        with patch(
            "osh_datasets.enrichment.bom_files._download_file",
            return_value=csv_data,
        ):
            enrich_bom_files(db_path=db_path, jsonl_path=jsonl)

        # Reset processed flag and re-run
        conn = open_connection(db_path)
        conn.execute(
            "UPDATE bom_file_paths SET processed = 0 WHERE id = 1"
        )
        conn.commit()
        conn.close()

        with patch(
            "osh_datasets.enrichment.bom_files._download_file",
            return_value=csv_data,
        ):
            enrich_bom_files(db_path=db_path, jsonl_path=jsonl)

        conn = open_connection(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM bom_components WHERE project_id = 1"
        ).fetchone()[0]
        conn.close()
        assert count == 1  # Not 2
