"""
Helper module - Custom helper functions for this bot.

Provides:
    * Re-exports of common nova logging helpers (log_print, etc.)
    * Daily patient-report CSV tracking (Feature 1)
    * Per-note attempt screenshot helper (Feature 2)
"""

import csv
import os
import sys
from datetime import datetime

import system.nova as nova

# Re-export common nova helpers so callers can use helper.* directly
log_print = nova.log_print
initialize = nova.initialize
stop = nova.stop
check_and_wait_if_paused = nova.check_and_wait_if_paused

# Module-level constants
REPORTS_FOLDER = "reports"
MAX_FAILURES = 3

# CSV column order (kept stable for header writing & DictWriter)
REPORT_FIELDNAMES = [
    "note_id",
    "patient_first_name",
    "patient_last_name",
    "patient_phone",
    "patient_dob",
    "clinic_name",
    "status",
    "failure_count",
    "last_attempt_time",
    "note",
]


def _project_root():
    """Return absolute path to the project root (parent of modules/)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def _report_key(note_data):
    """Build the daily-report dict key for a note row / DataFrame row."""
    return "{phone}_{first}_{clinic}_{nid}".format(
        phone=note_data.get("patient_phone", ""),
        first=note_data.get("patient_first_name", ""),
        clinic=note_data.get("clinic_name", ""),
        nid=note_data.get("note_id", ""),
    )


def _content_key(note_data):
    """Build the duplicate-content key from note data (independent of note_id)."""
    return "{first}_{last}_{dob}_{phone}_{note}".format(
        first=note_data.get("patient_first_name", ""),
        last=note_data.get("patient_last_name", ""),
        dob=note_data.get("patient_dob", ""),
        phone=note_data.get("patient_phone", ""),
        note=note_data.get("note", ""),
    )


def get_daily_report_file():
    """
    Return the absolute path of today's patient report CSV.

    Creates the reports/ directory if it does not yet exist. The file
    itself is *not* created here; save_patient_to_report() handles header
    writing on first append.
    """
    reports_dir = os.path.join(_project_root(), REPORTS_FOLDER)
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir, exist_ok=True)

    filename = "patient_report_{date}_v2.csv".format(
        date=datetime.now().strftime("%Y-%m-%d")
    )
    return os.path.join(reports_dir, filename)


def load_patient_report():
    """
    Load today's patient report into memory.

    Returns:
        tuple(dict, set):
            - report_dict keyed by "{patient_phone}_{patient_first_name}_"
              "{clinic_name}_{note_id}" -> row dict (columns from CSV).
            - content_keys set of "{first_name}_{last_name}_{dob}_{phone}_"
              "{note_text}" built only from rows where status == 'success'.
    """
    report_dict = {}
    content_keys = set()

    report_path = get_daily_report_file()
    if not os.path.exists(report_path):
        return report_dict, content_keys

    try:
        with open(report_path, "r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if not row:
                    continue
                key = _report_key(row)
                report_dict[key] = row
                if (row.get("status") or "").strip().lower() == "success":
                    content_keys.add(_content_key({
                        "patient_first_name": row.get("patient_first_name", ""),
                        "patient_last_name": row.get("patient_last_name", ""),
                        "patient_dob": row.get("patient_dob", ""),
                        "patient_phone": row.get("patient_phone", ""),
                        "note": row.get("note", ""),
                    }))
    except Exception as exc:
        nova.log_print(
            "REPORT: Failed to load patient report '{path}': {err} - continuing without it".format(
                path=report_path, err=exc
            ),
            level="WARN",
        )

    return report_dict, content_keys


def save_patient_to_report(note_data, status, failure_count):
    """
    Append one row to today's patient report CSV.

    Writes the header row if the file did not previously exist.

    Args:
        note_data: Mapping with note fields (note_id, patient_first_name,
                   patient_last_name, patient_phone, patient_dob, clinic_name,
                   note).
        status: One of 'success', 'failed', 'timeout', 'verification_failed'.
        failure_count: Cumulative failure count for this note (int or str).
    """
    report_path = get_daily_report_file()
    file_is_new = not os.path.exists(report_path)

    row = {
        "note_id": note_data.get("note_id", ""),
        "patient_first_name": note_data.get("patient_first_name", ""),
        "patient_last_name": note_data.get("patient_last_name", ""),
        "patient_phone": note_data.get("patient_phone", ""),
        "patient_dob": note_data.get("patient_dob", ""),
        "clinic_name": note_data.get("clinic_name", ""),
        "status": status,
        "failure_count": failure_count,
        "last_attempt_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": note_data.get("note", ""),
    }

    try:
        with open(report_path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=REPORT_FIELDNAMES)
            if file_is_new:
                writer.writeheader()
            writer.writerow(row)
    except Exception as exc:
        nova.log_print(
            "REPORT: Failed to append row for note_id={nid} to '{path}': {err}".format(
                nid=note_data.get("note_id", ""), path=report_path, err=exc
            ),
            level="ERROR",
        )


def filter_notes_by_report(notes_dataframe, patient_report, content_keys, update_api_fn):
    """
    Filter the notes DataFrame using today's patient report.

    Skips notes that have already succeeded today, that have exhausted their
    retry budget, and notes whose patient + content combination already
    succeeded under a different note_id (duplicate content). For duplicates,
    the API is updated immediately and the duplicate is logged as 'success'
    in the report.

    Args:
        notes_dataframe: pandas DataFrame of notes to evaluate.
        patient_report: Dict returned by load_patient_report().
        content_keys: Set returned by load_patient_report().
        update_api_fn: Callable(note_id) used to mark duplicates complete.

    Returns:
        tuple(filtered_dataframe, skipped_list)
            - filtered_dataframe: DataFrame containing only notes that should
              be processed this cycle.
            - skipped_list: List of dicts describing every skipped note with
              keys 'note_id' and 'reason'.
    """
    skipped = []

    if notes_dataframe is None or notes_dataframe.empty:
        return notes_dataframe, skipped

    keep_indices = []

    for idx, note in notes_dataframe.iterrows():
        note_dict = note.to_dict() if hasattr(note, "to_dict") else dict(note)
        report_key = _report_key(note_dict)
        content_key = _content_key(note_dict)
        existing = patient_report.get(report_key, {}) or {}
        existing_status = (existing.get("status") or "").strip().lower()

        try:
            existing_failures = int(existing.get("failure_count", 0) or 0)
        except (TypeError, ValueError):
            existing_failures = 0

        if existing_status == "success":
            skipped.append({
                "note_id": note_dict.get("note_id", ""),
                "reason": "already_success",
            })
            continue

        if existing_failures >= MAX_FAILURES:
            skipped.append({
                "note_id": note_dict.get("note_id", ""),
                "reason": "max_failures_reached",
            })
            continue

        if content_key in content_keys:
            note_id = note_dict.get("note_id", "")
            nova.log_print(
                "REPORT: Duplicate content detected for note_id={nid} "
                "(patient {first} {last}); marking complete via API.".format(
                    nid=note_id,
                    first=note_dict.get("patient_first_name", ""),
                    last=note_dict.get("patient_last_name", ""),
                ),
                level="WARN",
            )
            try:
                if callable(update_api_fn):
                    update_api_fn(note_id)
            except Exception as exc:
                nova.log_print(
                    "REPORT: update_api_fn failed for duplicate note_id={nid}: {err}".format(
                        nid=note_id, err=exc
                    ),
                    level="ERROR",
                )

            save_patient_to_report(note_dict, "success", 0)
            patient_report[report_key] = {
                "status": "success",
                "failure_count": "0",
            }
            skipped.append({
                "note_id": note_id,
                "reason": "duplicate_content",
            })
            continue

        keep_indices.append(idx)

    filtered = notes_dataframe.loc[keep_indices].reset_index(drop=True)
    return filtered, skipped


def take_screenshot(page=None, prefix="screenshot"):
    """
    Save a timestamped screenshot to the project's screenshots/ directory.

    Args:
        page: Playwright Page object. If None, the call is a no-op (the
              caller most likely no longer has a live browser context).
        prefix: Filename prefix used for the saved screenshot.

    Returns:
        Absolute path of the saved screenshot, or None on failure.
    """
    if page is None:
        return None

    try:
        screenshots_dir = os.path.join(_project_root(), "screenshots")
        if not os.path.exists(screenshots_dir):
            os.makedirs(screenshots_dir, exist_ok=True)

        filename = "{prefix}_{ts}.png".format(
            prefix=prefix,
            ts=datetime.now().strftime("%Y%m%d_%H%M%S"),
        )
        path = os.path.join(screenshots_dir, filename)
        page.screenshot(path=path, full_page=False)
        nova.log_print("SCREENSHOT: Saved to {path}".format(path=path), level="TRACE")
        return path
    except Exception as exc:
        line_number = sys.exc_info()[2].tb_lineno if sys.exc_info()[2] else "?"
        nova.log_print(
            "SCREENSHOT: Failed ({err}) at line {ln}".format(err=exc, ln=line_number),
            level="WARN",
        )
        return None
