# Fabrice -- Wiki based on Jacques Vallee's works — Project Context for Claude Code

## Project Goal
Extract UFO case files from Jacques Vallée's *Passport to Magonia* (and eventually other books) and publish them as an interconnected wiki using Quartz + GitHub Pages.

## Stack
- **Wiki framework:** Quartz v4 (https://quartz.jzhao.xyz)
- **Hosting:** GitHub Pages via GitHub Actions (auto-deploys on push to main)
- **Local editing:** Obsidian vault pointed at `content/`
- **Extraction:** Python + pdfplumber + Anthropic API
- **Output format:** Markdown files with YAML frontmatter, one file per case

## Repo Structure
```
fabrice/
├── content/          # Obsidian vault / Quartz content root
│   ├── index.md      # Wiki homepage
│   └── cases/        # One .md file per UFO case
├── quartz.config.ts  # Quartz configuration
├── extract/          # Python extraction scripts (to be created)
│   ├── extract_cases.py
│   └── cases.json    # Intermediate structured output
└── CLAUDE.md         # This file
```

## Case Markdown Format
Each case file lives at `content/cases/case-{number}.md` and follows this structure:

```markdown
---
title: "Case 001 — Langenburg, Saskatchewan"
date: 1974-09-01
location: Langenburg, Saskatchewan
tags: [case, landing, trace-evidence]
source: Passport to Magonia
---

## Langenburg, Saskatchewan — September 1, 1974

{description}

**Witnesses:** {witnesses}
**Source:** {source}
**Category:** {category}
```

## Extraction Pipeline

### Step 1 — Extract raw text from PDF
```python
import pdfplumber

with pdfplumber.open("passport_to_magonia.pdf") as pdf:
    text = ""
    for page in pdf.pages[APPENDIX_START_PAGE:]:
        text += page.extract_text() + "\n"
```

### Step 2 — Parse cases with Claude API
Send chunks of appendix text to the API and ask for structured JSON output.

Target JSON schema per case:
```json
{
  "case_number": "001",
  "date": "1897-04-19",
  "location": "Leroy, Kansas",
  "description": "...",
  "witnesses": "...",
  "source": "...",
  "category": "CE2"
}
```

### Step 3 — Convert JSON to markdown
Loop over parsed cases, render each to a `.md` file using the format above, save to `content/cases/`.

### Step 4 — Push to GitHub
```bash
npx quartz sync
```
GitHub Actions handles the build and deploy automatically.

## Key Things to Know
- The appendix in Passport to Magonia is already structured as a numbered case catalog — extraction should be relatively clean
- Chunk the appendix into ~3000 token segments before sending to the API to stay within context limits
- Use YAML frontmatter tags like `landing`, `CE1`, `CE2`, `CE3`, `humanoid`, `trace-evidence` etc. for Quartz to auto-generate tag pages
- Quartz backlinks work automatically — cases sharing tags or locations will link to each other
- `.env` file holds `ANTHROPIC_API_KEY`, never commit it

## Dependencies
```bash
pip install pdfplumber anthropic python-dotenv
```

## TODO
- [ ] Identify appendix start page in the PDF
- [ ] Write extract_cases.py
- [ ] Run extraction and review cases.json for quality
- [ ] Write json_to_markdown.py
- [ ] Populate content/cases/
- [ ] Customize quartz.config.ts (site title, colors etc.)
- [ ] Verify GitHub Actions deployment works
- [ ] Eventually add cases from Dimensions, Confrontations, etc.
