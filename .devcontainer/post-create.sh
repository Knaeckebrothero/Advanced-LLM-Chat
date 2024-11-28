#!/bin/bash

# Install Python dependencies
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

# Install Angular dependencies
if [ -f "package.json" ]; then
    npm install
fi

# Create development certificates directory
mkdir -p devcerts

# Run the backend mockup once to generate the certificates
python backend_mockup.py
