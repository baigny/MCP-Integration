"""JD embed -> hybrid retrieval -> score -> reasoning (regex-based, no LLM)."""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend import embeddings, fs_tools, vector_store

RESUME_DIR = "data/resumes"
CANDIDATE_POOL = 30  # chunks pulled from Chroma before aggregating per-resume
TOP_N = 10
MIN_MUST_HAVE_MATCHES = 1  # candidates matching fewer JD skills than this are dropped


def _normalize(text):
    """Tokenize on word boundaries and rejoin with '|' delimiters, so punctuation/spacing
    variants (CI/CD vs ci-cd vs CICD) collapse to the same token stream while a short skill
    like 'EE' can no longer substring-match inside an unrelated word like 'need' - matching
    now requires the skill's own token sequence to appear as whole, adjacent tokens."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return "|" + "|".join(tokens) + "|"


def jd_must_have_skills(jd_text, candidate_skills):
    """Must-have skills = the union of all retrieved candidates' own (already
    extracted at ingest time by metadata_extractor) skills that literally
    appear in the JD text - no LLM call needed to re-derive them here."""
    normalized_jd = _normalize(jd_text)
    all_skills = {skill for skills in candidate_skills for skill in skills}
    return sorted(skill for skill in all_skills if _normalize(skill) in normalized_jd)


def keyword_score(resume_skills, resume_text, must_have_skills):
    if not must_have_skills:
        return 0.0, []
    normalized_text = _normalize(resume_text)
    normalized_skills = {_normalize(s) for s in resume_skills}
    matched = [
        skill for skill in must_have_skills
        if _normalize(skill) in normalized_skills or _normalize(skill) in normalized_text
    ]
    return len(matched) / len(must_have_skills), matched


def generate_reasoning(matched_skills, must_have_skills, years_experience, sections):
    """Template-based reasoning referencing matched skills and resume sections."""
    if matched_skills:
        skill_part = f"Matches {len(matched_skills)}/{len(must_have_skills)} required skills ({', '.join(matched_skills)})"
    else:
        skill_part = "No required skills matched directly, ranked on semantic similarity alone"

    section_part = f", supported by the {', '.join(sections)} section(s)" if sections else ""
    experience_part = f". Candidate has {years_experience} years of experience." if years_experience else "."

    return f"{skill_part}{section_part}{experience_part}"


def match(jd_text, top_n=TOP_N, min_years=None, semantic_weight=0.6, keyword_weight=0.4, include_reasoning=True):
    jd_embedding = embeddings.embed_text(jd_text)

    where = {"years_experience": {"$gte": min_years}} if min_years else None
    results = vector_store.query(jd_embedding, top_k=CANDIDATE_POOL, where=where)

    if not results["ids"][0]:
        return []

    # aggregate best (lowest distance) chunk per resume
    per_resume = {}
    for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
        source = meta["source_file"]
        if source not in per_resume or dist < per_resume[source]["best_distance"]:
            per_resume[source] = {"best_distance": dist, "meta": meta}
        per_resume[source].setdefault("chunks", []).append({
            "section": meta.get("section", "resume"),
            "text": doc,
        })

    resume_skills = {
        source: [s.strip() for s in info["meta"].get("skills", "").split(",") if s.strip()]
        for source, info in per_resume.items()
    }
    must_have = jd_must_have_skills(jd_text, resume_skills.values())

    candidates = []
    for source, info in per_resume.items():
        meta = info["meta"]
        resume_file_path = os.path.join(RESUME_DIR, source)
        read_result = fs_tools.read_file(resume_file_path)
        resume_text = read_result["content"] if read_result["success"] else "\n".join(c["text"] for c in info["chunks"])

        # distance -> similarity (Chroma cosine distance is in [0, 2])
        semantic_sim = max(0.0, 1 - info["best_distance"] / 2)
        kw_score, matched_skills = keyword_score(resume_skills[source], resume_text, must_have)

        # hard must-have filter: drop candidates matching too few required skills
        if must_have and len(matched_skills) < MIN_MUST_HAVE_MATCHES:
            continue

        final_score = round((semantic_weight * semantic_sim + keyword_weight * kw_score) * 100, 1)

        candidates.append({
            "candidate_name": meta.get("name", "Unknown"),
            "resume_path": resume_file_path.replace("\\", "/"),
            "match_score": final_score,
            "years_experience": meta.get("years_experience", 0),
            "education": meta.get("education", "Unknown"),
            "semantic_similarity": round(semantic_sim, 3),
            "keyword_match": round(kw_score, 3),
            "matched_skills": matched_skills,
            "relevant_excerpts": [f"[{c['section']}] {c['text'].strip()[:300]}" for c in info["chunks"][:3]],
            "matched_chunks": info["chunks"],
        })

    candidates.sort(key=lambda c: c["match_score"], reverse=True)
    top_candidates = candidates[:top_n]

    for c in top_candidates:
        if include_reasoning:
            sections = sorted({ch["section"] for ch in c["matched_chunks"][:3]})
            c["reasoning"] = generate_reasoning(c["matched_skills"], must_have, c["years_experience"], sections)
        del c["matched_chunks"]

    return top_candidates


def main():
    parser = argparse.ArgumentParser(description="Match a job description against ingested resumes.")
    parser.add_argument("jd_path", help="Path to job description text file")
    parser.add_argument("--top", type=int, default=TOP_N)
    parser.add_argument("--min-years", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="Print results as JSON instead of text")
    args = parser.parse_args()

    read_result = fs_tools.read_file(args.jd_path)
    if not read_result["success"]:
        print(f"Error reading {args.jd_path}: {read_result['error']}")
        sys.exit(1)

    jd_text = read_result["content"]
    results = match(jd_text, top_n=args.top, min_years=args.min_years)

    if args.json:
        print(json.dumps({"job_description": jd_text, "top_matches": results}, indent=2))
        return

    print(f"\nTop {len(results)} matches for {args.jd_path}:\n")
    for i, c in enumerate(results, start=1):
        print(f"{i}. {c['candidate_name']} ({c['resume_path']}) — score {c['match_score']}/100")
        print(f"   years: {c['years_experience']}, education: {c['education']}")
        print(f"   semantic: {c['semantic_similarity']}, keyword: {c['keyword_match']}, matched skills: {c['matched_skills']}")
        print(f"   reasoning: {c['reasoning']}")
        print()


if __name__ == "__main__":
    main()
