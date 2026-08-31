# LinkedIn Profile API

A hosted API that accepts a LinkedIn profile URL and returns structured profile data, built by reverse-engineering LinkedIn's internal request/response mechanisms — no browser automation involved in the deployed service.

## Live API

`POST https://linkedin-profile-api-oy0e.onrender.com/profile`

(Note: hosted on Render's free tier, which spins down after inactivity — the first request after idle time may take 30–60s to respond while the service wakes up.)

## Deployment (Render)

1. Push this repo to GitHub.
2. On Render, create a new **Web Service** connected to the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT` (already declared in the `Procfile`).
5. Add `LINKEDIN_LI_AT` and `LINKEDIN_JSESSIONID` as environment variables in Render's dashboard — never in the repo.
6. Deploy. Render provisions HTTPS automatically.

## API Documentation

### `GET /health`

Returns `{"status": "ok"}`. Used for uptime checks.

### `POST /profile`

**Request body:**
```json
{ "profile_url": "https://www.linkedin.com/in/sundarpichai/" }
```
(A bare public identifier like `"sundarpichai"` also works.)

**Response (200):**
```json
{
  "public_identifier": "sundarpichai",
  "profile_url": "https://www.linkedin.com/in/sundarpichai/",
  "name": "Sundar Pichai",
  "headline": "CEO at Google",
  "location": "Mountain View, California, United States",
  "current_company": "Google",
  "current_school": "The Wharton School",
  "follower_count": 5093728,
  "connections_count": null,
  "profile_image_url": "https://...",
  "cover_image_url": "https://...",
  "experience": [
    { "title": "CEO", "company": "Google", "dates": "2015 – Present" }
  ],
  "about": null,
  "education": null,
  "skills": null,
  "certifications": null,
  "languages": null,
  "_known_limitations": "..."
}
```

**Error responses:**
- `404` — profile doesn't exist
- `422` — profile is private/restricted, or the backing LinkedIn session has expired

## Setup Instructions

1. Clone the repo and create a virtual environment:
   ```
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Obtain your LinkedIn session cookies:
   - Log into a LinkedIn account (a secondary/throwaway account is strongly recommended — see Known Limitations for why) in a normal browser.
   - Open DevTools → Application → Cookies → `https://www.linkedin.com`.
   - Copy the values of `li_at` and `JSESSIONID` (keep the surrounding quotes on `JSESSIONID`).

3. Create a `.env` file in the project root:
   ```
   LINKEDIN_LI_AT=<your li_at value>
   LINKEDIN_JSESSIONID=<your JSESSIONID value, quotes included>
   ```
   Never commit this file — it's already in `.gitignore`.

4. Run locally:
   ```
   uvicorn main:app --reload
   ```

5. Test:
   ```
   curl -X POST http://localhost:8000/profile \
     -H "Content-Type: application/json" \
     -d '{"profile_url": "https://www.linkedin.com/in/sundarpichai/"}'
   ```

## Approach

LinkedIn's current (2026) web app is server-driven — the profile page's HTML embeds most of its content directly as literal text rather than requiring a separate REST/GraphQL fetch for everything, which meant the classic "hit `/voyager/api/...`" approach wasn't the whole story.

The investigation, roughly in order:
1. **Authentication**: LinkedIn's session is carried by two cookies — `li_at` (session identity) and `JSESSIONID` (echoed back as a `csrf-token` header). A plain `requests.get()` carrying both, with a realistic `User-Agent`, is treated identically to a logged-in browser request.
2. **Topcard fields** (name, headline, location, current company/school, follower count, images): confirmed to be plain, literal text in the initial HTML response for *any* profile — no JavaScript execution needed.
3. **Experience**: on the main profile page this section is lazy-loaded client-side and returns empty on a raw fetch. However, LinkedIn's dedicated `/in/<id>/details/experience/` subpage renders full experience history server-side, so hitting that URL directly recovers complete job history.
4. **Education, Skills, Certifications, Languages, About**: tested the same "dedicated subpage" trick — it does **not** generalize. These sections remain lazy-loaded even on their own subpages, fetched via an internal endpoint (`POST /flagship-web/rsc-action/actions/component`) that requires several session-scoped tracking headers and a JSON payload whose exact schema isn't discoverable without deeper protocol reverse-engineering. A second attempt via the "Save to PDF" feature was traced to the same underlying `rsc-action` system (a `server-request` action variant), confirming this is an architectural boundary, not a one-off gap — both independent paths into extra profile data terminate at the same session-bound, undocumented mechanism.

## Known Limitations

- **About, Education, Skills, Certifications, Languages are not returned.** These are lazy-loaded by LinkedIn's client through an internal, session-authenticated action-dispatch endpoint that a stateless HTTP client cannot fully replicate (see Approach above). Notably, even PhantomBuster's own referenced LinkedIn Profile Scraper doesn't cover this depth either — profile pictures, full work history, skills, and endorsements are explicitly split into a separate product tier ("LinkedIn Profile Visitor") in their own documentation.
- **Experience parsing is heuristic**, based on the visual text ordering of two observed profile layouts (single-role and multi-role-per-company). A small number of entries may show `"company": null` where LinkedIn's grouping structure doesn't match either pattern exactly.
- **Requires a live, valid LinkedIn session.** `li_at`/`JSESSIONID` values expire and must be refreshed periodically by logging in again.
- **Account risk**: using a real LinkedIn session for automated requests violates LinkedIn's Terms of Service. A secondary/throwaway account is strongly recommended over a primary one, since LinkedIn does enforce against this pattern (account restrictions, not legal action, are the realistic risk for individual use at this scale).
- **No retry/backoff logic** for rate limiting is implemented; sustained high-volume use would need it.
