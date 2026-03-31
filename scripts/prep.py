#!/usr/bin/env python3
"""
prep.py — Job application prep.

Takes a job URL, researches the company, and produces:
  - Fit analysis + gap matrix
  - Humanized cover letter saved to covers/
  - Study guide (what to review before the interview)
  - Honest assessment + recommendation

Uses the Claude API with live web search and your resume context.

Usage:
    python scripts/prep.py --url "https://job-boards.greenhouse.io/..."
    python scripts/prep.py --url "https://..." --no-cl    # skip cover letter
    python scripts/prep.py --list                          # process all URLs in jobs.txt
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("anthropic not installed. Run: pip install anthropic")
    sys.exit(1)

try:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.enums import TA_LEFT
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

# ── paths ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
RESUME_CONTEXT = ROOT / "skill" / "references" / "resume_context.md"
COVERS_DIR = ROOT / "covers"
OUTPUT_DIR = ROOT / "output"

COVERS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ── system prompts ────────────────────────────────────────────────────────────

CANDIDATE_NAME = "Arnav Nair"

def build_research_system_prompt() -> str:
    """Opus: research the role and produce the brief (no cover letter)."""
    resume = RESUME_CONTEXT.read_text() if RESUME_CONTEXT.exists() else "(no resume context found)"
    return f"""You are a job application strategist for a quantitative finance professional named {CANDIDATE_NAME}.
Your job is to produce a structured application brief for any role the user gives you.

## Candidate Resume Context

{resume}

## Output Format

Produce the following sections in order. Use markdown headers.

### 1. Role Summary
Company, role title, location, level, platform (Greenhouse/Workday/etc.), and a 2-sentence
description of what the team actually does — not the job posting language.

### 2. Fit Matrix
A table with columns: Requirement | Candidate Evidence | Strength (Strong/Moderate/Gap)
Be specific. Pull directly from the resume context above. Do not fabricate.

### 3. Overall Fit Rating
One of: Strong Fit / Moderate Fit / Stretch / Likely Underqualified
Explain in 2-3 sentences.

### 4. Key Strengths to Lead With
2-3 bullet points. Specific to this role. Pull from resume context.

### 5. Gaps and How to Address Them
Honest list. If there's no adjacent experience, say so. Don't spin.

### 6. Study Guide
What to review before a phone screen or interview for this specific role.
Organize by topic (e.g., "Portfolio risk metrics", "Factor models", "Python/SQL").
3-5 bullets per topic. Be specific — name the actual concepts, formulas, or tools.

### 7. "Why This Role" Talking Points
2-3 sentences the candidate can use in a recruiter screen or "why us" field.
Ground these in something specific from your company research. Sounds like a real person.

### 8. Red Flags / Honest Assessment
- Is the role too senior?
- Missing credential (MS/PhD required)?
- Geographic mismatch?
- Domain outside experience?
- Any other reason this might not be worth the time?

### 9. Recommendation
One line: Apply / Apply with caveats / Skip — and why.
"""


def build_cl_system_prompt() -> str:
    """Sonnet: write the cover letter using research context."""
    resume = RESUME_CONTEXT.read_text() if RESUME_CONTEXT.exists() else "(no resume context found)"
    return f"""You are a cover letter writer for {CANDIDATE_NAME}, a quantitative finance professional.
You will receive a job posting, company research, and a fit analysis. Your only job is to write
a single cover letter — nothing else.

## Candidate Resume Context

{resume}

## Cover Letter Requirements

- Sign off as: {CANDIDATE_NAME}
- Length: 250-400 words. Not a word more.
- Structure:
  1. Opening (2-3 sentences): state the role, reference ONE specific recent company fact
     from the research (fund performance, a product launch, a leadership change, a deal).
     NOT generic mission-statement language. No "I am writing to express my interest."
  2. Body paragraph 1 (3-4 sentences): strongest relevant experience mapped to the role's
     primary responsibility. Name the specific tool, model, or result. Pull from resume context only.
  3. Body paragraph 2 (3-4 sentences): second angle of fit — a different skill dimension,
     adjacent experience, or relevant project. Ground it in resume context.
  4. Closing (2-3 sentences): what {CANDIDATE_NAME} wants to do in this role specifically.
     End with a concrete next step. No "I look forward to the opportunity."

