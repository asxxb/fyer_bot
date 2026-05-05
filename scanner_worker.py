"""
scanner_worker.py
Runs scanner continuously
and saves results to JSON
"""

import os
import json
import time
from datetime import datetime

import pandas as pd

from scanner import scan_stock
from core.scanner import (
    get_performance_data,
    to_internal,
    should_include_stock,
    passes_momentum_filter
)

from config import settings

from utils.logger import get_logger

log = get_logger()

# Scanner interval (5 minutes default)
SCANNER_INTERVAL = 300

# ---------------------------------------------------
# WATCHLIST (use settings.WATCHLIST)
# ---------------------------------------------------

# Use settings.WATCHLIST - strip -EQ for yfinance
WATCHLIST = [s.replace("-EQ", "") for s in settings.WATCHLIST]

DATA_DIR = "data"

os.makedirs(
    DATA_DIR,
    exist_ok=True
)

RESULT_FILE = os.path.join(
    DATA_DIR,
    "scanner_results.json"
)

# ---------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------

while True:

    scan_start = time.time()

    try:

        log.info(
            "Running scanner..."
        )

        scanner_results = []

        # Get fresh performance data (auto-reload every 5 mins)
        perf_data = get_performance_data()

        # -----------------------------------------
        # SCAN STOCKS
        # -----------------------------------------

        for stock in WATCHLIST:

            # ---------------------------------
            # STEP 1: QUALITY FILTER (Performance)
            # ---------------------------------
            
            # Use to_internal for consistent symbol format (returns None if missing)
            perf = perf_data.get(to_internal(stock))
            
            # Handle None (missing) vs valid data
            if perf is None:
                if settings.ALLOW_UNKNOWN_STOCKS:
                    log.debug(f"{stock}: Allowing unknown stock")
                else:
                    log.debug(f"{stock}: Skipping - no performance data")
                    continue
            else:
                include, reason = should_include_stock(stock, perf)
                if not include:
                    log.debug(f"{stock}: Skipping - {reason}")
                    continue

            result = scan_stock(stock)

            if result:

                # ---------------------------------
                # STEP 2: MOMENTUM FILTER
                # ---------------------------------

                if passes_momentum_filter(result["change_pct"], result["score"]):
                    scanner_results.append(result)

        # -----------------------------------------
        # SORT
        # -----------------------------------------

        scanner_results = sorted(

            scanner_results,

            key=lambda x: x["score"],

            reverse=True

        )

        # -----------------------------------------
        # SAVE JSON
        # -----------------------------------------

        output = {

            "last_scan": datetime.now()
            .strftime("%Y-%m-%d %H:%M:%S"),

            "results": scanner_results

        }

        with open(
            RESULT_FILE,
            "w"
        ) as f:

            json.dump(
                output,
                f,
                indent=2
            )

        log.info(

            f"Scanner complete | "
            f"{len(scanner_results)} stocks"

        )

    except Exception as e:

        log.error(
            f"Scanner worker error: {e}"
        )

    # ---------------------------------------------
    # WAIT (rate protection)
    # ---------------------------------------------

    elapsed = time.time() - scan_start
    sleep_time = max(0, SCANNER_INTERVAL - elapsed)
    log.debug(f"Scan took {elapsed:.1f}s, sleeping {sleep_time:.1f}s")
    time.sleep(sleep_time)