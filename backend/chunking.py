"""Regex-based section chunking for resumes (no LLM - splits on ALL-CAPS header lines)."""
import re

HEADER_RE = re.compile(r"^[A-Z][A-Z \-/&]{2,}$")
MARKDOWN_EMPHASIS_RE = re.compile(r"^([*_]{1,2})(.+)\1$")


def _strip_markdown_emphasis(line):
    """Strips wrapping **bold**/__bold__/*italic* markers some resumes use for headers."""
    match = MARKDOWN_EMPHASIS_RE.match(line)
    return match.group(2).strip() if match else line


def chunk_resume(resume_text):
    """Segments resume text into sections by ALL-CAPS header lines. Returns list of {"section", "text"}."""
    lines = resume_text.splitlines()
    chunks = []
    current_section = "SUMMARY"
    current_lines = []
    for line in lines:
        stripped = _strip_markdown_emphasis(line.strip())
        if stripped and HEADER_RE.match(stripped) and len(stripped) < 40:
            if current_lines:
                chunks.append({"section": current_section, "text": "\n".join(current_lines).strip()})
            current_section = stripped
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        chunks.append({"section": current_section, "text": "\n".join(current_lines).strip()})
    return [c for c in chunks if c["text"]]
