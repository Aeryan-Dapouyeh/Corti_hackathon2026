import os
import pandas as pd
import uuid
import requests
import time
import json
import queue
import numpy as np
import threading
from urllib.parse import quote
import sounddevice as sd
import websocket
from dotenv import load_dotenv
from scipy.io.wavfile import write

load_dotenv()

CLIENT_ID = os.environ["CORTI_CLIENT_ID"]
CLIENT_SECRET = os.environ["CORTI_CLIENT_SECRET"]
ENVIRONMENT = os.getenv("CORTI_ENVIRONMENT", "eu")
TENANT = os.getenv("CORTI_TENANT", "base")



def get_access_token():
    url = (
        f"https://auth.{ENVIRONMENT}.corti.app"
        f"/realms/{TENANT}/protocol/openid-connect/token"
    )

    response = requests.post(
        url,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials",
            "scope": "openid",
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json()["access_token"]


def extract_facts(text):
    token = get_access_token()

    url = (
        f"https://api.{ENVIRONMENT}.corti.app"
        "/v2/tools/extract-facts"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Tenant-Name": TENANT,
        "Content-Type": "application/json",
    }

    payload = {
        "context": [
            {
                "type": "text",
                "text": text,
            }
        ],
        "outputLanguage": "en",
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=120,
    )

    response.raise_for_status()

    return response.json()


def codes_to_dataframe(coding_result):

    rows = []

    for item in coding_result["codes"]:

        evidences = item.get("evidences", [])

        evidence_text = [
            evidence["text"]
            for evidence in evidences
        ]

        rows.append(
            {
                "system": item["system"],
                "code": item["code"],
                "display": item["display"],
                "evidence": " | ".join(evidence_text),
            }
        )

    return pd.DataFrame(rows)


def read_patient_journal(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()



def predict_codes(text, token):

    url = (
        f"https://api.{ENVIRONMENT}.corti.app"
        "/v2/tools/coding/"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Tenant-Name": TENANT,
        "Content-Type": "application/json",
    }

    payload = {
        "system": [
            "icd10int-inpatient"
        ],
        "context": [
            {
                "type": "text",
                "text": text
            }
        ]
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=120,
    )

    response.raise_for_status()

    return response.json()


def extractFacts(journal):

    facts_result = extract_facts(journal)
    
    for fact in facts_result["facts"]:
        print(fact)

    df_facts = pd.DataFrame(facts_result["facts"])

    return df_facts


def extractCodes(journal):
    token = get_access_token()
    coding_result = predict_codes(text=journal, token=token)

    print(coding_result)


    for code in coding_result["codes"]:

        print("System:", code["system"])
        print("Code:", code["code"])
        print("Diagnosis:", code["display"])
        print()

    df_codes = codes_to_dataframe(coding_result)

    print(df_codes)

    return df_codes



def create_interaction(token):
    url = f"https://api.{ENVIRONMENT}.corti.app/v2/interactions/"

    headers = {
        "Authorization": f"Bearer {token}",
        "Tenant-Name": TENANT,
        "Content-Type": "application/json",
    }

    payload = {
        "encounter": {
            "identifier": str(uuid.uuid4()),
            "status": "planned",
            "type": "first_consultation",
            "title": "Patient journal text generation",
        }
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()["interactionId"]


def generate_text_from_journal(
    journal,
    output_path="generated_patient_summary.txt",
    template_key="corti-brief-clinical-note",
):
    token = get_access_token()

    # Corti document generation requires an interaction
    interaction_id = create_interaction(token)

    url = (
        f"https://api.{ENVIRONMENT}.corti.app"
        f"/v2/interactions/{interaction_id}/documents"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Tenant-Name": TENANT,
        "Content-Type": "application/json",

        # Generate the document without retaining it in Corti
        "X-Corti-Retention-Policy": "none",
    }

    payload = {
        "context": [
            {
                "type": "string",
                "data": journal,
            }
        ],
        "templateKey": template_key,
        "name": "Generated patient summary",
        "outputLanguage": "en",
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=120,
    )

    response.raise_for_status()

    document = response.json()

    # Combine Corti's generated sections into one text document
    sections = document.get("sections", [])

    generated_text = []

    for section in sections:
        section_name = section.get("name", "")
        section_text = section.get("text", "")

        if section_text:
            if section_name:
                generated_text.append(
                    f"{section_name}\n{'-' * len(section_name)}\n{section_text}"
                )
            else:
                generated_text.append(section_text)

    generated_text = "\n\n".join(generated_text)

    # Save locally
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(generated_text)

    print(f"Generated document saved to: {output_path}")

    return generated_text


def record_audio(
    output_path="patient_interaction.wav",
    sample_rate=16000,
):
    print("\nRecording started.")
    print("Doctor and patient can now speak.")
    print("Press ENTER to stop recording.\n")

    audio_chunks = []

    def callback(indata, frames, time_info, status):
        if status:
            print(status)

        audio_chunks.append(indata.copy())

    with sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        callback=callback,
    ):
        input()

    audio = np.concatenate(audio_chunks, axis=0)

    write(
        output_path,
        sample_rate,
        audio,
    )

    print(f"Audio saved to {output_path}")

    return output_path


def create_interaction(token):

    url = (
        f"https://api.{ENVIRONMENT}.corti.app"
        "/v2/interactions/"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Tenant-Name": TENANT,
        "Content-Type": "application/json",
    }

    payload = {
        "encounter": {
            "identifier": str(uuid.uuid4()),
            "status": "planned",
            "type": "first_consultation",
            "title": "Doctor patient consultation",
        }
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()["interactionId"]



def dictate_patient_journal(
    output_path="dictated_patient_journal.txt",
    duration_seconds=30,
    language="en",
):

    # -----------------------------------
    # Audio configuration
    # -----------------------------------

    sample_rate = 16000
    channels = 1
    block_duration = 0.25  # 250 ms

    block_size = int(
        sample_rate * block_duration
    )

    # -----------------------------------
    # Authenticate with Corti
    # -----------------------------------

    token = get_access_token()

    ws_url = (
        f"wss://api.{ENVIRONMENT}.corti.app"
        f"/audio-bridge/v2/transcribe"
        f"?tenant-name={quote(TENANT)}"
        f"&token={quote(f'Bearer {token}')}"
    )

    print("Connecting to Corti...")

    ws = websocket.create_connection(
        ws_url,
        timeout=10,
    )

    # -----------------------------------
    # Configure Corti dictation
    # -----------------------------------

    config = {
        "type": "config",
        "configuration": {
            "primaryLanguage": language,
            "interimResults": True,

            # Dictation-style punctuation:
            # Say "period", "comma",
            # "new paragraph", etc.
            "spokenPunctuation": True,
            "automaticPunctuation": False,

            "audioFormat": (
                "audio/pcm; "
                "rate=16000; "
                "channels=1; "
                "bits=16; "
                "endian=little; "
                "encoding=sint"
            ),

            "formatting": {
                "numbers": "numerals_above_nine",
                "measurements": "abbreviated",
            },
        },
    }

    ws.send(json.dumps(config))

    # -----------------------------------
    # Wait until Corti accepts config
    # -----------------------------------

    while True:

        message = json.loads(ws.recv())

        message_type = message.get("type")

        if message_type == "CONFIG_ACCEPTED":
            print("Corti dictation ready.")
            break

        if message_type in {
            "CONFIG_DENIED",
            "CONFIG_TIMEOUT",
            "error",
        }:
            ws.close()

            raise RuntimeError(
                f"Corti rejected configuration: {message}"
            )

    # -----------------------------------
    # Hold transcript results
    # -----------------------------------

    final_segments = []

    finished = threading.Event()

    # -----------------------------------
    # Receive Corti messages
    # -----------------------------------

    def receive_messages():

        ws.settimeout(1)

        while not finished.is_set():

            try:
                raw_message = ws.recv()

            except websocket.WebSocketTimeoutException:
                continue

            except websocket.WebSocketConnectionClosedException:
                break

            if not raw_message:
                continue

            try:
                message = json.loads(raw_message)

            except (json.JSONDecodeError, TypeError):
                continue

            message_type = message.get("type")

            # ---------------------------
            # Transcript
            # ---------------------------

            if message_type == "transcript":

                data = message["data"]

                text = data["text"]

                if data["isFinal"]:

                    final_segments.append(text)

                    print(
                        "\nFINAL:",
                        text
                    )

                else:

                    print(
                        "\rInterim:",
                        text,
                        end="",
                        flush=True,
                    )

            # ---------------------------
            # Error
            # ---------------------------

            elif message_type == "error":

                print(
                    "\nCorti error:",
                    message
                )

            # ---------------------------
            # Session finished
            # ---------------------------

            elif message_type == "ended":

                finished.set()
                break

    receiver_thread = threading.Thread(
        target=receive_messages,
        daemon=True,
    )

    receiver_thread.start()

    # -----------------------------------
    # Microphone queue
    # -----------------------------------

    audio_queue = queue.Queue()

    def audio_callback(
        indata,
        frames,
        time_info,
        status,
    ):

        if status:
            print(
                "\nAudio warning:",
                status
            )

        audio_queue.put(
            bytes(indata)
        )

    # -----------------------------------
    # Start microphone
    # -----------------------------------

    print()
    print(
        f"Start dictating. Recording for "
        f"{duration_seconds} seconds..."
    )
    print()

    start_time = time.monotonic()

    with sd.RawInputStream(
        samplerate=sample_rate,
        blocksize=block_size,
        channels=channels,
        dtype="int16",
        callback=audio_callback,
    ):

        while (
            time.monotonic() - start_time
            < duration_seconds
        ):

            try:

                audio_chunk = audio_queue.get(
                    timeout=0.5
                )

                ws.send(
                    audio_chunk,
                    opcode=websocket.ABNF.OPCODE_BINARY,
                )

            except queue.Empty:
                continue

    # Send any audio still sitting in the queue
    while not audio_queue.empty():

        audio_chunk = audio_queue.get_nowait()

        ws.send(
            audio_chunk,
            opcode=websocket.ABNF.OPCODE_BINARY,
        )

    # -----------------------------------
    # End Corti session
    # -----------------------------------

    ws.send(
        json.dumps(
            {
                "type": "end"
            }
        )
    )

    # Give Corti time to return remaining
    # final transcript segments
    finished.wait(timeout=15)

    ws.close()

    receiver_thread.join(timeout=2)

    # -----------------------------------
    # Build patient journal
    # -----------------------------------

    journal_text = " ".join(
        segment.strip()
        for segment in final_segments
        if segment.strip()
    )

    # -----------------------------------
    # Save patient journal
    # -----------------------------------

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:

        file.write(journal_text)

    print()
    print("=" * 60)
    print("PATIENT JOURNAL")
    print("=" * 60)
    print(journal_text)
    print("=" * 60)

    print(
        f"\nSaved journal to: {output_path}"
    )

    return journal_text


from pathlib import Path
import re
import uuid

import pandas as pd


# ============================================================
# Helpers
# ============================================================

def make_id(prefix):
    return f"{prefix}-JRN-{uuid.uuid4().hex[:8].upper()}"


def get_fact_time():
    return pd.Timestamp.now(
        tz="Europe/Copenhagen"
    ).strftime("%Y-%m-%dT%H:%M:%S")


# ============================================================
# Vital-sign parsing
# ============================================================

def parse_vital(text):

    text = str(text).strip()

    # Blood pressure creates TWO rows
    match = re.match(
        r"^Blood pressure\s+"
        r"(\d+(?:\.\d+)?)\s*/\s*"
        r"(\d+(?:\.\d+)?)\s*mmHg\.?$",
        text,
        re.IGNORECASE,
    )

    if match:
        systolic = float(match.group(1))
        diastolic = float(match.group(2))

        return [
            (
                "Systolic blood pressure",
                systolic,
                "mmHg",
            ),
            (
                "Diastolic blood pressure",
                diastolic,
                "mmHg",
            ),
        ]

    patterns = [
        (
            r"^Temperature\s+(-?\d+(?:\.\d+)?)\s*([CF])\.?$",
            "Temperature",
            lambda m: m.group(2).upper(),
        ),
        (
            r"^Heart rate\s+(\d+(?:\.\d+)?)\s*bpm\.?$",
            "Pulse",
            lambda m: "bpm",
        ),
        (
            r"^Respiratory rate\s+(\d+(?:\.\d+)?)\s*/min\.?$",
            "Respiratory rate",
            lambda m: "breaths/min",
        ),
        (
            r"^Oxygen saturation\s+(\d+(?:\.\d+)?)%\s*.*$",
            "SpO2",
            lambda m: "%",
        ),
    ]

    for pattern, measurement_type, unit_function in patterns:

        match = re.match(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:

            value = float(match.group(1))
            unit = unit_function(match)

            return [
                (
                    measurement_type,
                    value,
                    unit,
                )
            ]

    return []


# ============================================================
# Laboratory parsing
# ============================================================

LAB_MAP = {
    "white blood cell count": (
        "White Blood Cell Count",
        "WBC",
        "White Blood Cell Count",
    ),
    "hemoglobin": (
        "Hemoglobin",
        "HGB",
        "Hemoglobin",
    ),
    "platelet count": (
        "Platelet count",
        "PLT",
        "Platelet count",
    ),
    "sodium": (
        "Sodium",
        "NA",
        "Sodium",
    ),
    "potassium": (
        "Potassium",
        "K",
        "Potassium",
    ),
    "creatinine": (
        "Creatinine",
        "CREA",
        "Creatinine",
    ),
    "glucose": (
        "Glucose",
        "GLU",
        "Glucose",
    ),
    "c-reactive protein": (
        "C-reactive protein",
        "CRP",
        "CRP",
    ),
}


def parse_lab(text):

    text = str(text).strip().rstrip(".")

    for prefix, names in sorted(
        LAB_MAP.items(),
        key=lambda x: -len(x[0]),
    ):

        if not text.lower().startswith(prefix):
            continue

        remaining = text[len(prefix):].strip()

        match = re.match(
            r"^(-?\d+(?:\.\d+)?)\s+(.+)$",
            remaining,
        )

        # e.g. "Elevated white blood cell count"
        # has no actual numerical measurement
        if match is None:
            return None

        component, base, common = names

        return {
            "ComponentName": component,
            "BaseName": base,
            "CommonName": common,
            "NumericValue": float(match.group(1)),
            "Unit": match.group(2).strip(),
        }

    return None


# ============================================================
# Prescription parsing
# ============================================================

def parse_home_medication(text):

    text = str(text).strip().rstrip(".")

    # Example:
    # Metformin 1000 mg twice daily

    match = re.match(
        r"^(?P<drug>.+?)\s+"
        r"(?P<dose>\d+(?:\.\d+)?)\s*"
        r"(?P<unit>mg|g|mcg|µg|mL|ml|units?)\s+"
        r"(?P<frequency>.+)$",
        text,
        re.IGNORECASE,
    )

    if match:

        data = match.groupdict()

        return {
            "Drug": data["drug"].strip(),
            "Dose": float(data["dose"]),
            "DoseUnit": data["unit"],
            "Frequency": data["frequency"].strip(),
        }

    # Example:
    # Tiotropium inhaler daily

    match = re.match(
        r"^(?P<drug>.+?)\s+"
        r"(?P<frequency>"
        r"once daily|twice daily|daily|nightly|as needed"
        r")$",
        text,
        re.IGNORECASE,
    )

    if match:

        return {
            "Drug": match.group("drug").strip(),
            "Dose": "",
            "DoseUnit": "",
            "Frequency": match.group("frequency"),
        }

    return None


# ============================================================
# Medication plans
# ============================================================

def parse_planned_medications(text):

    text = str(text).strip().rstrip(".")

    medications = []

    # Oxygen
    if re.search(
        r"\bstart\s+oxygen\b",
        text,
        re.IGNORECASE,
    ):

        route = ""

        if "nasal cannula" in text.lower():
            route = "nasal cannula"

        medications.append(
            ("Oxygen", route)
        )

    # For this prototype these are medications appearing in
    # the dummy journal. Extend this list later.
    known_drugs = [
        "ceftriaxone",
        "azithromycin",
    ]

    for drug in known_drugs:

        if not re.search(
            rf"\b{drug}\b",
            text,
            re.IGNORECASE,
        ):
            continue

        if not re.search(
            r"\b(start|continue)\b",
            text,
            re.IGNORECASE,
        ):
            continue

        route = ""

        if re.search(
            r"\bIV\b",
            text,
            re.IGNORECASE,
        ):
            route = "IV"

        medications.append(
            (
                drug.capitalize(),
                route,
            )
        )

    return medications


# ============================================================
# Main routing function
# ============================================================


def insert_corti_data_into_tables(
    data_dir="Data",
    output_dir="GeneratedData",
    facts_path="facts.csv",
    codes_path="medical_codes.csv",
    encounter_key="E0001",
):
    from pathlib import Path
    import re
    import uuid
    import pandas as pd

    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Same timestamp for everything extracted in this run
    now = pd.Timestamp.now(
        tz="Europe/Copenhagen"
    ).strftime("%Y-%m-%dT%H:%M:%S")

    today = now[:10]

    def make_id(prefix):
        return f"{prefix}-JRN-{uuid.uuid4().hex[:8].upper()}"

    def load_table(filename):
        path = data_dir / filename

        if path.exists():
            return pd.read_csv(path)

        # Also allows filenames such as Vitals(1).csv
        stem = Path(filename).stem
        matches = list(data_dir.glob(f"{stem}*.csv"))

        if not matches:
            raise FileNotFoundError(
                f"Could not find {filename} in {data_dir}"
            )

        return pd.read_csv(matches[0])

    # --------------------------------------------------------
    # Load original tables
    # --------------------------------------------------------

    tables = {
        "Population.csv": load_table("Population.csv"),
        "Vitals.csv": load_table("Vitals.csv"),
        "Bloodtests.csv": load_table("Bloodtests.csv"),
        "MedicationAdministrations.csv":
            load_table("MedicationAdministrations.csv"),
        "Prescriptions.csv": load_table("Prescriptions.csv"),
        "Flowsheet.csv": load_table("Flowsheet.csv"),
        "Diagnosis.csv": load_table("Diagnosis.csv"),
    }

    facts = pd.read_csv(facts_path)
    codes = pd.read_csv(codes_path)

    # --------------------------------------------------------
    # Resolve patient identifiers
    # --------------------------------------------------------

    population = tables["Population.csv"]

    patient_rows = population[
        population["EncounterKey"].astype(str)
        == str(encounter_key)
    ]

    if patient_rows.empty:
        raise ValueError(
            f"{encounter_key} was not found in Population.csv"
        )

    patient = patient_rows.iloc[0]

    enterprise_id = patient["EnterpriseId"]
    patient_durable_key = patient["PatientDurableKey"]

    # --------------------------------------------------------
    # Containers for new rows
    # --------------------------------------------------------

    new_vitals = []
    new_labs = []
    new_prescriptions = []
    new_medications = []
    new_diagnoses = []
    unmapped = []

    # --------------------------------------------------------
    # Parse Corti facts
    # --------------------------------------------------------

    for _, fact in facts.iterrows():

        group = str(fact["group"]).strip().lower()
        text = str(fact["value"]).strip().rstrip(".")

        mapped = False

        # ====================================================
        # VITALS
        # ====================================================

        if group == "vital-signs":

            measurements = []

            # Blood pressure
            m = re.search(
                r"blood pressure\s+"
                r"(\d+(?:\.\d+)?)\s*/\s*"
                r"(\d+(?:\.\d+)?)",
                text,
                re.I,
            )

            if m:
                measurements.extend([
                    (
                        "Systolic blood pressure",
                        float(m.group(1)),
                        "mmHg",
                    ),
                    (
                        "Diastolic blood pressure",
                        float(m.group(2)),
                        "mmHg",
                    ),
                ])

            else:

                patterns = [
                    (
                        r"temperature\s+(-?\d+(?:\.\d+)?)\s*([CF])",
                        "Temperature",
                        lambda m: m.group(2).upper(),
                    ),
                    (
                        r"heart rate\s+(\d+(?:\.\d+)?)",
                        "Pulse",
                        lambda m: "bpm",
                    ),
                    (
                        r"respiratory rate\s+(\d+(?:\.\d+)?)",
                        "Respiratory rate",
                        lambda m: "breaths/min",
                    ),
                    (
                        r"oxygen saturation\s+(\d+(?:\.\d+)?)",
                        "SpO2",
                        lambda m: "%",
                    ),
                ]

                for pattern, name, unit_func in patterns:

                    m = re.search(pattern, text, re.I)

                    if m:
                        measurements.append(
                            (
                                name,
                                float(m.group(1)),
                                unit_func(m),
                            )
                        )
                        break

            for measurement_type, value, unit in measurements:

                new_vitals.append({
                    "VitalsFlowsheetValueKey": make_id("VFV"),
                    "EncounterKey": encounter_key,
                    "EnterpriseId": enterprise_id,
                    "StringValue": str(value),
                    "NumericValue": value,
                    "Unit": unit,
                    "MeasurementType": measurement_type,
                    "TakenInstant": now,
                    "IsAbnormal": False,
                    "AbnormalType": "",
                })

            mapped = len(measurements) > 0

        # ====================================================
        # LABORATORY RESULTS
        # ====================================================

        elif group == "laboratory-results":

            lab_names = {
                "white blood cell count":
                    ("White Blood Cell Count", "WBC"),
                "hemoglobin":
                    ("Hemoglobin", "HGB"),
                "platelet count":
                    ("Platelet count", "PLT"),
                "sodium":
                    ("Sodium", "NA"),
                "potassium":
                    ("Potassium", "K"),
                "creatinine":
                    ("Creatinine", "CREA"),
                "glucose":
                    ("Glucose", "GLU"),
                "c-reactive protein":
                    ("C-reactive protein", "CRP"),
            }

            for prefix, (component, basename) in lab_names.items():

                if not text.lower().startswith(prefix):
                    continue

                remaining = text[len(prefix):].strip()

                m = re.match(
                    r"(-?\d+(?:\.\d+)?)\s+(.+)",
                    remaining,
                )

                # Do not add things such as
                # "Elevated white blood cell count"
                # because there is no numeric result.
                if not m:
                    break

                value = float(m.group(1))
                unit = m.group(2)

                new_labs.append({
                    "EncounterKey": encounter_key,
                    "EnterpriseId": enterprise_id,
                    "LabOrderEpicId": make_id("LAB"),
                    "SpecimenType": "Blood",
                    "OrderType": "Journal extraction",
                    "ComponentName": component,
                    "BaseName": basename,
                    "CommonName": component,
                    "CollectionInstant": now,
                    "ResultInstant": now,
                    "ResultStatus": "Extracted",
                    "Flag": "",
                    "Value": value,
                    "NumericValue": value,
                    "Unit": unit,
                    "ReferenceValueLow": "",
                    "ReferenceValueHigh": "",
                    "FinalResultStatus": "Journal review",
                    "IsFinal": False,
                    "IsAbnormal": False,
                })

                mapped = True
                break

        # ====================================================
        # EXISTING / HOME MEDICATIONS
        # ====================================================

        elif group == "medications-prior-to-visit":

            m = re.match(
                r"(.+?)\s+"
                r"(\d+(?:\.\d+)?)\s*"
                r"(mg|g|mcg|µg|ml|mL|units?)\s+"
                r"(.+)",
                text,
                re.I,
            )

            if m:

                new_prescriptions.append({
                    "PrescriptionKey": make_id("RX"),
                    "PatientDurableKey":
                        patient_durable_key,
                    "EncounterKey": encounter_key,
                    "EnterpriseId": enterprise_id,
                    "Drug": m.group(1),
                    "ATCCode": "",
                    "Dose": float(m.group(2)),
                    "DoseUnit": m.group(3),
                    "Route": "",
                    "Frequency": m.group(4),
                    "PrescriptionStartInstant": now,
                    "PrescriptionEndInstant": "",
                    "Status":
                        "Extracted from patient journal",
                })

                mapped = True

            else:
                # e.g. "Tiotropium inhaler daily"
                m = re.match(
                    r"(.+?)\s+"
                    r"(daily|twice daily|once daily|"
                    r"nightly|as needed)",
                    text,
                    re.I,
                )

                if m:
                    new_prescriptions.append({
                        "PrescriptionKey": make_id("RX"),
                        "PatientDurableKey":
                            patient_durable_key,
                        "EncounterKey": encounter_key,
                        "EnterpriseId": enterprise_id,
                        "Drug": m.group(1),
                        "ATCCode": "",
                        "Dose": "",
                        "DoseUnit": "",
                        "Route": "",
                        "Frequency": m.group(2),
                        "PrescriptionStartInstant": now,
                        "PrescriptionEndInstant": "",
                        "Status":
                            "Extracted from patient journal",
                    })

                    mapped = True

        # ====================================================
        # NEW MEDICATION PLANS
        # ====================================================

        elif group == "plan":

            medications = []

            if re.search(r"\boxygen\b", text, re.I):
                medications.append(
                    ("Oxygen", "nasal cannula"
                     if "nasal cannula" in text.lower()
                     else "")
                )

            if re.search(r"\bceftriaxone\b", text, re.I):
                medications.append(
                    (
                        "Ceftriaxone",
                        "IV" if re.search(
                            r"\bIV\b", text, re.I
                        ) else "",
                    )
                )

            if re.search(r"\bazithromycin\b", text, re.I):
                medications.append(
                    (
                        "Azithromycin",
                        "IV" if re.search(
                            r"\bIV\b", text, re.I
                        ) else "",
                    )
                )

            for medication_name, route in medications:

                new_medications.append({
                    "MedicationAdministrationKey":
                        make_id("MED"),
                    "EncounterKey": encounter_key,
                    "EnterpriseId": enterprise_id,
                    "MedicationName": medication_name,
                    "ATCCode": "",
                    "Dose": "",
                    "DoseUnit": "",
                    "Route": route,
                    "AdministrationInstant": now,
                    "Status":
                        "Planned from journal",
                    "Indication":
                        "Extracted from patient journal",
                })

            mapped = len(medications) > 0

        # ----------------------------------------------------
        # Anything not safely mapped goes to FactSheet
        # ----------------------------------------------------

        if not mapped:

            unmapped.append({
                "group": fact["group"],
                "text": fact["text"],
                "value": fact["value"],
                "EncounterKey": encounter_key,
                "RecordedInstant": now,
            })

    # ========================================================
    # MEDICAL CODES -> DIAGNOSIS
    # ========================================================

    for _, code in codes.iterrows():

        system = str(code["system"])
        medical_code = str(code["code"])

        new_diagnoses.append({
            "DiagnosisKey": make_id("DX"),
            "EncounterKey": encounter_key,
            "EnterpriseId": enterprise_id,

            # Preserve Corti's original coding system/code
            "DiagnosisEpicId":
                f"CORTI|{system}|{medical_code}",

            "Name": code["display"],
            "DiagnosisStartDate": today,
            "DiagnosisEndDate": "",
            "Type": f"Corti ({system})",

            # Corti returned international ICD-10,
            # not Danish SKS, so do not falsely call it SKS.
            "SKSCode":
                medical_code
                if "sks" in system.lower()
                else "",

            "IsActionDiagnosis": False,
        })

    # ========================================================
    # Append IN MEMORY
    # ========================================================

    additions = {
        "Vitals.csv": new_vitals,
        "Bloodtests.csv": new_labs,
        "MedicationAdministrations.csv":
            new_medications,
        "Prescriptions.csv": new_prescriptions,
        "Diagnosis.csv": new_diagnoses,
    }

    generated_tables = {}

    for filename, original in tables.items():

        if filename in additions:
            new_rows = pd.DataFrame(
                additions[filename]
            )

            if not new_rows.empty:

                new_rows = new_rows.reindex(
                    columns=original.columns
                )

                generated = pd.concat(
                    [original, new_rows],
                    ignore_index=True,
                )

            else:
                generated = original.copy()

        else:
            generated = original.copy()

        generated_tables[filename] = generated

    # ========================================================
    # SAVE AS NEW FILES
    # ========================================================

    for filename, df in generated_tables.items():

        df.to_csv(
            output_dir / filename,
            index=False,
        )

    pd.DataFrame(unmapped).to_csv(
        output_dir / "FactSheet.csv",
        index=False,
    )

    print(f"New dataset saved to: {output_dir}")

    print(f"Vitals added: {len(new_vitals)}")
    print(f"Lab results added: {len(new_labs)}")
    print(
        f"Medication administrations added: "
        f"{len(new_medications)}"
    )
    print(
        f"Prescriptions added: "
        f"{len(new_prescriptions)}"
    )
    print(
        f"Diagnoses added: "
        f"{len(new_diagnoses)}"
    )
    print(f"Unmapped facts: {len(unmapped)}")

    return generated_tables




def generate_patient_timeline(
    data_dir,
    output_filename="PatientTimeline.csv",
):
    data_dir = Path(data_dir)

    timeline_parts = []

    def load_table(name):
        path = data_dir / f"{name}.csv"

        if path.exists():
            return pd.read_csv(path)

        # Also supports names such as Vitals(1).csv
        matches = list(data_dir.glob(f"{name}*.csv"))

        if matches:
            return pd.read_csv(matches[0])

        return None

    # ========================================================
    # Population
    # Used to determine encounter start times for diagnoses
    # ========================================================

    population = load_table("Population")

    # ========================================================
    # VITALS
    # ========================================================

    df = load_table("Vitals")

    if df is not None:

        part = pd.DataFrame({
            "EncounterKey": df["EncounterKey"],
            "EventTime": df["TakenInstant"],
            "SourceTable": "Vitals",
            "EventType": df["MeasurementType"],
            "Value": df["NumericValue"],
            "Unit": df["Unit"],
        })

        timeline_parts.append(part)

    # ========================================================
    # BLOOD TESTS
    # ========================================================

    df = load_table("Bloodtests")

    if df is not None:

        part = pd.DataFrame({
            "EncounterKey": df["EncounterKey"],
            "EventTime": df["CollectionInstant"],
            "SourceTable": "Bloodtests",
            "EventType": df["ComponentName"],
            "Value": df["NumericValue"],
            "Unit": df["Unit"],
        })

        timeline_parts.append(part)

    # ========================================================
    # FLOWSHEET
    # ========================================================

    df = load_table("Flowsheet")

    if df is not None:

        part = pd.DataFrame({
            "EncounterKey": df["EncounterKey"],
            "EventTime": df["TakenInstant"],
            "SourceTable": "Flowsheet",
            "EventType": df["DisplayName"],
            "Value": df["NumericValue"],
            "Unit": None,
        })

        timeline_parts.append(part)

    # ========================================================
    # MEDICATION ADMINISTRATIONS
    # ========================================================

    df = load_table("MedicationAdministrations")

    if df is not None:

        part = pd.DataFrame({
            "EncounterKey": df["EncounterKey"],
            "EventTime": df["AdministrationInstant"],
            "SourceTable": "MedicationAdministrations",
            "EventType": df["MedicationName"],
            "Value": df["Dose"],
            "Unit": df["DoseUnit"],
        })

        timeline_parts.append(part)

    # ========================================================
    # PRESCRIPTIONS
    # ========================================================

    df = load_table("Prescriptions")

    if df is not None:

        part = pd.DataFrame({
            "EncounterKey": df["EncounterKey"],
            "EventTime": df["PrescriptionStartInstant"],
            "SourceTable": "Prescriptions",
            "EventType": df["Drug"],
            "Value": df["Dose"],
            "Unit": df["DoseUnit"],
        })

        timeline_parts.append(part)

    # ========================================================
    # DIAGNOSES
    # ========================================================

    df = load_table("Diagnosis")

    if df is not None:

        diagnosis_times = []

        for _, row in df.iterrows():

            diagnosis_date = pd.to_datetime(
                row["DiagnosisStartDate"],
                errors="coerce",
            )

            event_time = diagnosis_date

            # If diagnosis occurred on the encounter start date,
            # use the actual encounter start time.
            if population is not None:

                patient_encounter = population[
                    population["EncounterKey"].astype(str)
                    == str(row["EncounterKey"])
                ]

                if not patient_encounter.empty:

                    encounter = patient_encounter.iloc[0]

                    start_time = pd.to_datetime(
                        encounter["StartInstant"],
                        errors="coerce",
                    )

                    if (
                        pd.notna(start_time)
                        and pd.notna(diagnosis_date)
                        and start_time.date()
                        == diagnosis_date.date()
                    ):
                        event_time = start_time

            diagnosis_times.append(event_time)

        part = pd.DataFrame({
            "EncounterKey": df["EncounterKey"],
            "EventTime": diagnosis_times,
            "SourceTable": "Diagnosis",
            "EventType": df["Name"],
            "Value": df["SKSCode"],
            "Unit": None,
        })

        timeline_parts.append(part)

    # ========================================================
    # COMBINE
    # ========================================================

    if not timeline_parts:
        raise ValueError(
            f"No supported tables found in {data_dir}"
        )

    timeline = pd.concat(
        timeline_parts,
        ignore_index=True,
    )

    # Convert to proper datetime for sorting
    timeline["EventTime"] = pd.to_datetime(
        timeline["EventTime"],
        errors="coerce",
    )

    # Remove rows without a timestamp
    timeline = timeline.dropna(
        subset=["EventTime"]
    )

    # Sort chronologically
    timeline = timeline.sort_values(
        ["EncounterKey", "EventTime"],
        kind="stable",
    ).reset_index(drop=True)

    # Return timestamps to ISO format
    timeline["EventTime"] = (
        timeline["EventTime"]
        .dt.strftime("%Y-%m-%dT%H:%M:%S")
    )

    # Save
    output_path = data_dir / output_filename

    timeline.to_csv(
        output_path,
        index=False,
    )

    print(f"Timeline saved to: {output_path}")
    print(f"Number of events: {len(timeline)}")

    return timeline








