"""
Job Auto-Apply: Main orchestrator.

Usage:
    python scripts/apply.py                          # Process all jobs in jobs.txt (dry run)
    python scripts/apply.py --dry-run                # Same as above, explicit dry run
    python scripts/apply.py --live                   # Actually submit applications
    python scripts/apply.py --url "https://..."      # Single job URL
    python scripts/apply.py --covers output/         # Attach cover letters from directory
    python scripts/apply.py --headless               # Run browser in background

The script:
1. Reads your profile from config/profile.txt
2. For each Greenhouse URL: opens the page, fills the form, uploads resume
3. Logs results to output/apply_log.csv
"""

import argparse
import asyncio
import csv
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# Add parent dir to path so we can import sibling modules
sys.path.insert(0, str(Path(__file__).parent))

from parse_profile import parse_profile
from greenhouse import fill_greenhouse_form

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def detect_platform(url: str) -> str:
    """Detect which ATS platform a URL belongs to."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    if "greenhouse" in domain or "greenhouse" in url:
        return "greenhouse"
    elif "workday" in domain or "myworkdayjobs" in domain:
        return "workday"
    elif "lever" in domain or "lever.co" in domain:
        return "lever"
    elif "taleo" in domain:
        return "taleo"
    elif "icims" in domain:
        return "icims"
    elif "bankofamerica" in domain:
        return "workday"  # BofA uses Workday
    elif "biospace" in domain:
        return "biospace"
    else:
        return "unknown"


def extract_company_name(url: str) -> str:
    """Try to extract a company name from the URL."""
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")

    if "greenhouse" in parsed.netloc:
        # Format: job-boards.greenhouse.io/COMPANY/jobs/ID
        if len(path_parts) >= 1:
            return path_parts[0]

    # Fallback: use domain
    return parsed.netloc.split(".")[0]


def find_cover_letter(covers_dir: str | None, company: str, url: str) -> str | None:
    """Look for a matching cover letter file in the covers directory."""
    if not covers_dir:
        return None

    covers_path = Path(covers_dir)
    if not covers_path.exists():
        return None

    company_lower = company.lower()

    # Try exact match first, then partial
    for pattern in [
        f"CoverLetter_{company}*.pdf",
        f"cover_letter_{company_lower}*.pdf",
        f"*{company_lower}*.pdf",
    ]:
        matches = list(covers_path.glob(pattern))
        if matches:
            return str(matches[0])

    return None


def load_jobs(jobs_file: str = "jobs.txt") -> list[str]:
    """Load job URLs from jobs.txt."""
    path = Path(jobs_file)
    if not path.exists():
        logger.error(f"No {jobs_file} found. Create it with one URL per line.")
        return []

    urls = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)

    return urls


def log_result(log_path: str, result: dict):
    """Append a result row to the CSV log."""
    path = Path(log_path)
    write_header = not path.exists()

    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "timestamp", "url", "company", "platform", "status",
            "fields_filled", "fields_skipped", "submitted", "notes"
        ])
        if write_header:
            writer.writeheader()
        writer.writerow(result)


async def process_greenhouse_job(
    page,
    url: str,
    profile: dict,
    resume_path: str,
    cover_letter_path: str | None,
    dry_run: bool,
) -> dict:
    """Process a single Greenhouse application."""
    company = extract_company_name(url)
    logger.info(f"Processing: {company} ({url})")

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception as e:
        return {
            "timestamp": datetime.now().isoformat(),
            "url": url,
            "company": company,
            "platform": "greenhouse",
            "status": "error",
            "fields_filled": "",
            "fields_skipped": "",
            "submitted": False,
            "notes": f"Failed to load page: {e}",
        }

    result = await fill_greenhouse_form(
        page=page,
        profile=profile,
        resume_path=resume_path,
        cover_letter_path=cover_letter_path,
        dry_run=dry_run,
    )

    return {
        "timestamp": datetime.now().isoformat(),
        "url": url,
        "company": company,
        "platform": "greenhouse",
        "status": "submitted" if result["submitted"] else ("dry_run" if dry_run else "error"),
        "fields_filled": ", ".join(result["filled"]),
        "fields_skipped": ", ".join(result["skipped"]),
        "submitted": result["submitted"],
        "notes": "",
    }


async def main():
    parser = argparse.ArgumentParser(description="Auto-apply to Greenhouse jobs")
    parser.add_argument("--url", help="Single job URL to apply to")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Fill forms but do not submit (default)")
    parser.add_argument("--live", action="store_true",
                        help="Actually submit applications")
    parser.add_argument("--covers", help="Directory containing cover letter PDFs")
    parser.add_argument("--headless", action="store_true",
                        help="Run browser in headless mode (no visible window)")
    parser.add_argument("--jobs-file", default="jobs.txt",
                        help="Path to file with job URLs")
    parser.add_argument("--profile", default="config/profile.txt",
                        help="Path to profile.txt")
    parser.add_argument("--delay", type=float, default=3.0,
                        help="Seconds to wait between applications")

    args = parser.parse_args()

    dry_run = not args.live

    if dry_run:
        logger.info("=== DRY RUN MODE (forms filled but NOT submitted) ===")
    else:
        logger.info("=== LIVE MODE (applications WILL be submitted) ===")
        response = input("Are you sure you want to submit applications? (yes/no): ")
        if response.lower() != "yes":
            logger.info("Aborted.")
            return

    # Load profile
    try:
        profile = parse_profile(args.profile)
    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        return

    # Resolve resume path
    config_dir = Path(args.profile).parent
    resume_path = str(config_dir / profile["resume_path"])
    if not Path(resume_path).exists():
        logger.error(f"Resume not found at {resume_path}")
        return

    logger.info(f"Profile loaded: {profile['first_name']} {profile['last_name']}")
    logger.info(f"Resume: {resume_path}")

    # Load job URLs
    if args.url:
        urls = [args.url]
    else:
        urls = load_jobs(args.jobs_file)

    if not urls:
        logger.error("No job URLs to process.")
        return

    # Separate by platform
    greenhouse_urls = []
    other_urls = []

    for url in urls:
        platform = detect_platform(url)
        if platform == "greenhouse":
            greenhouse_urls.append(url)
        else:
            other_urls.append((url, platform))

    if other_urls:
        logger.info(f"\n{'='*60}")
        logger.info("NON-GREENHOUSE JOBS (manual application required):")
        logger.info(f"{'='*60}")
        for url, platform in other_urls:
            company = extract_company_name(url)
            logger.info(f"  [{platform.upper()}] {company}: {url}")
            log_result("output/apply_log.csv", {
                "timestamp": datetime.now().isoformat(),
                "url": url,
                "company": company,
                "platform": platform,
                "status": "manual_required",
                "fields_filled": "",
                "fields_skipped": "",
                "submitted": False,
                "notes": f"Platform '{platform}' not supported for automation. "
                         f"Use the Claude skill for cover letter + fit analysis.",
            })
        logger.info(f"\nUse the Claude skill to generate briefs for these roles.")

    if not greenhouse_urls:
        logger.info("No Greenhouse URLs to process.")
        return

    logger.info(f"\nProcessing {len(greenhouse_urls)} Greenhouse application(s)...")

    # Launch browser
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=args.headless,
            slow_mo=500,  # Slow down actions so sites don't flag us
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        page = await context.new_page()

        for i, url in enumerate(greenhouse_urls):
            company = extract_company_name(url)
            cover_letter = find_cover_letter(args.covers, company, url)

            if cover_letter:
                logger.info(f"Found cover letter: {cover_letter}")

            result = await process_greenhouse_job(
                page=page,
                url=url,
                profile=profile,
                resume_path=resume_path,
                cover_letter_path=cover_letter,
                dry_run=dry_run,
            )

            log_result("output/apply_log.csv", result)

            status = result["status"]
            filled = len(result["fields_filled"].split(", ")) if result["fields_filled"] else 0
            skipped = len(result["fields_skipped"].split(", ")) if result["fields_skipped"] else 0

            logger.info(
                f"[{i+1}/{len(greenhouse_urls)}] {company}: "
                f"{status} (filled: {filled}, skipped: {skipped})"
            )

            # Wait between applications
            if i < len(greenhouse_urls) - 1:
                logger.info(f"Waiting {args.delay}s before next application...")
                await asyncio.sleep(args.delay)

        await browser.close()

    logger.info(f"\nResults logged to output/apply_log.csv")
    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
