"""
Greenhouse form filler.

Greenhouse applications are single-page forms with relatively predictable
field structure. This module maps profile data to Greenhouse form fields
and handles file uploads.

Field identification strategy:
- Greenhouse uses <input>, <select>, and <textarea> elements
- Fields are identified by: id, name, label text, aria-label, autocomplete attr
- File uploads use <input type="file"> with accept filters
- Custom questions vary per company but usually have descriptive labels
"""

import asyncio
import logging
from pathlib import Path
from playwright.async_api import Page, Locator

logger = logging.getLogger(__name__)


# Maps our profile keys to common Greenhouse field identifiers.
# Each entry is a list of possible selectors to try in order.
FIELD_MAP = {
    "first_name": [
        'input[name="first_name"]',
        'input[id*="first_name"]',
        'input[autocomplete="given-name"]',
    ],
    "last_name": [
        'input[name="last_name"]',
        'input[id*="last_name"]',
        'input[autocomplete="family-name"]',
    ],
    "email": [
        'input[name="email"]',
        'input[id*="email"]',
        'input[type="email"]',
        'input[autocomplete="email"]',
    ],
    "phone": [
        'input[name="phone"]',
        'input[id*="phone"]',
        'input[type="tel"]',
        'input[autocomplete="tel"]',
    ],
    "location_city": [
        'input[name*="location"]',
        'input[id*="location"]',
        'input[id*="city"]',
        'input[autocomplete="address-level2"]',
    ],
    "linkedin": [
        'input[name*="linkedin"]',
        'input[id*="linkedin"]',
        'input[aria-label*="LinkedIn"]',
    ],
    "website": [
        'input[name*="website"]',
        'input[id*="website"]',
        'input[aria-label*="Website"]',
        'input[aria-label*="website"]',
    ],
    "github": [
        'input[name*="github"]',
        'input[id*="github"]',
        'input[aria-label*="GitHub"]',
    ],
}

# For select dropdowns (work auth, sponsorship, etc.)
SELECT_MAP = {
    "authorized_us": {
        "selectors": [
            'select[id*="authorized"]',
            'select[id*="authorization"]',
        ],
        "label_patterns": [
            "authorized to work",
            "legally authorized",
            "work authorization",
            "authorized to work in the united states",
        ],
        "value_map": {"Yes": "Yes", "No": "No"},
    },
    "needs_sponsorship": {
        "selectors": [
            'select[id*="sponsor"]',
            'select[id*="visa"]',
        ],
        "label_patterns": [
            "sponsorship",
            "require sponsorship",
            "visa sponsorship",
        ],
        "value_map": {"Yes": "Yes", "No": "No"},
    },
    "gender": {
        "selectors": ['select[id*="gender"]'],
        "label_patterns": ["gender"],
        "value_map": {"Male": "Male", "Female": "Female", "": "Decline"},
    },
    "hispanic_latino": {
        "selectors": ['select[id*="hispanic"]', 'select[id*="latino"]'],
        "label_patterns": ["hispanic", "latino"],
        "value_map": {"Yes": "Yes", "No": "No"},
    },
    "race": {
        "selectors": ['select[id*="race"]', 'select[id*="ethnicity"]'],
        "label_patterns": ["race", "ethnicity"],
        "value_map": {
            "Asian": "Asian",
            "White": "White",
            "Black": "Black or African American",
            "Hispanic": "Hispanic or Latino",
            "": "Decline To Self Identify",
        },
    },
    "veteran": {
        "selectors": ['select[id*="veteran"]'],
        "label_patterns": ["veteran"],
        "value_map": {"Yes": "Yes", "No": "No", "": "Decline"},
    },
    "disability": {
        "selectors": ['select[id*="disabilit"]'],
        "label_patterns": ["disability"],
        "value_map": {"Yes": "Yes", "No": "No", "": "Decline"},
    },
}


async def find_and_fill_input(page: Page, selectors: list[str], value: str) -> bool:
    """Try each selector until one matches, then fill the field."""
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0 and await locator.is_visible():
                await locator.click()
                await locator.fill(value)
                logger.info(f"Filled {selector} with '{value[:30]}...'")
                return True
        except Exception:
            continue
    return False


async def find_and_select(page: Page, field_config: dict, value: str) -> bool:
    """Try to find a select dropdown and choose the right option."""
    if not value:
        return False

    mapped_value = field_config["value_map"].get(value, value)

    # Try direct selectors first
    for selector in field_config["selectors"]:
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0 and await locator.is_visible():
                # Get all options and find best match
                options = await locator.locator("option").all_text_contents()
                best_match = None
                for opt in options:
                    if mapped_value.lower() in opt.lower() or opt.lower() in mapped_value.lower():
                        best_match = opt
                        break
                if best_match:
                    await locator.select_option(label=best_match)
                    logger.info(f"Selected '{best_match}' for {selector}")
                    return True
        except Exception:
            continue

    # Fallback: search by label text
    for pattern in field_config["label_patterns"]:
        try:
            # Find label containing the pattern, then find its associated select
            labels = page.locator(f"label:has-text('{pattern}')")
            if await labels.count() > 0:
                label = labels.first
                for_attr = await label.get_attribute("for")
                if for_attr:
                    select = page.locator(f"select#{for_attr}")
                    if await select.count() > 0:
                        options = await select.locator("option").all_text_contents()
                        for opt in options:
                            if mapped_value.lower() in opt.lower():
                                await select.select_option(label=opt)
                                logger.info(f"Selected '{opt}' via label '{pattern}'")
                                return True
        except Exception:
            continue

    return False


