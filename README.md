# Job Auto-Apply

Automated job application tool for Greenhouse-based job postings. Uses
Playwright to fill and submit applications, with pre-generated cover letters
and fit analysis powered by Claude.

## How it works

1. You put job URLs in `jobs.txt` (one per line)
2. The script fetches each posting, fills in your profile data, attaches
   your resume, and optionally attaches a cover letter
3. For Greenhouse jobs: fully automated submit
4. For non-Greenhouse jobs (Workday, Taleo, etc.): generates an application
   brief with cover letter that you fill in manually

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+ (for Playwright)
- A resume PDF in the `config/` directory

### Install

```bash
# Clone the repo
git clone <your-repo-url>
cd job-auto-apply

# Install Python dependencies
pip install playwright beautifulsoup4 requests

# Install Playwright browsers
playwright install chromium

# (Optional) If you want Claude-generated cover letters via CLI:
# Install Claude Code: npm install -g @anthropic-ai/claude-code
```

### Configure your profile

Edit `config/profile.txt` with your information. Every field matters.
The script reads this file to fill application forms.

```bash
cp config/profile.txt.example config/profile.txt
# Edit config/profile.txt with your details
```

Place your resume PDF at `config/resume.pdf`.

### Add jobs

Add Greenhouse job URLs to `jobs.txt`, one per line:

```
https://job-boards.greenhouse.io/schonfeld/jobs/7402926
https://job-boards.greenhouse.io/citadel/jobs/1234567
```

Lines starting with `#` are ignored (use for notes or skipped jobs).

### Run

```bash
# Dry run (fills forms but does NOT submit)
python scripts/apply.py --dry-run

# Live run (actually submits)
python scripts/apply.py

# Single job
python scripts/apply.py --url "https://job-boards.greenhouse.io/company/jobs/12345"

# With cover letter directory
python scripts/apply.py --covers output/
```

## Directory structure

```
job-auto-apply/
├── README.md
├── jobs.txt                  # Your job URLs (one per line)
├── config/
│   ├── profile.txt           # Your personal info (you edit this)
│   ├── profile.txt.example   # Template for friends
│   └── resume.pdf            # Your resume (you add this)
├── scripts/
│   ├── apply.py              # Main automation script
│   ├── greenhouse.py         # Greenhouse form filler
│   └── parse_profile.py      # Profile parser
└── output/
│   └── (cover letters and briefs go here)
└── skill/
    ├── SKILL.md              # Claude skill for cover letters + fit analysis
    └── references/
        ├── profile.md        # Claude-readable profile (auto-generated)
        └── resume_context.md # Structured resume data
```

## For friends / other users

1. Fork or clone this repo
2. Replace `config/profile.txt` with your own info
3. Replace `config/resume.pdf` with your resume
4. Edit `skill/references/resume_context.md` with your own experience
5. Edit `skill/references/profile.md` to match your profile.txt
6. Add your job URLs to `jobs.txt`
7. Run `python scripts/apply.py --dry-run` to test

## Limitations

- Only automates Greenhouse applications (single-page forms)
- Does NOT handle: Workday, Taleo, iCIMS, Lever login-required portals,
  or any multi-step authenticated flows
- Cover letter generation requires Claude Code CLI or manual use of the
  Claude skill in claude.ai
- The script runs headful (visible browser) by default so you can watch
  and intervene if something goes wrong
- Some Greenhouse boards have custom fields not covered by the default
  mapping. The script will skip those and log them for you to fill manually.

## Generating cover letters with Claude

If you have Claude Code installed:

```bash
# Generate a cover letter for a specific role
claude -p "Read the skill at skill/SKILL.md then generate a cover letter
for this role: <URL>. Use my profile from skill/references/profile.md
and resume from skill/references/resume_context.md."
```

Or use the skill in claude.ai by installing `job-apply-prep.skill`.
