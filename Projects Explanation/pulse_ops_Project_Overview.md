# PulseOps AI - Complete Project Overview

## 📖 Introduction
**PulseOps AI** is an advanced, autonomous incident response and orchestration system designed for Site Reliability Engineering (SRE) teams. The project addresses a critical bottleneck in modern IT operations: **alert fatigue and slow incident triage (MTTR)**. 

By utilizing a multi-agent system, PulseOps AI automatically ingests unstructured alarm emails, triages their severity, searches for historical resolutions, and intelligently allocates the incident to the most appropriate on-call engineer based on workload and skills.

---

## 🎯 Core Objectives
1. **Automate Triage:** Extract key diagnostics from raw alarm alerts without human intervention.
2. **Reduce MTTR (Mean Time To Resolution):** Provide immediate remediation steps by fetching historical incidents using local Retrieval-Augmented Generation (RAG).
3. **Optimize Workforce Allocation:** Assign tickets dynamically based on engineers' real-time workloads, specialties, and schedule availability to prevent burnout and SLA breaches.
4. **Interactive Copilot:** Offer engineers a Chat interface to run diagnostic queries directly against the system state and knowledge base.

---

## 🛠️ Complete Technology Stack

### Backend Stack
* **Python (3.9+)**: The core programming language for the backend orchestration.
* **FastAPI**: A modern, high-performance web framework used to build the REST API endpoints and manage asynchronous agent routines.
* **Uvicorn**: ASGI web server implementation for Python to run the FastAPI application.
* **Pydantic**: Data validation and settings management, enforcing strict JSON schemas for API routes and agent payloads.
* **Ollama (llama3.2)**: A local LLM runner used to execute the `llama3.2` model securely offline. It performs NLP parsing, decision-making, and powers the chat Copilot.
* **In-Memory TF-IDF / Vector Database**: A custom implementation used for calculating Cosine Similarity to find historical runbooks (acting as the RAG storage). This was chosen to prevent GPU/HTTP timeouts on heavy alert loads.

### Frontend Stack
* **HTML5**: Semantic structuring of the Single Page Application (SPA).
* **Vanilla JavaScript (ES6+)**: Handles all client-side logic, API calls (`fetch`), state synchronization, simulation timing, and dynamic DOM rendering.
* **Vanilla CSS3**: Custom-built stylesheet focusing on a premium **Matrix Emerald Green** and **CRED-style Dark Mode** aesthetic. Utilizes CSS Grid, Flexbox, and CSS Variables (custom properties) without relying on heavy external frameworks like Tailwind or Bootstrap.
* **Inline SVGs**: For scalable, zero-request icons colored dynamically via CSS `currentColor`.

### Conceptual Stack & Patterns
* **Multi-Agent Architecture**: Decoupled agents (Parser, Triage, RAG, Allocation) chained sequentially.
* **RAG (Retrieval-Augmented Generation)**: Grounding LLM responses with factual historical data to prevent hallucinations.
* **State Synchronization**: Client-side polling and manual triggers to align the UI with the backend memory state.

---

## 🏗️ System Architecture & Workflow

The system operates on a chained multi-agent pipeline. When an alert arrives, it passes through four distinct phases:

1. **Parser Agent (`email_agent.py`)**
   * **Input**: Unstructured email text (Subject, Body, Sender).
   * **Output**: Structured JSON (Severity flags, Component Category, Description).
2. **Triage Agent (`triage_agent.py`)**
   * **Input**: Structured alert data.
   * **Output**: Priority Scoring and target SLA limits calculated via heuristic matrices.
3. **RAG Agent (`rag_agent.py`)**
   * **Input**: Incident description.
   * **Output**: Historical recommendations. It queries the Vector Database (using TF-IDF cosine similarity) for incidents matching the current alert, returning the highest-confidence Root Cause Analysis (RCA).
4. **Allocation Agent (`allocation_agent.py`)**
   * **Input**: Full context (Priority, Category, active on-call list).
   * **Output**: The best-matched engineer. It calculates a "Workload Score" avoiding over-allocation while ensuring the assignee has the necessary component skills.

---

## 💻 Codebase Layout

```text
OpsPilot/
├── index.html            # Main UI Dashboard
├── css/
│   ├── variables.css     # Theming tokens (Matrix Green, Dark Surfaces)
│   ├── layout.css        # Core Grid and Sidebar drawers
│   ├── components.css    # Cards, pills, forms, animations
│   └── animations.css    # Keyframes for pulse effects and loading
├── js/
│   ├── app.js            # Main frontend controller connecting to FastAPI
│   ├── data.js           # Mock data fallback (offline mode)
│   └── copilot.js        # Chat interface logic
└── backend/
    ├── main.py           # FastAPI Application and HTTP Routes
    ├── database/
    │   └── store.py      # TF-IDF Vector Database and Memory State
    └── agents/
        ├── email_agent.py      # Parses text to JSON
        ├── triage_agent.py     # Assigns Priority & SLA Risk
        ├── rag_agent.py        # Vector similarity search
        ├── allocation_agent.py # Workload routing
        └── orchestrator.py     # Master supervisor pipeline
```

---

## 🚀 How to Run the Project

1. **Start the Backend API:**
   Ensure Python dependencies are installed, then run the FastAPI server:
   ```bash
   pip install fastapi uvicorn pydantic
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
   ```

2. **Start the Frontend Client:**
   Serve the static files using Python's built-in HTTP server:
   ```bash
   python -m http.server 8080
   ```

3. **Access the App:**
   Open `http://localhost:8080` in your browser. Ensure the local Ollama instance (running `llama3.2`) is active in the background to handle NLP tasks.
