"""
Parse profile.txt into a dictionary.
Simple key = value format, ignores comments and blank lines.
"""

from pathlib import Path


def parse_profile(profile_path: str = "config/profile.txt") -> dict:
    """Parse a profile.txt file into a flat dictionary."""
    profile = {}
    path = Path(profile_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Profile not found at {profile_path}. "
            f"Copy config/profile.txt.example to config/profile.txt and fill it in."
        )

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            # Skip comments and blank lines
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue

            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            if value:  # Only store non-empty values
                profile[key] = value

    # Validate required fields
    required = ["first_name", "last_name", "email", "phone", "resume_path"]
    missing = [f for f in required if f not in profile]
    if missing:
        raise ValueError(
            f"Missing required fields in profile.txt: {', '.join(missing)}"
        )

    return profile


if __name__ == "__main__":
    import json
    p = parse_profile()
    print(json.dumps(p, indent=2))
