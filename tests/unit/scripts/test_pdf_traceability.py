import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "docs/requirements/PDF_TRACEABILITY.md"
PDF = ROOT / "docs/Agentic_GTM_Revenue_Operations_Platform_Guia_Projeto.pdf"

CHECKER_PATH = ROOT / "scripts/check_pdf_traceability.py"
SPEC = importlib.util.spec_from_file_location("pdf_traceability_checker", CHECKER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load the PDF traceability checker")
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
parse_table = CHECKER.parse_table
validate_matrix = CHECKER.validate_matrix


def test_real_matrix_matches_pdf_and_covers_every_page() -> None:
    assert validate_matrix(MATRIX, PDF) == []
    _, rows = parse_table(MATRIX.read_text(encoding="utf-8"))
    assert len(rows) >= 20


def test_duplicate_id_and_invalid_state_are_rejected(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.md"
    content = MATRIX.read_text(encoding="utf-8")
    first_row = next(line for line in content.splitlines() if line.startswith("| PDF-"))
    invalid_row = first_row.replace("| partial |", "| bogus |", 1)
    matrix.write_text(
        content.replace(first_row, f"{invalid_row}\n{first_row}", 1), encoding="utf-8"
    )

    errors = validate_matrix(matrix, PDF)

    assert any("invalid state" in error for error in errors)
    assert any("duplicate ID" in error for error in errors)


def test_hash_drift_and_missing_implemented_evidence_are_rejected(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.md"
    content = MATRIX.read_text(encoding="utf-8")
    content = content.replace(
        "8C294C58019722357B98BEF75B2E3CA7B52D3BE21891FF9D9F7C7D0B4D86E42A", "0" * 64
    )
    first_row = next(line for line in content.splitlines() if "| implemented |" in line)
    invalid_row = first_row.replace("evidence:", "N/A", 1)
    matrix.write_text(content.replace(first_row, invalid_row, 1), encoding="utf-8")

    errors = validate_matrix(matrix, PDF)

    assert any("SHA-256 mismatch" in error for error in errors)
    assert any("implemented without concrete evidence" in error for error in errors)
