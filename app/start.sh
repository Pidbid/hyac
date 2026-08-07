#!/bin/sh

exec uvicorn main:app --host 0.0.0.0 --port 8001 --workers 1
