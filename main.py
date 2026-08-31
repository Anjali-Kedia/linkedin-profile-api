from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from linkedin_scraper import ProfileNotFound, ProfilePrivateOrBlocked, scrape_profile

app = FastAPI(title="LinkedIn Profile API", version="1.0.0")


class ProfileRequest(BaseModel):
    profile_url: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/profile")
def get_profile(request: ProfileRequest):
    try:
        return scrape_profile(request.profile_url)
    except ProfileNotFound:
        raise HTTPException(status_code=404, detail="Profile not found")
    except ProfilePrivateOrBlocked:
        raise HTTPException(
            status_code=422,
            detail="Profile could not be read — it may be private, restricted, or our session may have expired.",
        )
