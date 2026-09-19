"""Regex-based structured metadata (name, skills, years_experience, education) per resume - no LLM."""
import re

from backend.chunking import _strip_markdown_emphasis, chunk_resume

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

DATE_RANGE_RE = re.compile(
    r"([A-Za-z]{3,9})\s+(\d{4})\s*[-–to]+\s*(Present|Current|[A-Za-z]{3,9}\s+\d{4})",
    re.IGNORECASE,
)
YEAR_ONLY_RANGE_RE = re.compile(r"\((\d{4})\s*[-–]\s*(Present|Current|\d{4})\)", re.IGNORECASE)
STATED_EXPERIENCE_RE = re.compile(r"(\d+)\+?\s*years?\s+(?:of\s+)?experience", re.IGNORECASE)
CURRENT_YEAR = 2026


def _section_text(chunks, name):
    for c in chunks:
        if c["section"].strip().lower() == name:
            return c["text"]
    return ""


def _parse_skills(section_text):
    skills = []
    for line in section_text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[-•*]\s*", "", line)
        parenthetical = re.findall(r"\(([^)]*)\)", line)
        main = re.sub(r"\([^)]*\)", "", line)
        for piece in [main] + parenthetical:
            for part in re.split(r",| and |/", piece):
                part = part.strip(" .")
                if part:
                    skills.append(part)

    seen = set()
    deduped = []
    for s in skills:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(s)
    return deduped


def _months_between(start_month, start_year, end_str):
    end_str = end_str.strip().lower()
    if end_str in ("present", "current"):
        end_month, end_year = 8, 2026  # treat as "now" for this dataset
    else:
        m = re.match(r"([A-Za-z]{3,9})\s+(\d{4})", end_str)
        if not m:
            return 0
        end_month = MONTHS.get(m.group(1)[:3].lower(), 1)
        end_year = int(m.group(2))
    return max(0, (end_year - start_year) * 12 + (end_month - start_month))


def _years_from_date_ranges(section_text):
    total_months = 0
    for start_name, start_year, end_str in DATE_RANGE_RE.findall(section_text):
        start_month = MONTHS.get(start_name[:3].lower())
        if start_month is None:
            continue
        total_months += _months_between(start_month, int(start_year), end_str)

    for start_year, end_str in YEAR_ONLY_RANGE_RE.findall(section_text):
        end_year = CURRENT_YEAR if end_str.lower() in ("present", "current") else int(end_str)
        total_months += max(0, (end_year - int(start_year)) * 12)

    return round(total_months / 12)


def _parse_years_experience(resume_text, experience_section_text):
    # An explicit "N years of experience" statement (common in a summary/objective)
    # is a more direct and reliable signal than reconstructing it from job date ranges.
    stated = STATED_EXPERIENCE_RE.search(resume_text)
    if stated:
        return int(stated.group(1))
    return _years_from_date_ranges(experience_section_text)


def _parse_education(section_text):
    for line in section_text.splitlines():
        line = line.strip()
        if line:
            return line
    return "Unknown"


GENERIC_LABEL_LINES = {"name", "resume", "profile", "candidate", "cv"}


def _parse_name(resume_text):
    for line in resume_text.strip().splitlines():
        line = _strip_markdown_emphasis(line.strip())
        if line and line.lower() not in GENERIC_LABEL_LINES:
            return line
    return "Unknown"


def extract_metadata(resume_text):
    name = _parse_name(resume_text)

    chunks = chunk_resume(resume_text)
    skills_text = _section_text(chunks, "skills")
    experience_text = _section_text(chunks, "experience")
    education_text = _section_text(chunks, "education")

    return {
        "name": name or "Unknown",
        "skills": _parse_skills(skills_text),
        "years_experience": _parse_years_experience(resume_text, experience_text),
        "education": _parse_education(education_text) or "Unknown",
    }
