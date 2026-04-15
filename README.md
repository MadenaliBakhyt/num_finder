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
    excel.py           # xlsx reader/writer for bulk lookup
frontend/
  index.html           # Single-page UI (single + bulk lookup)
requirements.txt
```

## Run locally

```bash
python -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Windows (cmd.exe):
.\.venv\Scripts\activate.bat

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

### Bulk lookup from Excel

`POST /search-excel` — multipart form upload, field name `file`, must be
`.xlsx`/`.xlsm`. Company names are read from the **first column**; header
rows (`Company`, `Компания`, `Общий итог`, ...) and blanks are skipped. The
server caps input at 100 rows.

Response:
```json
{
  "count": 2,
  "truncated": false,
  "rows": [
    { "company": "...", "website": "...", "phone": "..." }
  ]
}
```

`POST /export-excel` — accepts the same `rows` array and returns a generated
`.xlsx` file (used by the **Download results** button on the frontend).

`GET /health` → `{"status": "ok"}`

## Notes

- Requests have a 10s timeout and the scraper probes a bounded set of likely
  contact pages, so a single lookup is lightweight.
- Search results are filtered against a blocklist of aggregator/social domains
  (Wikipedia, LinkedIn, 2GIS, hh.kz, ...).
- All errors are logged but the endpoint never crashes — missing fields simply
  come back as `null`.
