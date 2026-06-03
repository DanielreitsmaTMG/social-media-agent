#!/bin/bash

PROJECT_DIR="/Users/danielreitsma/Desktop/Marketing Agent Social Media"
LOG_FILE="$PROJECT_DIR/logs/pipeline_$(date +%Y-%m-%d).log"

mkdir -p "$PROJECT_DIR/logs"
cd "$PROJECT_DIR"

echo "======================================" >> "$LOG_FILE"
echo "Pipeline gestart: $(date)" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

echo "" >> "$LOG_FILE"
echo "--- Stap 1: Klantprofielen laden ---" >> "$LOG_FILE"
/usr/bin/python3 systems/read_client_profiles.py >> "$LOG_FILE" 2>&1

echo "" >> "$LOG_FILE"
echo "--- Stap 2: URLs scrapen ---" >> "$LOG_FILE"
/usr/bin/python3 systems/scrape_client_sources.py >> "$LOG_FILE" 2>&1

echo "" >> "$LOG_FILE"
echo "--- Stap 3: Posts genereren ---" >> "$LOG_FILE"
/usr/bin/python3 systems/generate_weekly_posts.py >> "$LOG_FILE" 2>&1

echo "" >> "$LOG_FILE"
echo "--- Stap 4: Word-documenten opslaan ---" >> "$LOG_FILE"
/usr/bin/python3 systems/save_local_docs.py >> "$LOG_FILE" 2>&1

echo "" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"
echo "Pipeline klaar: $(date)" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"
