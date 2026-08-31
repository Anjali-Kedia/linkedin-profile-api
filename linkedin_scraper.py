import base64
import json
import os
import re

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BASE_HEADERS = {
    "Cookie": (
        f"li_at={os.environ.get('LINKEDIN_LI_AT')}; "
        f"JSESSIONID={os.environ.get('LINKEDIN_JSESSIONID')}"
    ),
    "csrf-token": os.environ.get("LINKEDIN_JSESSIONID"),
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

DURATION_ONLY_RE = re.compile(r"^\d+\s*(yrs?|mos?)(\s+\d+\s*mos?)?$")
DATE_RANGE_RE = re.compile(r"\b\d{4}\b.*(–|-).*(\b\d{4}\b|\bPresent\b)")
PRONOUN_TAGS = {"she/her", "he/him", "they/them"}


class ProfileNotFound(Exception):
    pass


class ProfilePrivateOrBlocked(Exception):
    pass


def extract_public_id(profile_url_or_id):
    """Accepts either a full LinkedIn profile URL or a bare public identifier."""
    match = re.search(r"linkedin\.com/in/([^/?]+)", profile_url_or_id)
    if match:
        return match.group(1)
    return profile_url_or_id.strip("/")


def fetch_html(url):
    response = requests.get(url, headers=BASE_HEADERS)
    response.encoding = "utf-8"
    return response


def parse_topcard(html):
    soup = BeautifulSoup(html, "html.parser")
    topcard = soup.find(id=re.compile(r"Topcard$"))
    if topcard is None:
        return None

    texts = list(topcard.stripped_strings)
    if not texts:
        return None

    result = {
        "name": texts[0],
        "headline": None,
        "location": None,
        "current_company": None,
        "current_school": None,
        "follower_count": None,
        "connections_count": None,
    }

    idx = 1
    # skip a pronoun tag if present (e.g. "She/Her") right after the name
    if idx < len(texts) and texts[idx].strip().lower() in PRONOUN_TAGS:
        idx += 1

    # next item is the headline, whatever it is
    if idx < len(texts):
        result["headline"] = texts[idx]
        idx += 1

    # next item is usually a combined "Company · School" summary line — skip it
    if idx < len(texts) and "·" in texts[idx]:
        idx += 1

    # next item is location
    if idx < len(texts) and texts[idx] != "Contact info":
        result["location"] = texts[idx]
        idx += 1

    # find "Contact info" anchor; clean company/school pills follow it
    try:
        contact_idx = texts.index("Contact info", idx)
    except ValueError:
        contact_idx = None

    if contact_idx is not None:
        pills = []
        for t in texts[contact_idx + 1:]:
            if t in ("Message", "More", "Follow", "Connect", "Open to work", "Show details") or t.endswith("more"):
                break
            if re.match(r"^[\d,]+\+?$", t) or t in ("followers", "connections"):
                continue
            pills.append(t)
        if len(pills) >= 1:
            result["current_company"] = pills[0]
        if len(pills) >= 2:
            result["current_school"] = pills[1]

    # follower / connection counts can appear anywhere in the remaining text
    for i, t in enumerate(texts):
        m = re.match(r"^([\d,]+)\s+followers?$", t)
        if m:
            result["follower_count"] = int(m.group(1).replace(",", ""))
        elif re.match(r"^[\d,]+\+?$", t) and i + 1 < len(texts) and texts[i + 1] == "connections":
            result["connections_count"] = t

    # images
    profile_img = topcard.find("img", attrs={"alt": ""})
    cover_img = topcard.find("img", attrs={"alt": "Cover photo"})
    result["profile_image_url"] = profile_img["src"] if profile_img else None
    result["cover_image_url"] = cover_img["src"] if cover_img else None

    return result


def parse_experience(html):
    """Returns a flat list of {title, company, dates} entries.

    Handles two layouts observed in practice:
    - grouped: Company header, total duration, then per-role "Title" / "dates"
      pairs (multiple roles at one company, company stated once)
    - ungrouped: per-role "Title" / "Company · Type" / "dates" triples
      (single role per company, company restated each time)
    """
    soup = BeautifulSoup(html, "html.parser")
    section = soup.find(id=re.compile(r"ExperienceDetailsSection$"))
    if section is None:
        return []

    texts = list(section.stripped_strings)
    if texts and texts[0] == "Experience":
        texts = texts[1:]

    entries = []
    last_company_header = None
    for i, t in enumerate(texts):
        if DURATION_ONLY_RE.match(t) and i >= 1:
            # previous item was a company header in the grouped layout
            last_company_header = texts[i - 1]
            continue

        if DATE_RANGE_RE.search(t):
            prev1 = texts[i - 1] if i >= 1 else None
            prev2 = texts[i - 2] if i >= 2 else None
            if prev1 and "·" in prev1 and not DURATION_ONLY_RE.match(prev1):
                title, company = prev2, prev1
            else:
                title, company = prev1, last_company_header
            if title:
                entries.append({"title": title, "company": company, "dates": t})

    return entries


def scrape_profile(profile_url_or_id):
    public_id = extract_public_id(profile_url_or_id)

    main_response = fetch_html(f"https://www.linkedin.com/in/{public_id}/")
    if main_response.status_code == 404:
        raise ProfileNotFound(public_id)
    if main_response.status_code != 200 or "rehydrate-data" not in main_response.text:
        raise ProfilePrivateOrBlocked(public_id)

    topcard_data = parse_topcard(main_response.text)

    exp_response = fetch_html(f"https://www.linkedin.com/in/{public_id}/details/experience/")
    experience_data = parse_experience(exp_response.text) if exp_response.status_code == 200 else []

    return {
        "public_identifier": public_id,
        "profile_url": f"https://www.linkedin.com/in/{public_id}/",
        **(topcard_data or {}),
        "experience": experience_data,
        "about": None,
        "education": None,
        "skills": None,
        "certifications": None,
        "languages": None,
        "_known_limitations": (
            "about, education, skills, certifications, and languages are not "
            "available via this implementation; LinkedIn lazy-loads these "
            "sections through a session-authenticated internal RPC mechanism "
            "that could not be replicated with a stateless HTTP client. "
            "See README for details."
        ),
    }


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "sundarpichai"
    data = scrape_profile(target)
    print(json.dumps(data, indent=2, ensure_ascii=False))
