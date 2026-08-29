"""Tests for nk doctor and nk validate scripts."""
import ast
from pathlib import Path

import pytest


class TestDoctorScript:
    def test_doctor_exists_and_parses(self) -> None:
        doctor = Path(__file__).parent.parent / "scripts" / "doctor.py"
        assert doctor.exists()
        source = doctor.read_text()
        try:
            ast.parse(source)
        except SyntaxError as exc:
            pytest.fail(f"doctor.py has syntax error: {exc}")

    def test_run_doctor_returns_bool(self) -> None:
        import importlib
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        from doctor import run_doctor
        result = run_doctor(project_root=Path(__file__).parent.parent)
        assert isinstance(result, bool)


class TestValidateScript:
    def test_validate_exists_and_parses(self) -> None:
        validate = Path(__file__).parent.parent / "scripts" / "validate.py"
        assert validate.exists()
        source = validate.read_text()
        try:
            ast.parse(source)
        except SyntaxError as exc:
            pytest.fail(f"validate.py has syntax error: {exc}")

    def test_validate_detects_broken_python(self, tmp_path: Path) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        # Create a package with a broken .py file
        pkg = tmp_path / "broken_app"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "bad_file.py").write_text("def broken(:\n  pass")

        from validate import run_validate
        result = run_validate(project_root=tmp_path)
        assert result is False

    def test_validate_passes_clean_project(self, tmp_path: Path) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        pkg = tmp_path / "clean_app"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "good_file.py").write_text("def hello():\n    return True\n")

        from validate import run_validate
        result = run_validate(project_root=tmp_path)
        assert result is True
