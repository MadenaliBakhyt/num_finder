# num_finder

MVP web app that finds a company's official website and phone number from its name.

- **Backend:** FastAPI (Python)
- **Frontend:** plain HTML + vanilla JS
- **Search:** DuckDuckGo via `ddgs`
- **Scraping:** `requests` + `BeautifulSoup` (no Selenium)

## Project layout

```
backend/
  main.py              # FastAPI app + routes, serves the frontend
  services/
    search.py          # Company website finder (DuckDuckGo)
    parser.py          # Phone-number extractor
frontend/
  index.html           # Single-page UI
requirements.txt
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn backend.main:app --reload --port 8000
```

Open <http://localhost:8000> in a browser, type a company name, hit **Search**.

## API

`POST /search`

Request:
```json
{ "company": "TOO Ferronordic Kazakhstan" }
```

Response:
```json
{
  "company": "TOO Ferronordic Kazakhstan",
  "website": "https://ferronordic.kz",
  "phone": "+7 727 000 00 00"
}
```

`website` and/or `phone` can be `null` if nothing was found.

`GET /health` → `{"status": "ok"}`

## Notes

- Requests have a 10s timeout and the scraper probes a bounded set of likely
  contact pages, so a single lookup is lightweight.
- Search results are filtered against a blocklist of aggregator/social domains
  (Wikipedia, LinkedIn, 2GIS, hh.kz, ...).
- All errors are logged but the endpoint never crashes — missing fields simply
  come back as `null`.
