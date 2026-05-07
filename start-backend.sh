#!/bin/bash
# Start FastAPI backend on Render
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
