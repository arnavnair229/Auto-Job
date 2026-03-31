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

# ── system prompt ─────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    resume = RESUME_CONTEXT.read_text() if RESUME_CONTEXT.exists() else "(no resume context found)"
    return f"""You are a job application strategist for a quantitative finance professional.
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

### 6. Cover Letter
A full cover letter, 250-400 words. Structure:
- Opening: state the role, one specific company fact from your research (NOT generic mission-statement
  language). No "I am writing to express my interest."
- Body 1: strongest relevant experience mapped to the role's primary responsibility. Name the tool,
  model, or result. Source everything from resume context.
- Body 2: second angle of fit — different skill dimension or side project.
- Closing: what you want to do in the role. Concrete next step, no "I look forward to hearing from you."

Writing rules (non-negotiable):
- No em dashes anywhere
- No "I am passionate about" or "I am excited to"
- No "leverage", "utilize", "spearhead", "drive", "foster", "impactful"
- No rule-of-three constructions
- No sentences starting with "Furthermore", "Moreover", "Additionally"
- No generic closers
- Every claim must trace back to the resume context. If you can't source it, don't write it.
- Write like a real 22-year-old quant writing a professional email, not a career-center template.

### 7. Study Guide
What to review before a phone screen or interview for this specific role.
Organize by topic (e.g., "Portfolio risk metrics", "Factor models", "Python/SQL").
3-5 bullets per topic. Be specific — name the actual concepts, formulas, or tools.

### 8. "Why This Role" Talking Points
2-3 sentences the candidate can use in a recruiter screen or "why us" field.
Ground these in something specific from your company research. Sounds like a real person.

### 9. Red Flags / Honest Assessment
- Is the role too senior?
- Missing credential (MS/PhD required)?
- Geographic mismatch?
- Domain outside experience?
- Any other reason this might not be worth the time?

### 10. Recommendation
One line: Apply / Apply with caveats / Skip — and why.
"""


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
    parts = parsed.path.strip("/").split("/")
    if "greenhouse" in parsed.netloc and parts:
        return parts[0].title()
    return parsed.netloc.split(".")[0].title()


def run_prep(url: str, skip_cl: bool = False) -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        print("Run: export ANTHROPIC_API_KEY=your_key_here")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    company = extract_company_from_url(url)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    user_message = f"""Job posting URL: {url}

Please:
1. Use web_fetch to retrieve the full job description from that URL.
2. Use web_search to find 2-3 recent, specific facts about the company
   (last 6 months: news, product launches, fund performance, leadership changes, etc.).
   Do NOT use generic mission-statement facts. Find something real and recent.
3. Produce the full application brief as specified in your instructions.
{"Note: The user has asked to skip the cover letter for this run." if skip_cl else ""}
"""

    print(f"\n{'='*60}")
    print(f"Prepping: {company}")
    print(f"URL: {url}")
    print(f"{'='*60}\n")

    full_text = []

    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=build_system_prompt(),
        tools=[
            {"type": "web_search_20260209", "name": "web_search"},
            {"type": "web_fetch_20260209",  "name": "web_fetch"},
        ],
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for event in stream:
            if event.type == "content_block_delta":
                if event.delta.type == "text_delta":
                    chunk = event.delta.text
                    print(chunk, end="", flush=True)
                    full_text.append(chunk)

        final = stream.get_final_message()

    brief = "".join(full_text)

    # ── save full brief ───────────────────────────────────────────────────────
    brief_path = OUTPUT_DIR / f"{slugify(company)}_{timestamp}_brief.md"
    brief_path.write_text(
        f"# Application Brief: {company}\n"
        f"URL: {url}\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        + brief
    )
    print(f"\n\n{'='*60}")
    print(f"Brief saved to: {brief_path}")

    # ── extract and save cover letter ─────────────────────────────────────────
    if not skip_cl:
        cl_match = re.search(
            r"#{1,3}\s*6\.\s*Cover Letter\s*\n(.*?)(?=\n#{1,3}\s*7\.|\Z)",
            brief,
            re.DOTALL | re.IGNORECASE,
        )
        if cl_match:
            cl_text = cl_match.group(1).strip()
            cl_base = f"CoverLetter_{slugify(company)}_{timestamp}"
            # Always save txt as backup
            cl_path = COVERS_DIR / f"{cl_base}.txt"
            cl_path.write_text(cl_text)
            # Save as PDF if reportlab is available
            if HAS_REPORTLAB:
                pdf_path = COVERS_DIR / f"{cl_base}.pdf"
                _save_cover_letter_pdf(cl_text, pdf_path, company)
                print(f"Cover letter saved to: {pdf_path}")
            else:
                print(f"Cover letter saved to: {cl_path}")
                print("(Install reportlab for auto-PDF: pip install reportlab)")
        else:
            print("Note: Could not auto-extract cover letter section. Check the brief file.")

    # ── usage ─────────────────────────────────────────────────────────────────
    usage = final.usage
    input_cost  = usage.input_tokens  * 0.000005
    output_cost = usage.output_tokens * 0.000025
    print(f"\nTokens: {usage.input_tokens} in / {usage.output_tokens} out")
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
