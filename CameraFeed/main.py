import ast
import json
import os
import signal
import time
import traceback
import xml.etree.ElementTree as ET
from threading import Thread
from typing import Dict

import requests
from dateutil import parser
from kafka import KafkaProducer
from kafka.errors import KafkaError
from shapely.geometry import Point, Polygon
from utils.utils import *

string_encoding = os.environ["string_encoding"]
coords = os.environ["fence_coordinates"]
jamcams_api_definition_url = os.environ["jamcams_api_definition"]
aws_xml_root_url = os.environ["aws_xml_root"]
jamcams_api_url = os.environ["jamcams_api"]
api_key = os.environ["tfl_api_key"]


# Should the main loop run?
RUN = True

# Setup camera coordinates and fence area
if coords == "":
    USE_GEO_FENCE = False
else:
    USE_GEO_FENCE = True
    area_of_interest = ast.literal_eval(coords)
    print(f"Area of interest = {area_of_interest}")
    area_of_interest_polygon = Polygon(area_of_interest)

# Path to local XML file with API definition
JAMCAMS_XML_FILE_PATH = "jamcams.xml"


# Define the Kafka producer
producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    client_id="kafka-python-producer-1",
    value_serializer=lambda v: str(v).encode(string_encoding),
)


def get_data() -> None:
    """
    Main function to retrieve data about online JamCams, process it,
    and publish relevant information to the Kafka stream topic.
    The function runs in a loop until the global RUN variable is set to False.
    """
    while RUN:
        start = time.time()
        print("Loading new data.")

        # Make a request for JamCams API definition
        print("Calling AWS API for JamCam API definition")
        resp = make_request_with_retry(jamcams_api_definition_url)
        if resp is None:
            continue

        # Parse JamCams API definition and extract data for cameras
        cameras_data = parse_xml_file(resp, JAMCAMS_XML_FILE_PATH, aws_xml_root_url)

        print("Calling JamCam API for camera data")
        cameras = make_request_with_retry(f"{jamcams_api_url}?&app_key={api_key}")
        cameras_list = cameras.json()

        for camera in cameras_list:
            publish_camera_data(
                camera, cameras_data, producer, area_of_interest_polygon, USE_GEO_FENCE
            )

        sleep_time = int(os.environ["sleep_interval"]) - (time.time() - start)

        if sleep_time > 0:
            print("Sleep for " + str(sleep_time))
            time.sleep(sleep_time)


def before_shutdown() -> None:
    """
    Function to be executed before shutting down the application.
    Stops the main data retrieval loop by setting the global RUN variable to False.
    """
    global RUN

    print("Received shutdown signal. Stopping the application.")

    # Stop the main loop
    RUN = False


def main() -> None:
    """
    Creates a thread to run the main data retrieval function and handles termination signals.
    """
    try:
        # Register the before_shutdown function to be called on SIGINT or SIGTERM
        signal.signal(signal.SIGINT, before_shutdown)  # Signal interrupt
        signal.signal(signal.SIGTERM, before_shutdown)  # Signal terminate

        thread = Thread(target=get_data)
        thread.start()

        # wait for worker thread to end
        thread.join()

        before_shutdown()
        print("Exiting")

    except Exception as ex:
        # Log exception traceback for debugging purposes
        traceback.print_exc()

        print("An unexpected error occured:")
        print(ex)
        print("\nProcess terminating.")


if __name__ == "__main__":
    main()
