# Virtual Race Engineer

A professional-grade F1 telemetry analysis platform built with Python and FastF1.
Compare driver performance lap-by-lap, analyse braking signatures, and get automated strategic insights — all in an interactive web interface.

> **Status: Phase 4 — Advanced Features & AI Verdict** · Phase 5 (Visualisation) next

---

## Features

| Status | Feature |
|--------|---------|
| ✅ | FastF1 data access with local cache |
| ✅ | Thread-safe Singleton repository |
| ✅ | Retry logic for API timeouts |
| ✅ | Domain models (Lap, DriverStats) with Pydantic validation |
| ✅ | Dark theme UI with F1-inspired colour palette |
| ✅ | Session selector sidebar (Year, GP, Session, Drivers) |
| ✅ | Reusable component library (Stat Cards, Driver Badges) |
| ✅ | Distance-based lap synchronisation (1 m grid) |
| ✅ | Speed Delta — cumulative time loss/gain per metre |
| ✅ | Driver DNA — Aggressiveness & Smoothness scores |
| ✅ | Brake Shape Analysis (Trail Braker vs. V-Shaper) |
| 🔜 | Driver telemetry comparison charts (Speed, Throttle, Brake) |
| ✅ | Micro-Sector Dominance (50 m segments, colour-coded winner per zone) |
| ✅ | Overtake Profile (corner exit speed comparison, vulnerability map) |
| ✅ | AI Race Engineer Verdict (heuristic — deterministic, offline) |
| 🔜 | Driver telemetry comparison charts (Speed, Throttle, Brake) |
| 🔜 | Cumulative Delta chart |
| 🔜 | Track map heatmap |

---

## Requirements

- Python **3.10** or higher
- Internet access for the first data fetch (FastF1 caches locally afterwards)

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/VirtualRaceEngineer.git
cd VirtualRaceEngineer
```

### 2. Create a virtual environment

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` at the beginning of your terminal prompt.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Running the app

```bash
streamlit run main.py
```

The app opens automatically at `http://localhost:8501`.

---

## Running the tests

```bash
pytest tests/ -v
```

All unit tests use mocked FastF1 data — no internet connection required.

---

## Project structure

```
VirtualRaceEngineer/
├── src/
│   ├── domain/          # Pydantic entities & value objects
│   ├── services/        # Business logic & analysis strategies
│   ├── infrastructure/  # FastF1 API wrapper & cache management
│   ├── ui/              # Streamlit pages & UI components
│   └── shared/          # Constants, type aliases, utilities
├── tests/               # Pytest suite
├── data_cache/          # Local FastF1 cache (git-ignored)
├── main.py              # App entry point
└── requirements.txt
```

---

## Development

### Code quality

```bash
# Auto-format
black src/ tests/

# Type checking
mypy src/
```

### Deactivating the virtual environment

```bash
deactivate
```

---