## Non-Negotiable Writing Rules (Blader Humanizer)

These rules exist because AI writing is detectable. Every rule broken makes the letter worse.

- NO em dashes (--) anywhere. Use a comma or period instead.
- NO "I am passionate about" or "I am excited to" or "I am eager to"
- NO "leverage", "utilize", "spearhead", "drive", "foster", "impactful", "synergy"
- NO rule-of-three constructions ("A, B, and C" lists in openers/closers)
- NO sentences starting with "Furthermore", "Moreover", "Additionally", "In conclusion"
- NO generic closers like "I look forward to hearing from you" or "I welcome the opportunity"
- NO fabricated claims. Every statement must trace to the resume context above.
- Write like a real 22-year-old quant writing a professional email to a hiring manager.
  Confident, direct, specific. Not a career-center template.
- After drafting, mentally check: would a human write this sentence? If not, rewrite it.

Output ONLY the cover letter text. No preamble, no "here is the cover letter", no commentary."""


# ── main ──────────────────────────────────────────────────────────────────────

def _save_cover_letter_pdf(text: str, path: Path, company: str) -> None:
    """Render a plain-text cover letter to a clean PDF."""
    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        leftMargin=1.1 * inch,
        rightMargin=1.1 * inch,
        topMargin=1.0 * inch,
        bottomMargin=1.0 * inch,
    )
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "CLBody",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=11,
        leading=16,
        alignment=TA_LEFT,
        spaceAfter=10,
    )
    story = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        # Escape special reportlab chars
        para = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(para, body_style))
        story.append(Spacer(1, 4))
    doc.build(story)


def slugify(text: str) -> str:
    """Convert text to a safe filename slug."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", text).strip("_")[:60]


def extract_company_from_url(url: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    parts = parsed.path.strip("/").split("/")

    if "greenhouse" in domain and parts:
        return parts[0].title()

    # Known domains
    known = {
        "bankofamerica": "BofA",
        "goldmansachs": "GoldmanSachs",
        "morganstanley": "MorganStanley",
        "jpmorgan": "JPMorgan",
        "citadel": "Citadel",
        "twosigma": "TwoSigma",
        "deshaw": "DEShaw",
        "point72": "Point72",
        "millennium": "Millennium",
        "hudsonrivertrading": "HRT",
        "janeststreet": "JaneStreet",
        "biospace": "BioSpace",
    }
    for key, name in known.items():
        if key in domain:
            return name

    # Fallback: first meaningful domain segment
    segment = domain.replace("www.", "").split(".")[0]
    return segment.title()


def run_prep(url: str, skip_cl: bool = False) -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        print("Run: export ANTHROPIC_API_KEY=your_key_here")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    company = extract_company_from_url(url)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    total_input = 0
    total_output = 0

    print(f"\n{'='*60}")
    print(f"Prepping: {company}")
    print(f"URL: {url}")
    print(f"{'='*60}\n")

    # ── pass 1: Opus — research + brief ──────────────────────────────────────
    print("[1/2] Opus researching role and building brief...\n")

    research_prompt = f"""Job posting URL: {url}

1. Use web_fetch to retrieve the full job description.
2. Use web_search to find 2-3 recent specific facts about the company
   (last 6 months: fund performance, product launches, leadership changes, deals, expansions).
   Real and recent only — no generic mission-statement language.
3. Produce the full application brief as specified."""

    brief_chunks = []
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=build_research_system_prompt(),
        tools=[
            {"type": "web_search_20260209", "name": "web_search"},
            {"type": "web_fetch_20260209",  "name": "web_fetch"},
        ],
        messages=[{"role": "user", "content": research_prompt}],
    ) as stream:
        for event in stream:
            if event.type == "content_block_delta" and event.delta.type == "text_delta":
                chunk = event.delta.text
                print(chunk, end="", flush=True)
                brief_chunks.append(chunk)
        opus_final = stream.get_final_message()

    brief = "".join(brief_chunks)
    total_input  += opus_final.usage.input_tokens
    total_output += opus_final.usage.output_tokens

    # ── save brief ────────────────────────────────────────────────────────────
    brief_path = OUTPUT_DIR / f"{slugify(company)}_{timestamp}_brief.md"
    brief_path.write_text(
        f"# Application Brief: {company}\n"
        f"URL: {url}\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        + brief
    )
    print(f"\n\n{'='*60}")
    print(f"Brief saved to: {brief_path}")

    if skip_cl:
        _print_cost(total_input, total_output)
        return

    # ── pass 2: Sonnet — write cover letter ──────────────────────────────────
    print(f"\n[2/2] Sonnet writing cover letter for {CANDIDATE_NAME}...\n")

    cl_prompt = f"""Job URL: {url}

Here is the research brief from the previous analysis:

{brief}

Using the brief above and your resume context, write the cover letter now."""

    cl_chunks = []
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=build_cl_system_prompt(),
        messages=[{"role": "user", "content": cl_prompt}],
    ) as stream:
        for event in stream:
            if event.type == "content_block_delta" and event.delta.type == "text_delta":
                chunk = event.delta.text
                print(chunk, end="", flush=True)
                cl_chunks.append(chunk)
        sonnet_final = stream.get_final_message()

    cl_text = "".join(cl_chunks).strip()
    # Ensure name is present in sign-off
    if CANDIDATE_NAME not in cl_text:
        cl_text += f"\n\nSincerely,\n{CANDIDATE_NAME}"

    total_input  += sonnet_final.usage.input_tokens
    total_output += sonnet_final.usage.output_tokens

    # ── save cover letter ─────────────────────────────────────────────────────
    cl_base = f"CoverLetter_{slugify(company)}_{timestamp}"
    cl_path = COVERS_DIR / f"{cl_base}.txt"
    cl_path.write_text(cl_text)

    print(f"\n\n{'='*60}")
    if HAS_REPORTLAB:
        pdf_path = COVERS_DIR / f"{cl_base}.pdf"
        _save_cover_letter_pdf(cl_text, pdf_path, company)
        print(f"Cover letter saved to: {pdf_path}")
    else:
        print(f"Cover letter saved to: {cl_path}")
        print("(pip install reportlab for auto-PDF)")

    _print_cost(total_input, total_output)


