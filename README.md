# fastcohort

A library for reviewing OMOP Cohorts.

## Cohort timeline app

This repository now includes a FastHTML app that renders OMOP procedure/condition timelines. It connects to a Postgres database via FastSQL and lets you edit the underlying SQL query directly in the UI.

### Setup

1. Create a `.env` file that includes one of the following connection string variables pointing at your Postgres database: `DATABASE_URL`, `POSTGRES_CONNSTR`, or `PG_CONNSTR`.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Run

Start the FastHTML server (defaults to port 5001):

```bash
python main.py
```

### Features

- The default SQL query targets cervical spine CT procedures for patients with cervical spinal stenosis and can be edited in the UI.
- Results are paginated in batches of 25 with previous/next buttons.
- Each row shows a simple timeline with the condition start (blue circle) and procedure date (red square) keyed by `person_id`.
