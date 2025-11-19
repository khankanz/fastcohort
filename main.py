from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Mapping, Optional

from dotenv import load_dotenv
from fasthtml.common import *
from fastsql import Database
from sqlalchemy import text

load_dotenv()

DEFAULT_QUERY = f"""
SELECT
    po.procedure_occurrence_id,
    po.person_id,
    (
        SELECT p.person_source_value
        FROM cdm.person AS p
        WHERE p.person_id = po.person_id
    ) AS patient_fhir_id,
    po.procedure_concept_id,
    po.procedure_date,
    po.procedure_type_concept_id,
    po.procedure_source_value,
    co.condition_source_concept_id,
    co.condition_type_concept_id,
    co.condition_source_value,
    co.condition_start_date
FROM cdm.procedure_occurrence AS po
JOIN cdm.condition_occurrence AS co
  ON po.person_id = co.person_id
WHERE
  -- Cervical spinal stenosis (ICD-10 M48.02)
  co.condition_source_concept_id = 42617675
  AND co.condition_type_concept_id = 32849
  AND (
        co.condition_source_value = 'M48.02'
        OR co.condition_source_value LIKE 'M48.02%' -- e.g., 'M48.02(Spinal stenosis, cervical region)'
      )
  -- CT cervical-spine related procedures
  AND po.procedure_concept_id IN (
        36713283, -- CT cervical spine without contrast
        4086261, -- CT of cervical spine
        4296895, -- CT of cervical spine with contrast
        45771285, -- CT of cervical and thoracic spine
        46286918, -- CT of cervical spine for radiotherapy planning
        37396027, -- CT of cervical spine for radiotherapy planning
        45765549, -- Computed tomography of cervical and lumbar spine
        36675712, -- Mobile intraoperative 3D (three-dimensional) CT of cervical spine
        35609874 -- Mobile intraoperative 3D (three-dimensional) CT of cervical spine
      )
  AND po.procedure_type_concept_id = 32841
ORDER BY
  po.person_id,
  po.procedure_occurrence_id
"""

PAGE_SIZE = 25

CONN_VARS = ("DATABASE_URL", "POSTGRES_CONNSTR", "PG_CONNSTR")


def conn_str() -> Optional[str]:
    """Return the first available connection string from expected env vars."""
    for key in CONN_VARS:
        value = os.getenv(key)
        if value:
            return value
    return None


db_url = conn_str()
db = Database(db_url) if db_url else None

app, rt = fast_app()


@dataclass
class CohortRow:
    procedure_occurrence_id: int
    person_id: int
    patient_fhir_id: Optional[str]
    procedure_concept_id: Optional[int]
    procedure_date: Optional[date]
    procedure_type_concept_id: Optional[int]
    procedure_source_value: Optional[str]
    condition_source_concept_id: Optional[int]
    condition_type_concept_id: Optional[int]
    condition_source_value: Optional[str]
    condition_start_date: Optional[date]

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "CohortRow":
        return cls(
            procedure_occurrence_id=row.get("procedure_occurrence_id"),
            person_id=row.get("person_id"),
            patient_fhir_id=row.get("patient_fhir_id"),
            procedure_concept_id=row.get("procedure_concept_id"),
            procedure_date=row.get("procedure_date"),
            procedure_type_concept_id=row.get("procedure_type_concept_id"),
            procedure_source_value=row.get("procedure_source_value"),
            condition_source_concept_id=row.get("condition_source_concept_id"),
            condition_type_concept_id=row.get("condition_type_concept_id"),
            condition_source_value=row.get("condition_source_value"),
            condition_start_date=row.get("condition_start_date"),
        )


style = Style(
    """
    body {font-family: 'Inter', system-ui, -apple-system, sans-serif; margin: 0; background: #f7f7fb; color: #1a1a1a;}
    header {background: #1e1e2f; color: white; padding: 1rem 1.5rem;}
    main {padding: 1.5rem; max-width: 1200px; margin: 0 auto;}
    .query-card {background: white; border-radius: 12px; padding: 1rem; box-shadow: 0 10px 30px rgba(0,0,0,0.08); margin-bottom: 1.5rem;}
    .query-actions {display: flex; align-items: center; gap: 0.75rem; margin-top: 0.75rem;}
    textarea {width: 100%; min-height: 260px; font-family: 'JetBrains Mono', 'SFMono-Regular', monospace; font-size: 0.95rem; border-radius: 8px; border: 1px solid #d8d8e3; padding: 0.75rem; background: #fafafe;}
    textarea:focus {outline: 2px solid #3b82f6; border-color: #3b82f6;}
    button, .button {background: #2563eb; color: white; border: none; border-radius: 8px; padding: 0.55rem 0.9rem; font-weight: 600; cursor: pointer; font-size: 0.95rem;}
    button[disabled], .button[disabled] {background: #cbd5e1; cursor: not-allowed;}
    .muted {color: #5b6078; font-size: 0.95rem;}
    .results {display: grid; gap: 1rem;}
    .result-card {background: white; border-radius: 12px; padding: 1rem; box-shadow: 0 8px 24px rgba(0,0,0,0.06);}
    .card-header {display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;}
    .badge {background: #eef2ff; color: #312e81; padding: 0.25rem 0.5rem; border-radius: 6px; font-size: 0.85rem;}
    .timeline {display: flex; flex-direction: column; gap: 0.5rem; margin-top: 0.5rem;}
    .event {display: grid; grid-template-columns: auto 1fr; gap: 0.75rem; align-items: center;}
    .marker {width: 16px; height: 16px;}
    .procedure {background: #e11d48; border-radius: 3px;}
    .condition {background: #2563eb; border-radius: 50%;}
    .event-label {font-weight: 700; color: #111827;}
    .event-date {color: #334155; font-size: 0.95rem;}
    .metadata {display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.35rem 0.75rem; margin-top: 0.5rem;}
    .metadata span {color: #475467; font-size: 0.95rem;}
    .pagination {display: flex; align-items: center; gap: 0.75rem; margin-top: 1rem;}
    footer {text-align: center; color: #6b7280; margin-top: 1.5rem; font-size: 0.9rem;}
    """
)