async def upload_file(page: Page, selector_patterns: list[str], file_path: str) -> bool:
    """Find a file input and upload a file to it."""
    path = Path(file_path)
    if not path.exists():
        logger.error(f"File not found: {file_path}")
        return False

    patterns = selector_patterns + [
        'input[type="file"]',
    ]

    for selector in patterns:
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                await locator.set_input_files(str(path))
                logger.info(f"Uploaded {path.name} via {selector}")
                return True
        except Exception:
            continue

    return False


async def fill_greenhouse_form(
    page: Page,
    profile: dict,
    resume_path: str,
    cover_letter_path: str | None = None,
    dry_run: bool = True,
) -> dict:
    """
    Fill a Greenhouse application form.

    Returns a dict with:
    - filled: list of fields successfully filled
    - skipped: list of fields that couldn't be found
    - submitted: bool (False if dry_run)
    """
    result = {"filled": [], "skipped": [], "submitted": False}

    # Wait for form to load
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)  # Greenhouse forms sometimes lazy-load

    # Fill text inputs
    for field_key, selectors in FIELD_MAP.items():
        value = profile.get(field_key, "")
        if not value:
            continue

        if await find_and_fill_input(page, selectors, value):
            result["filled"].append(field_key)
        else:
            result["skipped"].append(field_key)
            logger.warning(f"Could not find field for: {field_key}")

    # Handle select dropdowns
    for field_key, config in SELECT_MAP.items():
        value = profile.get(field_key, "")
        if await find_and_select(page, config, value):
            result["filled"].append(field_key)
        else:
            if value:  # Only log as skipped if we had a value to set
                result["skipped"].append(field_key)

    # Upload resume
    resume_selectors = [
        'input[type="file"][id*="resume"]',
        'input[type="file"][name*="resume"]',
        'input[type="file"][accept*="pdf"]',
    ]
    if await upload_file(page, resume_selectors, resume_path):
        result["filled"].append("resume")
    else:
        result["skipped"].append("resume")
        logger.error("CRITICAL: Could not upload resume")

    # Upload cover letter if provided
    if cover_letter_path:
        cl_selectors = [
            'input[type="file"][id*="cover"]',
            'input[type="file"][name*="cover"]',
        ]
        # Greenhouse often has a second file input for cover letters
        # If the first file input was used for resume, try the second one
        all_file_inputs = page.locator('input[type="file"]')
        count = await all_file_inputs.count()
        if count >= 2:
            try:
                await all_file_inputs.nth(1).set_input_files(cover_letter_path)
                result["filled"].append("cover_letter")
                logger.info(f"Uploaded cover letter via second file input")
            except Exception:
                if await upload_file(page, cl_selectors, cover_letter_path):
                    result["filled"].append("cover_letter")
                else:
                    result["skipped"].append("cover_letter")
        else:
            if await upload_file(page, cl_selectors, cover_letter_path):
                result["filled"].append("cover_letter")
            else:
                result["skipped"].append("cover_letter")

    # Handle the location autocomplete (Greenhouse uses a location picker)
    try:
        loc_input = page.locator('input[id*="location"], input[name*="location"]').first
        if await loc_input.count() > 0:
            city = profile.get("location_city", "")
            if city:
                await loc_input.fill(city)
                await asyncio.sleep(1)
                # Try to click first autocomplete suggestion
                suggestion = page.locator('[class*="suggestion"], [class*="autocomplete"] li, [role="option"]').first
                if await suggestion.count() > 0:
                    await suggestion.click()
                    logger.info("Selected location from autocomplete")
    except Exception as e:
        logger.warning(f"Location autocomplete handling failed: {e}")

    # Submit or dry-run
    if not dry_run:
        submit_btn = page.locator(
            'button[type="submit"], '
            'input[type="submit"], '
            'button:has-text("Submit"), '
            'button:has-text("Apply")'
        ).first
        if await submit_btn.count() > 0:
            await submit_btn.click()
            result["submitted"] = True
            logger.info("Application submitted!")
            await asyncio.sleep(3)
        else:
            logger.error("Could not find submit button")
    else:
        logger.info("DRY RUN: Form filled but not submitted")
        # Take a screenshot for review
        await page.screenshot(path="output/dry_run_screenshot.png", full_page=True)
        logger.info("Screenshot saved to output/dry_run_screenshot.png")

    return result
