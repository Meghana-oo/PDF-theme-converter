"""
PDF Dark Mode - Backend

Takes an uploaded PDF and returns a NEW PDF where:
  - Page backgrounds are filled with a dark color
  - Text is recolored to a light color
  - Images are left untouched (optionally you could invert/dim them)

Technique:
  1. Draw a dark rectangle behind all existing page content (overlay=False
     puts it underneath, so it acts as a new background).
  2. Walk the page's text spans, redact (erase) each one, then re-insert
     the same text in a light color at the same position/size.

This is a genuine content rewrite (not a CSS filter trick), so the
resulting PDF looks dark-mode in any viewer, not just this app.

To activate the virtual environment (if using conda):
    conda activate basepip
    ./.conda/bin/python -m pip install <packages>

Run locally:
    pip install -r requirements.txt or python-multipart
    uvicorn app:app --reload --port 8000
"""

import io
import fitz  # PyMuPDF: used to read, edit, and write the PDF data
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

app = FastAPI(title="PDF Dark Mode API")

# Allow the frontend (running on a different port/origin during dev) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to your actual frontend origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Default theme colors (RGB, 0-1 floats, as PyMuPDF expects)
DARK_BG = (0.10, 0.10, 0.12)
LIGHT_TEXT = (0.92, 0.92, 0.90)


def convert_pdf_to_dark(pdf_bytes: bytes, bg_color=DARK_BG, text_color=LIGHT_TEXT) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page in doc:
        rect = page.rect # gets the width, height, and boundary coordinates of the current page

        # 1. Dark background, drawn UNDER existing content.
        page.draw_rect(rect, color=bg_color, fill=bg_color, overlay=False)

        # 2. Collect every text span on the page (text, position, size, font).
        text_dict = page.get_text("dict")
        spans_to_redraw = []

        for block in text_dict.get("blocks", []):
            if "lines" not in block:
                continue  # skip image blocks
            for line in block["lines"]:
                for span in line["spans"]:
                    if not span["text"].strip():
                        continue
                    spans_to_redraw.append(span)

        # 3. Redact (erase) the original dark-on-light text.
        #    fill uses the new background color so no ghosting is left behind.
        #    images=PDF_REDACT_IMAGE_NONE keeps embedded images intact.
        for span in spans_to_redraw:
            bbox = fitz.Rect(span["bbox"])
            page.add_redact_annot(bbox, fill=bg_color)

        if spans_to_redraw:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        # 4. Re-insert the same text in a light color at the same spot.
        for span in spans_to_redraw:
            bbox = fitz.Rect(span["bbox"])
            try:
                page.insert_text(
                    (bbox.x0, bbox.y1 - 1.5),  # baseline approx = bottom of bbox
                    span["text"],
                    fontsize=span["size"],
                    color=text_color,
                    fontname="helv",  # fallback font; see README for font-matching notes
                )
            except Exception:
                # Some spans (rotated text, exotic encodings) can fail to re-insert.
                # Skipping keeps the rest of the page intact rather than failing the whole request.
                continue

    out = io.BytesIO()
    doc.save(out)
    doc.close()
    out.seek(0)
    return out.read()


def hex_to_rgb01(hex_color: str):
    """Convert '#1a1a1e' -> (0.10, 0.10, 0.12) style tuple for PyMuPDF."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        raise ValueError("Color must be a 6-digit hex string")
    r = int(hex_color[0:2], 16) / 255
    g = int(hex_color[2:4], 16) / 255
    b = int(hex_color[4:6], 16) / 255
    return (r, g, b)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/dark-mode")
async def dark_mode_pdf(
    file: UploadFile = File(...),
    bg_color: str = Form(default="#1a1a1e"),
    text_color: str = Form(default="#ebebe6"),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        bg = hex_to_rgb01(bg_color)
        text = hex_to_rgb01(text_color)
        result_bytes = convert_pdf_to_dark(pdf_bytes, bg_color=bg, text_color=text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process PDF: {e}")

    filename = (file.filename or "document").rsplit(".", 1)[0] + "-dark.pdf"
    return StreamingResponse(
        io.BytesIO(result_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
