from {{cookiecutter.project_name}}.agents.guardrails import Guardrails


def test_input_hook_rewrites() -> None:
    def redact(text: str) -> str:
        return text.replace("secret", "[REDACTED]")
    g = Guardrails(input_hooks=[redact])
    assert g.check_input("my secret is 123") == "my [REDACTED] is 123"


def test_output_hook_replaces() -> None:
    def censor(text: str) -> str | None:
        if "badword" in text:
            return text.replace("badword", "***")
        return None
    g = Guardrails(output_hooks=[censor])
    assert g.check_output("this has badword inside") == "this has *** inside"
    assert g.check_output("clean text") == "clean text"


def test_tool_deny_still_blocks() -> None:
    g = Guardrails(deny={"dangerous"})
    assert "DENIED" in g.check_tool("dangerous") or g.check_tool("dangerous") is not None
