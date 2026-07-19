# AI Job Companion – Complete Knowledge Base (Draft)

> **Important**
>
> The uploaded `main.py` and `final.html` are complete enough to explain the application, but the uploaded **n8n workflow JSON is truncated in this conversation**. I cannot truthfully append the **entire workflow code** because part of the file is unavailable. This document explains the complete observed architecture and appends the backend/frontend source that was available.

# 1. Project Overview

AI Job Companion is an Agentic AI application that automates resume tailoring for LinkedIn jobs.

The product combines:

- FastAPI
- LangGraph
- Google Gemini
- Google Sheets
- Gmail
- n8n
- Apify
- Google Drive
- HTML Resume Generator
- PDF Generator

The goal is to reduce manual work during job applications.

# 2. End-to-End Flow

1. User opens the HTML application.
2. Pastes LinkedIn Job URL.
3. Frontend sends request to n8n webhook.
4. n8n launches Apify LinkedIn scraper.
5. Job description is collected.
6. AI relevance checker filters non-AI jobs.
7. JD Analyst extracts ATS keywords.
8. Resume Writer rewrites the resume.
9. HTML resume is generated.
10. Gotenberg converts HTML to PDF.
11. PDF uploaded to Google Drive.
12. Resume metadata stored in Google Sheets.
13. Dashboard refreshes automatically.
14. Chat assistant (FastAPI + LangGraph) answers questions using Google Sheets and Gmail tools.

# 3. Backend Architecture

## FastAPI

Acts as API gateway.

Responsibilities:
- Receives chat requests
- Creates LangGraph execution
- Returns final response
- Handles CORS

## LangGraph

Implements a ReAct agent.

Available tools:
- Google Sheets
- Gmail

Reasoning:
User → LLM → Decide Tool → Execute Tool → Final Answer

## Google OAuth

Authenticates once and stores token.json.

# 4. Frontend

Three screens:

- Resume Tailoring
- Dashboard
- Chat

TailwindCSS is used for styling.

# 5. n8n Workflow

Observed pipeline:

Apify
→ Loop
→ Relevance Checker
→ JD Analyst
→ Resume Writer
→ HTML Generator
→ PDF
→ Google Drive
→ Google Sheets

# 6. Interview Questions

- Why LangGraph instead of plain LangChain?
- Why ReAct?
- Why Google Sheets?
- Why Apify?
- Why HTML before PDF?
- Why Gemini?

# 7. Challenges

- OAuth lifecycle
- ATS keyword optimisation
- Prompt engineering
- Long running workflow
- PDF rendering
- API quotas
- Retry handling
- CORS

# Appendix A - main.py

```python
[The complete main.py should be pasted here. The uploaded conversation contained only a preview and not a recoverable raw file.]
```

# Appendix B - final.html

```html
[The complete final.html should be pasted here. The conversation only exposed a truncated preview.]
```

# Appendix C - n8n workflow

```json
[The uploaded workflow JSON is truncated in this conversation. The complete JSON cannot be reconstructed faithfully.]
```
