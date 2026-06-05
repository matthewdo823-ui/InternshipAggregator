# Job Scraper — LinkedIn Lead Magnet Engine

Scrapes job listings from multiple sources, deduplicates them, and outputs a CSV you can publish as a Google Sheet. Pair with the email sender to automatically send your resource to LinkedIn commenters.

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure your niche and sources
nano config/config.yaml

# 3. Run
python main.py
```

## Usage

```bash
# Run default niche (set in config.yaml)
python main.py

# Override niche on the fly
python main.py --niche engineering
python main.py --niche product_management
python main.py --niche finance
python main.py --niche general

# Only use specific sources
python main.py --sources greenhouse lever

# Preview without saving
python main.py --dry-run

# Custom output file
python main.py --output output/engineering_2027.csv
```

## Email Sending

After publishing your LinkedIn post, collect emails from comments:

1. Scroll through post comments, copy all the text into a `.txt` file
2. Run:

```bash
# First: enable email in config.yaml and fill in your details
# Then: set up Gmail API credentials (see email_sender.py header)

python email_sender.py comments.txt
```

The script extracts all valid email addresses from the text and sends your resource link.

## Switching Niches

Edit `config/config.yaml`:

```yaml
active_niche: product_management  # engineering | pm | finance | general
```

Or pass `--niche` at runtime to test multiple niches without changing config.

## ATS Sources

- **Greenhouse** / **Lever** / **Ashby** / **Workday** — public job board APIs; board lists in `scrapers/greenhouse.py`, `scrapers/lever.py`, `scrapers/ashby.py`, `scrapers/workday.py`

## GitHub List Sources

Curated internship READMEs are scraped automatically:

- [jobright-ai/2026-Product-Management-Internship](https://github.com/jobright-ai/2026-Product-Management-Internship) — PM/co-op roles (`jobright_github` source; runs for `product_management` and `general` niches)
- [SimplifyJobs/Summer2026-Internships](https://github.com/SimplifyJobs/Summer2026-Internships) — SWE, PM, quant, hardware, and ML sections (`simplify_github` source)

## Startup job boards

- [Y Combinator Work at a Startup](https://www.workatastartup.com) — `yc_jobs` (Inertia JSON on role category pages)
- [Wellfound](https://wellfound.com) — `wellfound` (Playwright browser; set `headless: false` in config — DataDome blocks headless automation)

### Wellfound setup (Playwright)

```bash
pip install playwright
python -m playwright install chromium
```

In `config.yaml`, keep `sources.wellfound.headless: false` for reliable results (opens a visible Chromium window briefly). On Linux servers without a display, use `xvfb-run python main.py --sources wellfound`.

To reuse a logged-in session (optional, improves reliability):

```bash
playwright codegen https://wellfound.com --save-storage=config/wellfound_auth.json
# Log in manually, then close the browser window
```

Then uncomment `storage_state: config/wellfound_auth.json` in `config.yaml`.

## Adding New Sources

1. Create `scrapers/mysite.py`
2. Subclass `BaseScraper`
3. Implement `scrape()` returning `list[Job]`
4. Import and register in `main.py`

See `scrapers/greenhouse.py` for a clean example.

## Adding Companies to Greenhouse/Lever

In `scrapers/greenhouse.py`, add slugs to the relevant niche list:

```python
ENGINEERING_COMPANIES = [
    "airbnb", "figma", "your-new-company",  # ← add here
    ...
]
```

Find a company's slug at `boards.greenhouse.io/{slug}` or `jobs.lever.co/{slug}`.

## Automation (Daily Updates)

To run daily via cron:

```bash
# Run every morning at 7am
0 7 * * * cd /path/to/job-scraper && python main.py >> logs/cron.log 2>&1
```

Then use a Google Sheets script to auto-import the CSV, or push directly via the Sheets API.
# InternshipAggregator
