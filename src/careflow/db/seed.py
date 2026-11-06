from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb

from careflow import clock
from careflow.config import (
    CLINIC_TIMEZONE,
    SLOT_DAYS_AHEAD,
    SLOT_MINUTES,
    SLOT_TIMES,
    load_settings,
)
from careflow.db.connection import connect, reset_schema

ADMISSION_DAYS = 4

PATIENTS = (
    ("P001", "Ravi Kumar", date(1958, 3, 14), "+91-90000-00001", "Heart failure", 3),
    ("P002", "Lakshmi Menon", date(1951, 7, 2), "+91-90000-00002", "COPD exacerbation", 5),
    (
        "P003",
        "Arjun Reddy",
        date(1969, 11, 23),
        "+91-90000-00003",
        "Type 2 diabetes with hyperglycaemia",
        2,
    ),
    ("P004", "Fatima Shaikh", date(1962, 5, 9), "+91-90000-00004", "Total hip replacement", 7),
    (
        "P005",
        "Joseph Mathew",
        date(1975, 1, 30),
        "+91-90000-00005",
        "Community-acquired pneumonia",
        1,
    ),
)

FUROSEMIDE = ("medication", "Furosemide 40 mg once daily", None, None, None, None)

PLANS = (
    (
        "CP001-v1",
        "P001",
        1,
        "superseded",
        (
            ("follow_up", "Cardiology follow-up visit", "cardiology", 14, None, None),
            FUROSEMIDE,
        ),
    ),
    (
        "CP001-v2",
        "P001",
        2,
        "published",
        (
            ("follow_up", "Cardiology follow-up visit", "cardiology", 7, None, None),
            ("lab", "Basic metabolic panel", "laboratory", 7, None, None),
            FUROSEMIDE,
            (
                "warning_sign",
                "Weight gain over 2 kg in a week",
                None,
                None,
                "urgent",
                {"measurement": "weight_change_kg", "op": ">", "value": 2},
            ),
            (
                "warning_sign",
                "Chest pain or severe breathlessness at rest",
                None,
                None,
                "emergency",
                None,
            ),
            ("activity_rule", "Limit fluids to 1.5 litres a day", None, None, None, None),
        ),
    ),
    (
        "CP002-v1",
        "P002",
        1,
        "published",
        (
            ("follow_up", "Pulmonology follow-up visit", "pulmonology", 14, None, None),
            ("medication", "Tiotropium inhaler once daily", None, None, None, None),
            (
                "warning_sign",
                "Oxygen saturation below 90%",
                None,
                None,
                "urgent",
                {"measurement": "oxygen_saturation_pct", "op": "<", "value": 90},
            ),
            ("warning_sign", "Blue lips or new confusion", None, None, "emergency", None),
            ("activity_rule", "Walk 10 minutes twice a day", None, None, None, None),
        ),
    ),
    (
        "CP003-v1",
        "P003",
        1,
        "published",
        (
            ("follow_up", "Endocrinology follow-up visit", "endocrinology", 14, None, None),
            ("lab", "HbA1c blood test", "laboratory", 30, None, None),
            ("medication", "Metformin 500 mg twice daily", None, None, None, None),
            (
                "warning_sign",
                "Blood glucose above 300 mg/dL",
                None,
                None,
                "urgent",
                {"measurement": "blood_glucose_mg_dl", "op": ">", "value": 300},
            ),
            ("warning_sign", "Fainting or confusion", None, None, "emergency", None),
        ),
    ),
    (
        "CP004-v1",
        "P004",
        1,
        "published",
        (
            ("follow_up", "Orthopedics follow-up visit", "orthopedics", 14, None, None),
            ("follow_up", "Primary care follow-up visit", "primary_care", 30, None, None),
            ("medication", "Apixaban 2.5 mg twice daily", None, None, None, None),
            (
                "warning_sign",
                "Temperature above 38 C",
                None,
                None,
                "urgent",
                {"measurement": "temperature_c", "op": ">", "value": 38},
            ),
            ("warning_sign", "Sudden leg swelling with chest pain", None, None, "emergency", None),
            ("activity_rule", "Do not bend the hip past 90 degrees", None, None, None, None),
        ),
    ),
    (
        "CP005-v1",
        "P005",
        1,
        "published",
        (
            ("follow_up", "Primary care follow-up visit", "primary_care", 7, None, None),
            ("lab", "Chest X-ray", "radiology", 30, None, None),
            (
                "medication",
                "Amoxicillin 500 mg three times daily for 5 days",
                None,
                None,
                None,
                None,
            ),
            (
                "warning_sign",
                "Temperature above 38.5 C",
                None,
                None,
                "urgent",
                {"measurement": "temperature_c", "op": ">", "value": 38.5},
            ),
            ("warning_sign", "Severe difficulty breathing", None, None, "emergency", None),
        ),
    ),
)