def _print_cost(input_tokens: int, output_tokens: int) -> None:
    # Blended rate: Opus input $5/1M, Sonnet input $3/1M, outputs $25/$15 per 1M
    # We track combined totals; use Opus rates as a conservative upper bound
    input_cost  = input_tokens  * 0.000005
    output_cost = output_tokens * 0.000025
    print(f"\nTokens: {input_tokens} in / {output_tokens} out")
    print(f"Estimated cost: ${input_cost + output_cost:.4f}")
    print(f"{'='*60}\n")


def load_jobs() -> list[str]:
    jobs_file = ROOT / "jobs.txt"
    if not jobs_file.exists():
        return []
    urls = []
    for line in jobs_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def convert_to_pdf(txt_path: Path) -> None:
    """Convert an existing cover letter .txt to .pdf (no API call)."""
    if not HAS_REPORTLAB:
        print("reportlab not installed. Run: pip install reportlab")
        return
    if not txt_path.exists():
        print(f"File not found: {txt_path}")
        return
    text = txt_path.read_text()
    pdf_path = txt_path.with_suffix(".pdf")
    company = txt_path.stem.split("_")[1] if "_" in txt_path.stem else "Unknown"
    _save_cover_letter_pdf(text, pdf_path, company)
    print(f"PDF saved: {pdf_path}")


def main():
    parser = argparse.ArgumentParser(description="Job application prep via Claude API")
    parser.add_argument("--url",     help="Single job URL to prep")
    parser.add_argument("--list",    action="store_true", help="Process all URLs in jobs.txt")
    parser.add_argument("--no-cl",   action="store_true", help="Skip cover letter generation")
    parser.add_argument("--to-pdf",  help="Convert an existing covers/*.txt to PDF (no API call)",
                        metavar="FILE")
    args = parser.parse_args()

    if args.to_pdf:
        convert_to_pdf(Path(args.to_pdf))
    elif args.list:
        urls = load_jobs()
        if not urls:
            print("No URLs found in jobs.txt")
            return
        for url in urls:
            run_prep(url, skip_cl=args.no_cl)
    elif args.url:
        run_prep(args.url, skip_cl=args.no_cl)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
