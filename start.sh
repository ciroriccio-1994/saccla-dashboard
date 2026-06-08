#!/bin/bash
playwright install chromium
playwright install-deps chromium
exec streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true --server.enableXsrfProtection=false
