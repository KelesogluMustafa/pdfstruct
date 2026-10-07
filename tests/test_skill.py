"""Agent Skill: instructions only, correct archive layout."""
import importlib.util
import zipfile
from pathlib import Path

from conftest import TOOL_DIR

SKILL = TOOL_DIR / "skills" / "pdfstruct" / "SKILL.md"


def load_builder():
    spec = importlib.util.spec_from_file_location("build_skill_zip", TOOL_DIR / "scripts" / "build_skill_zip.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_metadata_and_rules():
    text = SKILL.read_text(encoding="utf-8")
    fields = load_builder().validate(text)
    assert fields["name"] == "pdfstruct" and len(fields["description"]) <= 1024
    for required in ("convert(", "read_excerpt", "search", "command line", "--format", "pdf",
                     "untrusted", "raw.json", "already_pdf", "never overwritten"):
        assert required.lower() in text.lower(), required
    # Claude for Windows: MCP only; no command line without a local shell; say when not connected
    for rule in ("only way in Claude for Windows", "do not try the command line",
                 "PDFStruct is not connected", "only uploaded into the chat"):
        assert rule in text, rule
    assert "Read tool" not in text  # no Claude Code tool names in the shared skill
    assert sorted(p.name for p in SKILL.parent.iterdir()) == ["SKILL.md"]  # no engine, no models


def test_skill_zip_layout(tmp_path, monkeypatch):
    builder = load_builder()
    monkeypatch.setattr(builder, "TARGET", tmp_path / "pdfstruct-skill.zip")
    target = builder.build()
    assert builder.check(target) == ["pdfstruct/SKILL.md"]
    with zipfile.ZipFile(target) as archive:
        assert archive.read("pdfstruct/SKILL.md").decode("utf-8").startswith("---\nname: pdfstruct\n")
    first = target.read_bytes()
    assert builder.build().read_bytes() == first  # reproducible
