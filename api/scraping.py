from fastapi import FastAPI
import os
import sys

# Add the parent directory to sys.path to import modules from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.scraper import ScrapingCache


app = FastAPI()
scraping_cache = ScrapingCache(refresh_interval_seconds=60)


@app.get("/")
@app.get("/api/scraping")
def scraping_endpoint(force: bool = False):
    scraping_cache.refresh(force)
    return scraping_cache.snapshot()
