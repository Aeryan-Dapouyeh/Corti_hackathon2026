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
from Utils import extract_facts, insert_corti_data_into_tables, predict_codes, get_access_token, codes_to_dataframe, read_patient_journal, generate_text_from_journal, dictate_patient_journal, extractFacts, extractCodes, generate_patient_timeline


print("Hello world!")


load_dotenv()

CLIENT_ID = os.environ["CORTI_CLIENT_ID"]
CLIENT_SECRET = os.environ["CORTI_CLIENT_SECRET"]
ENVIRONMENT = os.getenv("CORTI_ENVIRONMENT", "eu")
TENANT = os.getenv("CORTI_TENANT", "base")




if __name__ == "__main__":

    ####### To Generate text from patient journal #######
    # journal = read_patient_journal("Dummy_patientjournal.txt")
    # generated_text = generate_text_from_journal(journal, output_path="generated_patient_summary.txt")
    # print("\nGenerated text:")
    # print(generated_text)


    ####### To Extract facts from text #######
    # df_facts = extractFacts(journal)
    # df_codes = extractCodes(journal)


    ####### To Extract Medical Codes #######
    # df_facts.to_csv("facts.csv", index=False)
    # df_codes.to_csv("medical_codes.csv", index=False)


    ####### To Record Audio #######
    # journal = dictate_patient_journal( output_path="dictated_patient_journal.txt", duration_seconds=30, language="en")

    # print("\nDictated patient journal:")
    # print(journal) 


    ####### To Insert Data into Tables #######
    # generated_tables = insert_corti_data_into_tables(data_dir="Data", output_dir="GeneratedData", facts_path="facts.csv", codes_path="medical_codes.csv", encounter_key="E0001")


    df_timeline = generate_patient_timeline(data_dir="Data")

    print(df_timeline)