def paginate_query(sql: str) -> str:
    """Wrap the user SQL to enforce pagination."""
    trimmed = sql.strip().rstrip(";")
    return f"SELECT * FROM ({trimmed}) AS cohort_query LIMIT :limit OFFSET :offset"


def fetch_rows(sql: str, page: int) -> tuple[List[CohortRow], Optional[str]]:
    if not db:
        return [], "Missing database connection string. Set one of DATABASE_URL, POSTGRES_CONNSTR, or PG_CONNSTR."

    try:
        paginated = paginate_query(sql)
        offset = (max(page, 1) - 1) * PAGE_SIZE
        with db.engine.begin() as conn:
            result = conn.execute(text(paginated), {"limit": PAGE_SIZE, "offset": offset})
            rows = [CohortRow.from_mapping(r) for r in result.mappings()]
        return rows, None
    except Exception as exc:  # pragma: no cover - runtime DB errors are shown in UI
        return [], f"Query failed: {exc}"


def marker(label: str, dt: Optional[date], cls: str) -> Optional[Div]:
    if not dt:
        return None
    date_str = dt if isinstance(dt, str) else dt.isoformat() if isinstance(dt, (date, datetime)) else str(dt)
    return Div(
        Div(cls=f"marker {cls}"),
        Div(Span(label, cls="event-label"), Span(date_str, cls="event-date")),
        cls=f"event {cls}",
    )


def result_card(row: CohortRow) -> Div:
    events = [
        marker("Condition start", row.condition_start_date, "condition"),
        marker("Procedure", row.procedure_date, "procedure"),
    ]
    timeline = Div(*(ev for ev in events if ev), cls="timeline")

    metadata = Div(
        Span(f"Procedure concept: {row.procedure_concept_id}"),
        Span(f"Procedure type: {row.procedure_type_concept_id}"),
        Span(f"Procedure source: {row.procedure_source_value}"),
        Span(f"Condition concept: {row.condition_source_concept_id}"),
        Span(f"Condition type: {row.condition_type_concept_id}"),
        Span(f"Condition source: {row.condition_source_value}"),
        cls="metadata",
    )

    return Div(
        Div(
            Strong(f"Person {row.person_id}"),
            Span(f"Procedure #{row.procedure_occurrence_id}", cls="badge"),
            cls="card-header",
        ),
        timeline,
        metadata,
        cls="result-card",
    )


def pagination_controls(sql: str, page: int, has_next: bool) -> Div:
    prev_page = max(page - 1, 1)
    next_page = page + 1
    return Div(
        Form(
            Input(type="hidden", name="sql", value=sql),
            Input(type="hidden", name="page", value=prev_page),
            Button("← Previous 25", type="submit", disabled=page <= 1),
            method="get",
        ),
        Span(f"Page {page}", cls="muted"),
        Form(
            Input(type="hidden", name="sql", value=sql),
            Input(type="hidden", name="page", value=next_page),
            Button("Next 25 →", type="submit", disabled=not has_next),
            method="get",
        ),
        cls="pagination",
    )


@rt
def index(sql: Optional[str] = None, page: int = 1):
    query = sql or DEFAULT_QUERY
    rows, error = fetch_rows(query, page)
    has_next = len(rows) == PAGE_SIZE

    result_section = (
        Div(
            Div(*(result_card(r) for r in rows), cls="results") if rows else P("No results for this page.", cls="muted"),
            pagination_controls(query, page, has_next),
        )
        if not error
        else Div(P(error, cls="muted"))
    )

    return (
        Titled(
            "Cohort timelines",
            Header(H1("Cervical spine CT cohort timeline explorer")),
            Main(
                style,
                Div(
                    H2("SQL query"),
                    Form(
                        Textarea(query, name="sql"),
                        Div(Button("Run query", type="submit"), Span("25 results per page.", cls="muted"), cls="query-actions"),
                        Input(type="hidden", name="page", value=1),
                        method="get",
                        cls="query-card",
                    ),
                ),
                result_section,
            ),
            Footer("Uses FastHTML + FastSQL. Provide a Postgres connection string via environment variables."),
        )
    )


serve()
