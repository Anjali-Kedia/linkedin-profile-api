# LinkedIn Profile API

A hosted API that takes a LinkedIn profile URL and returns structured profile data. Built by reverse-engineering LinkedIn's own internal requests — no browser automation in the deployed service.

## Live API

`POST https://linkedin-profile-api-oy0e.onrender.com/profile`

This runs on Render's free tier, which spins down after inactivity, so the first request after a while idle can take 30-60s to wake up.

## Deployment (Render)

1. Push this repo to GitHub.
2. Create a new Web Service on Render, connected to the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT` (also in the `Procfile`).
5. Add `LINKEDIN_LI_AT` and `LINKEDIN_JSESSIONID` as environment variables in Render's dashboard, not in the repo.
6. Deploy — Render handles HTTPS automatically.

## API

### `GET /health`

Returns `{"status": "ok"}`.

### `POST /profile`

Request body:
```json
{ "profile_url": "https://www.linkedin.com/in/sundarpichai/" }
```
A bare public identifier (`"sundarpichai"`) works too.

Response:
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
  "languages": null
}
```

Errors: `404` if the profile doesn't exist, `422` if it's private/restricted or the session cookie has expired.

## Setup

1. Clone the repo, then:
   ```
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Get your LinkedIn session cookies — log into an account in a normal browser (use a secondary account, not your main one, see limitations below), open DevTools → Application → Cookies → linkedin.com, and copy the `li_at` and `JSESSIONID` values. Keep the quotes on `JSESSIONID`.

3. Put them in a `.env` file in the project root:
   ```
   LINKEDIN_LI_AT=<your li_at value>
   LINKEDIN_JSESSIONID=<your JSESSIONID value, quotes included>
   ```
   This file is gitignored, don't commit it.

4. Run it:
   ```
   uvicorn main:app --reload
   ```

5. Try it:
   ```
   curl -X POST http://localhost:8000/profile \
     -H "Content-Type: application/json" \
     -d '{"profile_url": "https://www.linkedin.com/in/sundarpichai/"}'
   ```

## Approach

LinkedIn's current web app is server-driven — most of the profile page's content is embedded as literal text in the HTML response rather than fetched separately through a REST or GraphQL call, so hitting `/voyager/api/...` endpoints turned out not to be the whole story.

Authentication is just two cookies: `li_at` for session identity, and `JSESSIONID`, which also has to be echoed back as a `csrf-token` header on every request. A plain `requests.get()` carrying both, with a normal browser User-Agent, gets treated the same as a logged-in browser tab.

The topcard fields (name, headline, location, current company/school, follower count, both images) come straight out of the main profile page's HTML for any profile, no JS execution needed. Experience was trickier — it's lazy-loaded on the main page and comes back empty on a plain fetch, but LinkedIn's own `/in/<id>/details/experience/` subpage renders the full job history server-side, so hitting that directly gets the complete history.

That trick doesn't generalize to Education, Skills, Certifications, Languages, or About — those stay lazy-loaded even on their own dedicated subpages. They're fetched through an internal endpoint, `POST /flagship-web/rsc-action/actions/component`, that needs several session-scoped tracking headers and a JSON body whose exact shape isn't something I could reconstruct from the outside. I also traced LinkedIn's "Save to PDF" feature to confirm it wasn't a simpler path — it hits the same `rsc-action` system under a different action type, and got the same result. Two separate routes into that data, same wall both times.

## Known limitations

About, Education, Skills, Certifications, and Languages aren't returned, for the reason above — they sit behind a session-authenticated internal endpoint a stateless script can't fully replicate. For what it's worth, PhantomBuster's own LinkedIn Profile Scraper (the example linked in the brief) has the same gap in its base tier — no profile pictures, only the two most recent job positions, and skills/endorsements pushed into a separate paid product entirely.

Experience parsing is pattern-based rather than schema-based, since there's no documented format to work against. It's been checked against two profiles with different layouts (grouped multi-role and single-role-per-company), but a handful of unusually structured entries can still come back with `"company": null`.

The `li_at`/`JSESSIONID` cookies expire and need refreshing periodically. Using a real LinkedIn session for automated requests is against their Terms of Service, so this is built to use a secondary account rather than a primary one — the realistic risk is account restriction, not anything more serious, but it's still worth isolating.

No retry or backoff logic for rate limiting yet; would need it for higher volume use.
