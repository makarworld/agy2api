---
title: "Phase 1: Project Setup"
status: todo
---

# Phase 1: Project Setup

## Overview

Set up a React + Vite + Tailwind + shadcn/ui project in the `ui` folder inside `agy2api`. Configure FastAPI in `agy2api/app/main.py` to serve the static build output of this UI.

## Requirements

- [x] Initialize Vite React project in `ui/`.
- [x] Install Tailwind CSS, shadcn/ui, Lucide icons.
- [x] Implement `index.css` following `goclaw`'s premium design styling (fonts, colors, layout).
- [x] Update `app/main.py` in FastAPI to serve `/ui/dist` statically at `/`.

## Implementation Steps

1. Run `npx -y create-vite@latest ui --template react-ts`.
2. Configure Tailwind and shadcn/ui inside the `ui` folder.
3. Apply global CSS variables and classes from `goclaw` to match the aesthetic.
4. Modify `agy2api/app/main.py` to add `app.mount("/", StaticFiles(directory="ui/dist", html=True), name="static")`.
5. Write a small script to build the UI and start FastAPI together.

## Todo

- [x] Create Vite app.
- [x] Setup Tailwind.
- [x] Copy `goclaw` CSS tokens.
- [x] Update FastAPI `main.py`.

## Success Criteria

Running FastAPI serves the default Vite React page (with Tailwind) on port 8000 when navigating to `http://localhost:8000/`.
