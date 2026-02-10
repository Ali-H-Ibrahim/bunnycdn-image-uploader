# Image Processor - Quick Start

This is a simple FastAPI project for processing image links and uploading files to BunnyCDN storage.

## Requirements

- Python 3.10+ (recommended)
- pip

## Setup

1) Create and activate virtual environment:

```bash
python -m venv venv
venv\Scripts\activate
```

2) Install dependencies:

```bash
pip install -r requirements.txt
```

3) Create `.env` from `.env.example` and fill your real values:

```bash
copy .env.example .env
```

Required main values:
- `BUNNY_STORAGE_ZONE`
- `BUNNY_ACCESS_KEY`
- `BUNNY_CDN_BASE_URL`

## Run

Use one of these:

```bash
python run.py
```

or

```bash
uvicorn app.main:app --reload
```

Then open:
- `http://127.0.0.1:8000`

## Screenshots

### Upload Section
![Upload Section](Images/Upload%20Section.png)

### Advanced Settings
![Advanced Settings](Images/Advanced%20Settings.png)

### Progress Section
![Progress Section](Images/Progress%20Section.jpeg)

### Results Section
![Results Section](Images/Results%20Section.jpg)

## Notes

- Job outputs are saved inside `jobs/`.
- Do not upload `.env` to GitHub.
