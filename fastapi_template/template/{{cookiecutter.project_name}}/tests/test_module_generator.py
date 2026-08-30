"""Test that the module generator produces valid Python files."""
import ast
from pathlib import Path

import pytest

from scripts.generate_module import generate_module, snake_to_pascal


class TestNameConversion:
    def test_snake_to_pascal(self) -> None:
        assert snake_to_pascal("leads") == "Leads"
        assert snake_to_pascal("order_items") == "OrderItems"


class TestGenerateModule:
    @pytest.fixture
    def tmp_project(self, tmp_path: Path) -> Path:
        (tmp_path / "pyproject.toml").write_text('name = "my_app"\n')
        (tmp_path / "business" / "modules").mkdir(parents=True)
        (tmp_path / "my_app" / "core").mkdir(parents=True)
        (tmp_path / "my_app" / "core" / "crud.py").write_text("")
        return tmp_path

    def test_creates_all_files(self, tmp_project: Path) -> None:
        written = generate_module("crm.leads", project_root=tmp_project)
        filenames = [f.name for f in written]
        assert "__init__.py" in filenames
        assert "models.py" in filenames
        assert "schemas.py" in filenames
        assert "service.py" in filenames
        assert "repository.py" in filenames
        assert "router.py" in filenames

    def test_generated_files_are_valid_python(self, tmp_project: Path) -> None:
        written = generate_module("crm.leads", fields=[("name", "str"), ("email", "str")],
                                  project_root=tmp_project)
        for filepath in written:
            if filepath.name == "__init__.py":
                continue  # empty file is valid Python
            source = filepath.read_text()
            try:
                ast.parse(source)
            except SyntaxError as exc:
                pytest.fail(f"{filepath.name} has invalid Python: {exc}")

    def test_service_class_uses_correct_name(self, tmp_project: Path) -> None:
        generate_module("catalog.products", project_root=tmp_project)
        service_file = tmp_project / "business" / "modules" / "catalog" / "products" / "service.py"
        content = service_file.read_text()
        assert "ProductsService(CrudService[Products])" in content

    def test_router_has_prefix_and_service_factory(self, tmp_project: Path) -> None:
        generate_module("crm.contacts", project_root=tmp_project)
        router_file = tmp_project / "business" / "modules" / "crm" / "contacts" / "router.py"
        content = router_file.read_text()
        assert 'prefix="/contacts"' in content
        assert "service_factory=_service_factory" in content
        assert "async def _service_factory" in content
        assert "NotImplementedError" not in content
{%- if cookiecutter.add_users|string|lower == "true" %}
        assert "Depends(CurrentUser)" in content
        assert "Depends(RequireCsrf())" in content
{%- endif %}
        repository_file = router_file.with_name("repository.py")
        assert "data.adapters.memory.repository" in repository_file.read_text()

    @pytest.mark.parametrize(
        "module_path",
        [
            "leads",
            "CRM.leads",
            "crm.leads.extra",
            "../crm.leads",
            "crm/../leads",
            "crm.class",
        ],
    )
    def test_rejects_invalid_module_path(
        self,
        tmp_project: Path,
        module_path: str,
    ) -> None:
        with pytest.raises(ValueError, match="module path must be"):
            generate_module(module_path, project_root=tmp_project)

    @pytest.mark.parametrize(
        "fields",
        [
            [("display-name", "str")],
            [("class", "str")],
            [("id", "str")],
            [("name", "EmailStr")],
            [("name", "str"), ("name", "int")],
            [("model_dump", "str")],
        ],
    )
    def test_rejects_unsafe_fields(
        self,
        tmp_project: Path,
        fields: list[tuple[str, str]],
    ) -> None:
        with pytest.raises(ValueError, match="invalid field"):
            generate_module("crm.leads", fields=fields, project_root=tmp_project)

    def test_custom_fields_in_schemas(self, tmp_project: Path) -> None:
        generate_module("crm.deals",
                        fields=[("title", "str"), ("amount", "float"), ("status", "str")],
                        project_root=tmp_project)
        schema_file = tmp_project / "business" / "modules" / "crm" / "deals" / "schemas.py"
        content = schema_file.read_text()
        assert "title: str" in content
        assert "amount: float" in content
        assert "status: str | None = None" in content  # Update schema has Optional

    def test_directory_structure(self, tmp_project: Path) -> None:
        generate_module("hr.employees", project_root=tmp_project)
        expected = tmp_project / "business" / "modules" / "hr" / "employees"
        assert expected.exists()
        assert (expected / "service.py").exists()
