# Job Application Prep

Research a job posting, get a fit analysis, humanized cover letter, and study
guide — all in one command. Uses Claude with live web search.

For form filling, use [Simplify](https://simplify.jobs) (browser extension).

## How it works

```
python scripts/prep.py --url "https://job-boards.greenhouse.io/..."
```

The script:
1. Fetches the job posting
2. Searches for recent company news (last 6 months — real specifics, not
   mission-statement language)
3. Maps your resume against the requirements
4. Writes a humanized cover letter grounded in your actual experience
5. Builds a study guide for the interview
6. Saves everything to `covers/` and `output/`

## Setup

```bash
# Clone
git clone https://github.com/arnavnair229/Auto-Job
cd job-auto-apply

# Install
pip install -r requirements.txt

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...
```

Drop your resume PDF at `config/resume.pdf` (gitignored, never pushed).
Update `skill/references/resume_context.md` with your experience.

## Usage

```bash
# Single job
python scripts/prep.py --url "https://..."

# All jobs in jobs.txt
python scripts/prep.py --list

# Skip cover letter (just the brief)
python scripts/prep.py --url "https://..." --no-cl
```

## Output

```
covers/
  CoverLetter_{Company}_{timestamp}.txt   ← convert to PDF before uploading
output/
  {Company}_{timestamp}_brief.md          ← full brief: fit matrix, gaps, study guide
```

## Structure

```
job-auto-apply/
├── jobs.txt                          # Job URLs (one per line, # = comment)
├── scripts/
│   └── prep.py                       # The script
├── config/
│   ├── profile.txt                   # Your info (gitignored)
│   ├── profile.txt.example           # Template
│   └── resume.pdf                    # Your resume (gitignored)
├── covers/                           # Generated cover letters (gitignored)
├── output/                           # Full briefs (gitignored)
└── skill/
    ├── SKILL.md                      # Claude Code skill (manual use)
    └── references/
        ├── profile.md
        └── resume_context.md         # Structured resume — edit this
```

## For a friend

1. Fork the repo
2. Copy `config/profile.txt.example` to `config/profile.txt` and fill it in
3. Drop your `resume.pdf` in `config/`
4. Rewrite `skill/references/resume_context.md` with your experience
5. Set `ANTHROPIC_API_KEY` and run
