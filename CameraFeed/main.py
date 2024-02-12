"""
JamCams Data Retrieval Script

This script retrieves data about online JamCams, processes it, and publishes relevant information
to the Kafka stream topic. It utilizes threading to run the data retrieval function in a separate
thread and handles termination signals gracefully.

Configuration:
    The script reads configuration variables from an 'app.yaml' file and environment variables.

Dependencies:
    - json
    - os
    - time
    - xml.dom.minidom
    - xml.etree.ElementTree (as ET)
    - typing
    - requests
    - shapely
    - dateutil.parser
    - kafka-python
    - yaml

Usage:
    Run this script to start the JamCams data retrieval process.
    The script creates a separate thread for data retrieval and handles termination signals
    for graceful shutdown.

Author:
    Yunus Skeete

Date:
    11/02/2024
"""

import ast
import os
import threading
import time
import traceback
from threading import Thread

import yaml
from kafka import KafkaProducer
from shapely.geometry import Polygon
from utils.utils import (
    STRING_ENCODING,
    CameraDataProcessor,
    make_request_with_retry,
    parse_xml_file,
)

# Read environment variables from app.yaml
app_yaml_path = os.environ.get("APP_YAML_PATH", "app.yaml")

with open(app_yaml_path, "r", encoding=STRING_ENCODING) as file:
    config = yaml.safe_load(file)
    if "variables" in config and isinstance(config["variables"], list):
        # Convert the list of variables to a dictionary
        variables_dict = {
            variable["name"]: variable["defaultValue"]
            for variable in config["variables"]
        }
        os.environ.update(variables_dict)

coords = os.environ["fence_coordinates"]
jamcams_api_definition_url = os.environ["jamcams_api_definition"]
aws_xml_root_url = os.environ["aws_xml_root"]
jamcams_api_url = os.environ["jamcams_api"]
api_key = os.environ["tfl_api_key"]
kafka_host = os.environ["kafka_host"]
kafka_port = os.environ["kafka_port"]


# Setup camera coordinates and fence area
if coords == "":
    USE_GEO_FENCE = False
    area_of_interest_polygon = None
else:
    USE_GEO_FENCE = True
    area_of_interest = ast.literal_eval(coords)
    print(f"Area of interest = {area_of_interest}")
    area_of_interest_polygon = Polygon(area_of_interest)


# Define the Kafka producer
producer = KafkaProducer(
    bootstrap_servers=f"{kafka_host}:{kafka_port}",
    client_id="kafka-python-producer-jamcams-camera-feed",
    value_serializer=lambda v: str(v).encode(STRING_ENCODING),
)


def get_data() -> None:
    """
    Main function to retrieve data about online JamCams, process it,
    and publish relevant information to the Kafka stream topic.

    Returns:
        None
    """
    processor = CameraDataProcessor(0, 0)

    while not stop_event.is_set():
        start = time.time()
        print("Loading new data.")

        # Make a request for JamCams API definition
        print("Calling AWS API for JamCam API definition")
        resp = make_request_with_retry(jamcams_api_definition_url)
        if resp is None:
            continue

        # Parse JamCams API definition and extract data for cameras
        cameras_data = parse_xml_file(resp, aws_xml_root_url)

        print("Calling JamCam API for camera data")
        cameras = make_request_with_retry(f"{jamcams_api_url}?&app_key={api_key}")
        if cameras is None:
            continue
        cameras_list = cameras.json()

        num_online, num_offline = processor.reset()
        for camera in cameras_list:
            processor.publish_camera_data(
                camera,
                cameras_data,
                producer,
                area_of_interest_polygon,
                USE_GEO_FENCE,
            )

        num_online, num_offline = processor.get_counts()
        print(f"{num_online} online cameras")
        print(f"{num_offline} offline cameras")

        producer.flush()

        sleep_time = int(os.environ["sleep_interval"]) - (time.time() - start)

        if sleep_time > 0:
            print("Sleep for " + str(sleep_time))
            time.sleep(sleep_time)


# Create an event to signal the main thread to stop
stop_event = threading.Event()


def main() -> None:
    """
    Creates a thread to run the main data retrieval function and handles termination signals.
    """
    try:
        thread = Thread(target=get_data, args=(stop_event,))
        thread.start()

        # Wait for the worker thread to finish
        thread.join()

        print("Exiting")

    except (KeyboardInterrupt, SystemExit):
        # Handle keyboard interrupt (Ctrl+C) or system exit
        print("Received interrupt signal. Stopping gracefully.")
        stop_event.set()

    except Exception as ex:
        # Log exception traceback for debugging purposes
        traceback.print_exc()

        print("An unexpected error occured:")
        print(ex)
        print("\nProcess terminating.")


if __name__ == "__main__":
    main()
