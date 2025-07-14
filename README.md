# Sun Tzu: The Unfought Battle - Core Game Engine API

## Overview
This repository contains the backend API for "Sun Tzu: The Unfought Battle," a turn-based strategy simulation inspired by Sun Tzu's *The Art of War*. It's a headless (no UI) Python/Flask API for simulating games, focusing on deception, terrain, and morale. Dual purpose: Fun psychological duel game and LLM research tool.

Based on the Game Design Document (GDD) in `docs/TheUnfoughtBattle.pdf`.

Key Features:
- Procedural hex grid map generation (10x10 hexes with Open, Difficult, Contentious terrains).
- Player resources: Chi (morale), Shih (momentum).
- Orders: Advance, Meditate, Deceive (with ghosts).
- Confrontations: Rock-paper-scissors stances (Mountain, River, Thunder).
- Victory paths: Demoralization, Domination, Deception Mastery.
- API endpoints for game creation, state, actions, logs.

Future: LLM integration, Godot UI.

## Setup
1. Clone the repo: `git clone https://github.com/GrahamWallingtonXeroth/SunTzu.git`
2. Navigate to the folder: `cd SunTzu`
3. Create and activate virtual environment: `python3 -m venv venv` then `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt` (coming soon; for now, `pip install flask numpy pytest`)
5. Run the API: `python app.py` (coming soon)

## Development
- Use Python 3.12+.
- Tests: `pytest`
- Deploy: Google Cloud Platform App Engine.

## Docs
- GDD: See attached PDF.
- Architecture: `docs/architecture.md` (coming soon).
- API Endpoints: `docs/api_endpoints.md` (coming soon).

Built with guidance from Grok 4 (xAI). License: MIT (open-source ethics as per GDD).