CLINICIANS = (
    ("C01", "Dr. Anil Verma", "cardiology"),
    ("C02", "Dr. Priya Nair", "cardiology"),
    ("C03", "Dr. Sunil Rao", "pulmonology"),
    ("C04", "Dr. Kavya Iyer", "endocrinology"),
    ("C05", "Dr. Rahul Bose", "orthopedics"),
    ("C06", "Dr. Meena Pillai", "primary_care"),
    ("C07", "Dr. Imran Khan", "primary_care"),
    ("C08", "Lab Desk", "laboratory"),
    ("C09", "Imaging Desk", "radiology"),
)

APPOINTMENTS = (
    ("A001", "P001", "C01", 9, "10:00", "CP001-v2-01"),
    ("A002", "P004", "C05", 6, "11:00", "CP004-v1-01"),
)


def discharge_date(days_ago: int) -> date:
    return clock.today() - timedelta(days=days_ago)


def first_weekday_from(day: date) -> date:
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def slot_id(clinician_id: str, day: date, start: str) -> str:
    return f"S-{clinician_id}-{day:%Y%m%d}-{start.replace(':', '')}"


def insert_patients(conn: psycopg.Connection) -> None:
    for patient_id, name, born, phone, diagnosis, days_ago in PATIENTS:
        discharged = discharge_date(days_ago)
        conn.execute(
            "INSERT INTO patients VALUES (%s, %s, %s, %s)", (patient_id, name, born, phone)
        )
        conn.execute(
            "INSERT INTO encounters VALUES (%s, %s, %s, %s, %s)",
            (
                f"E{patient_id[1:]}",
                patient_id,
                discharged - timedelta(days=ADMISSION_DAYS),
                discharged,
                diagnosis,
            ),
        )


def insert_care_plans(conn: psycopg.Connection) -> None:
    days_ago = {patient[0]: patient[5] for patient in PATIENTS}
    for plan_id, patient_id, version, status, items in PLANS:
        conn.execute(
            "INSERT INTO care_plans VALUES (%s, %s, %s, %s, %s, %s)",
            (
                plan_id,
                patient_id,
                f"E{patient_id[1:]}",
                version,
                status,
                discharge_date(days_ago[patient_id]),
            ),
        )
        insert_plan_items(conn, plan_id, items)


def insert_plan_items(conn: psycopg.Connection, plan_id: str, items: tuple) -> None:
    for index, item in enumerate(items, start=1):
        kind, description, specialty, due, severity, rule = item
        conn.execute(
            "INSERT INTO care_plan_items VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                f"{plan_id}-{index:02d}",
                plan_id,
                kind,
                description,
                specialty,
                due,
                severity,
                Jsonb(rule) if rule else None,
            ),
        )


def slot_starts() -> list[tuple[date, str]]:
    days = [clock.today() + timedelta(days=offset) for offset in range(1, SLOT_DAYS_AHEAD + 1)]
    return [(day, start) for day in days if day.weekday() < 5 for start in SLOT_TIMES]


def insert_clinicians_and_slots(conn: psycopg.Connection) -> None:
    starts = slot_starts()
    for clinician_id, name, specialty in CLINICIANS:
        conn.execute("INSERT INTO clinicians VALUES (%s, %s, %s)", (clinician_id, name, specialty))
        for day, start in starts:
            starts_at = datetime.combine(day, time.fromisoformat(start), ZoneInfo(CLINIC_TIMEZONE))
            conn.execute(
                "INSERT INTO slots VALUES (%s, %s, %s, %s)",
                (
                    slot_id(clinician_id, day, start),
                    clinician_id,
                    starts_at,
                    starts_at + timedelta(minutes=SLOT_MINUTES),
                ),
            )


def insert_appointments(conn: psycopg.Connection) -> None:
    for appointment_id, patient_id, clinician_id, days_ahead, start, item_id in APPOINTMENTS:
        day = first_weekday_from(clock.today() + timedelta(days=days_ahead))
        conn.execute(
            "INSERT INTO appointments (id, patient_id, slot_id, care_plan_item_id, status,"
            " idempotency_key) VALUES (%s, %s, %s, %s, 'booked', %s)",
            (
                appointment_id,
                patient_id,
                slot_id(clinician_id, day, start),
                item_id,
                f"seed-{appointment_id}",
            ),
        )


def seed(database_url: str) -> None:
    with connect(database_url) as conn:
        reset_schema(conn)
        insert_patients(conn)
        insert_care_plans(conn)
        insert_clinicians_and_slots(conn)
        insert_appointments(conn)


if __name__ == "__main__":
    seed(load_settings().database_url)
