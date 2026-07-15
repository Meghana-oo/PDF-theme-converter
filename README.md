# PDF Dark Mode (Nocturne)

A side project that lets you upload a PDF and get a dark-mode version of it.

Two layers, matching the two approaches discussed:

1. **Instant preview (client-side)** — the frontend renders the PDF with
   PDF.js and applies a CSS `invert()` filter as a quick visual toggle.
   Fast, but it's just a display trick (doesn't touch the file).
2. **Real export (server-side)** — the backend (FastAPI + PyMuPDF) actually
   rewrites the PDF: fills a dark background behind the page content, erases
   the original text via redaction, and re-inserts it in a light color.
   The download is a genuinely new PDF, viewable dark anywhere.

## Project structure

```
pdf-dark-mode/
├── backend/
│   ├── app.py            # FastAPI server, PDF color-rewrite logic
│   └── requirements.txt
├── frontend/
│   └── index.html        # Single-file frontend, no build step
└── README.md
```

## Running it

### 1. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

This starts the API at `http://localhost:8000`. Check it's alive at
`http://localhost:8000/api/health`.

### 2. Frontend

No build step needed — it's a single HTML file. Just open it, or serve it
so `fetch()` calls behave normally:

```bash
cd frontend
python3 -m http.server 5500
```

Then visit `http://localhost:5500`. If you change the backend's host/port,
update the `API_BASE` constant near the top of the `<script>` tag in
`index.html`.

## How the color rewrite works (backend/app.py)

For each page:
1. Draw a dark rectangle **underneath** existing content (`overlay=False`)
   — this becomes the new page background.
2. Walk every text span on the page (`page.get_text("dict")`), which gives
   text content, font size, and bounding box for each run of text.
3. **Redact** (erase) each span's bounding box, filling it with the new
   background color so nothing is left behind.
4. **Re-insert** the same text at the same position/size in a light color.

Images are left untouched — `apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)`
explicitly protects them from the redaction pass, so photos won't get
whited out or inverted.

## Known limitations / good next steps

- **Font matching**: re-inserted text uses a fallback font (`helv`) rather
  than the PDF's original embedded font, since matching PyMuPDF's writer
  fonts to arbitrary embedded fonts is nontrivial. Text will look right in
  position/size but the typeface may shift slightly. A next step is
  extracting the original font via `page.get_fonts()` and passing a matching
  `fontfile`.
- **Images**: currently untouched. You could optionally dim/desaturate them
  slightly (rather than full invert) so bright photos don't clash with the
  dark background — `page.get_images()` + `Pixmap` manipulation is the way in.
- **Vector graphics / drawings** (lines, shapes, fills that aren't text or
  images) aren't recolored yet — only text spans are. For PDFs with colored
  boxes/tables, you'd want to also walk `page.get_drawings()` and recolor
  fills/strokes that are close to black or close to white.
- **Large PDFs**: this is synchronous per-request. For a real product you'd
  want a job queue (e.g. Celery/RQ) and a status-polling or websocket flow
  for big files.
- **Auth/rate limiting**: there's none right now — fine for a side project,
  not for a public deploy without adding limits, since PDF processing is
  CPU-bound.
