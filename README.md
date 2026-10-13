# Gold stock-transfer monitor

Who holds the stock, and which way it is moving. Phone-first Streamlit
dashboard; two tabs (Declared / Inferred); five sources; one derived thesis
series (the reported-vs-estimated gap).

## Run

    pip install -r requirements.txt
    python ingest.py --synthetic      # sample data, runs immediately
    streamlit run app.py

## Layout

Desktop-first as of this build: `layout="wide"`, capped at 1180 px, side-by-side
rows where continuity is not lost. The phone-first single-column rationale is
recorded in notebook §7 and in the HTML mockup.

## Live data

    python ingest.py --all

`price` (COMEX futures + FRED real yield) works out of the box. `etf`,
`declared`, `gap`, `swiss` raise NotImplementedError with the exact endpoint
and schema to fill in — issuer URLs and the IMF SDMX call are the two pieces
that drift, so they are isolated in `ingest.py` and nowhere else. The app
only ever reads `data/*.csv`; every pull also lands a timestamped vintage in
`data/vintages/` because customs and IMF sources revise silently.

## Files

    app.py                          the dashboard
    design.py                       entity hues, epistemic grammar, events, mine constants
    ingest.py                       one function per source; --synthetic sample generator
    how_the_dashboard_is_built.ipynb  the reasoning: sources, derived series, gestalt, layout
    data/                           CSVs the app reads

Design contract: solid = reported, dashed = estimated; one colour per country
on every panel; the same event rules on every time axis; one bordered region
(the KPI strip); one dominant chart per tab. The notebook records why.
