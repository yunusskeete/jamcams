"""
This module defines functions and classes for processing JamCams data, making HTTP requests,
and interacting with a Kafka server for publishing camera data. It includes functions for checking
the online status of cameras, geofencing, making HTTP requests with retry mechanisms, and more.

Dependencies:
- requests
- shapely
- dateutil
- kafka-python

Environment Variables:
- PYTHONIOENCODING (optional): The encoding for string-related operations (default is 'utf-8').
- JAMCAMS_XML_FILE_PATH: Path to the local XML file with the API definition.

Classes:
- CameraDataProcessor: A class for processing camera data and managing counts of online and offline cameras.

Functions:
- camera_is_in_fence: Check if a given camera is within a specified geographic fence.
- make_request_with_retry: Make a generic HTTP request to a URL with a retry mechanism.
- pretty_format_xml: Format XML content to a pretty-printed, indented string.
- parse_xml_file: Create and parse an XML file from a requests.Response object.
- get_jamcams_data: Get JamCams data from the specified API URL with a retry mechanism.
- camera_is_online: Check if a given camera is online based on the 'available' status.
- headers_serializer: Serialize a list of header tuples into a list of tuples with UTF-8 encoded values.

Example:
    import os
    from kafka import KafkaProducer

    # Set up Kafka producer
    producer = KafkaProducer(
        bootstrap_servers='kafka-server:9092',
        client_id='example-client',
    )

    # Initialize CameraDataProcessor
    processor = CameraDataProcessor(num_online=0, num_offline=0)

    # Use the CameraDataProcessor to process camera data and publish to Kafka
    processor.publish_camera_data(
        camera={'id': 'JamCams_123', 'additionalProperties': [{'key': 'available', 'value': 'true'}]},
        cameras_data={'JamCams_123.mp4': '2022-02-12T12:00:00'},
        producer=producer,
        area_of_interest_polygon=None,
        use_geo_fence=False,
    )
"""

import json
import os
import time
import xml.dom.minidom
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional, Tuple, Union

import requests
import shapely
import yaml
from dateutil import parser
from kafka import KafkaProducer
from kafka.errors import KafkaError

# Read environment variables from app.yaml
app_yaml_path = os.environ.get("APP_YAML_PATH", "app.yaml")
STRING_ENCODING = os.environ.get("PYTHONIOENCODING", "utf-8")
TIMEOUT = int(os.environ.get("timeout_duration", "2"))

# Path to local XML file with API definition
JAMCAMS_XML_FILE_PATH = "jamcams.xml"


def load_environment_variables() -> None:
    """
    Load environment variables from an App YAML file.

    Reads an App YAML file specified by `app_yaml_path`, extracts the 'variables'
    section, and updates the current environment variables with the values provided
    in the 'name' and 'defaultValue' fields of the variables list.

    Parameters:
    - None: The function reads the App YAML file path from a predefined variable.

    Returns:
    - None: Updates the environment variables based on the contents of the App YAML file.

    Example:
    ```python
    load_environment_variables()
    ```

    Raises:
    - FileNotFoundError: If the specified App YAML file is not found.
    - yaml.YAMLError: If there is an error parsing the YAML file.
    - KeyError: If the 'variables' section is missing or not a list in the YAML file.
    - TypeError: If the 'variables' section contains invalid data types.
    """
    with open(app_yaml_path, "r", encoding=STRING_ENCODING) as file:
        config = yaml.safe_load(file)
        if "variables" in config and isinstance(config["variables"], list):
            # Convert the list of variables to a dictionary
            variables_dict = {
                variable["name"]: variable["defaultValue"]
                for variable in config["variables"]
            }
            os.environ.update(variables_dict)


def camera_is_in_fence(
    camera: Dict,
    area_of_interest_polygon: shapely.geometry.Polygon,
    use_geo_fence: bool,
) -> bool:
    """
    Check if the given camera is within the specified geographic fence.

    Parameters:
    - camera (dict): Dictionary containing information about the camera,
        including 'lon' and 'lat' coordinates.
    - area_of_interest_polygon (shapely.geometry.Polygon): Bounding box area defining cameras to be processed.
    - use_geo_fence (bool): Flag indicating whether geofencing is being used.

    Returns:
    - bool: True if the camera is inside the fence, False otherwise.
    """
    if not use_geo_fence:
        return False

    lon = float(camera["lon"])
    lat = float(camera["lat"])

    # check the ONLINE cameras position.
    camera_position = shapely.geometry.Point(lon, lat)
    return area_of_interest_polygon.contains(camera_position)


def make_request_with_retry(
    url: str, max_retries: int = 3, timeout: int = 10
) -> Optional[requests.Response]:
    """
    Make a generic HTTP request to the specified URL with a retry mechanism.

    Parameters:
    - url (str): The URL to make the request to.
    - max_retries (int): The maximum number of retries (default is 3).
    - timeout (int): The timeout for the request in seconds (default is 10).

    Returns:
    requests.Response or None: The response object if successful, None if max retries are reached.
    """
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)

            # Check if the request was successful (status code 200)
            if resp.status_code == 200:
                return resp  # Return the response if successful

            print(
                f"Attempt {attempt}: Call to the endpoint did not succeed (status code: {resp.status_code})."
            )

            # Check for a 429 status code (too many requests) and back off
            if resp.status_code == 429:
                back_off_period = attempt * 10
                print(
                    f"Attempt {attempt}: API rate limit exceeded, retrying after {back_off_period} seconds."
                )
                time.sleep(back_off_period)  # Wait before retrying
                continue  # Retry

        except requests.exceptions.Timeout as ex:
            print(
                f"Attempt {attempt}: A timeout error occurred while trying to call the endpoint."
            )
            print("Error:")
            print(ex)

        time.sleep(10)  # Wait for 10 seconds before retrying

    print("Max retries reached. Exiting the function.")
    return None


def pretty_format_xml(xml_content, spaces=4) -> bytes:
    """
    Format XML content to a pretty-printed, indented string.

    Parameters:
    - xml_content (str): The XML content to be formatted.
    - spaces (int): The number of spaces to use for indentation (default is 4).
    - STRING_ENCODING (str): The encoding to use when converting the formatted XML to bytes (default is 'utf-8').

    Returns:
    bytes: The formatted XML content as bytes.
    """
    dom = xml.dom.minidom.parseString(xml_content)
    return dom.toprettyxml(indent=" " * spaces).encode(STRING_ENCODING)


def parse_xml_file(
    resp: requests.Response, aws_xml_root_url: str
) -> Dict[str | Any | None, str | Any | None]:
    """
    Create and parse an XML file from a requests.Response object.

    Parameters:
    - resp (requests.Response): The response object containing XML content.
    - aws_xml_root_url (str): The root URL for AWS XML content.

    Returns:
    dict: A dictionary containing parsed information from the XML file.
    """
    with open(JAMCAMS_XML_FILE_PATH, "wb") as f:
        formatted_xml = pretty_format_xml(resp.content)
        f.write(formatted_xml)

    # Parse local XML file
    tree = ET.parse(JAMCAMS_XML_FILE_PATH)

    root = tree.getroot()

    files = {}
    for a in root.findall(f"{{{aws_xml_root_url}}}Contents"):
        files[a[0].text] = a[1].text

    return files


def get_jamcams_data(
    api_url: str, api_key: str, max_retries: int = 3
) -> Optional[Dict[str, Union[int, Dict]]]:
    """
    Get JamCams data from the specified API URL with a retry mechanism.

    Parameters:
    - api_url (str): The URL to make the request to.
    - api_key (str): The API key to include in the request.
    - max_retries (int): The maximum number of retries (default is 3).

    Returns:
    dict or None: A dictionary containing JamCams data if successful, None if max retries are reached.
    """
    for attempt in range(1, max_retries + 1):
        try:
            cameras = requests.get(f"{api_url}?&app_key={api_key}", timeout=10)

            print(f"Attempt {attempt}: Got {cameras.status_code} status code.")

            # if TfL returns a 429 (too many requests) then we need to back off a bit
            if cameras.status_code == 429:
                print("Received 429 status code. Retrying after 10 seconds.")
                time.sleep(10)  # wait 10 seconds
                continue  # Retry

        except requests.exceptions.Timeout as ex:
            print(
                "Attempt {attempt}: A timeout error occurred while trying to call the JamCam endpoint."
            )
            print("The JamCam endpoint may be down.")
            print("Error:")
            print(ex)
            print("Retrying after 10 seconds.")
            time.sleep(10)  # wait 10 seconds
            continue  # Retry

        finally:
            print(f"Attempt {attempt}: JamCam 'get' status: {cameras.status_code}")

        if cameras.status_code == 200:
            return cameras.json()  # Return JamCams data if successful

    print("Max retries reached. Exiting the function.")
    return None


def camera_is_online(camera: Dict) -> bool:
    """
    Check if the given camera is online based on the 'available' status.

    Parameters:
    - camera (dict): Dictionary containing information about the camera.

    Returns:
    - bool: True if the camera is online, False otherwise.
    """
    enabled = next(
        (
            account
            for account in camera["additionalProperties"]
            if account["key"] == "available" and account["value"] == "true"
        ),
        None,
    )
    return enabled is not None


def headers_serializer(headers):
    """
    Serialize a list of header tuples into a list of tuples with UTF-8 encoded values.

    Parameters:
    - headers (list): A list of tuples representing headers.

    Returns:
    list: A new list of tuples with headers, where values are UTF-8 encoded.
    """
    return [(key, str(value).encode(STRING_ENCODING)) for key, value in headers]


class CameraDataProcessor:
    """
    A class for processing camera data and managing counts of online and offline cameras.

    Attributes:
    - num_online (int): Count of online cameras.
    - num_offline (int): Count of offline cameras.

    Methods:
    - __init__(self, num_online: int, num_offline: int) -> None:
        Initialize a CameraDataProcessor instance.

    - get_counts(self) -> Tuple[int, int]:
        Get the current counts of online and offline cameras.

    - reset(self) -> Tuple[int, int]:
        Reset the counts of online and offline cameras to zero.

    - publish_camera_data(
        self,
        camera: Dict[str, Any],
        cameras_data: Dict[str, str],
        producer: KafkaProducer,
        area_of_interest_polygon: Optional[shapely.geometry.Polygon],
        use_geo_fence: bool,
    ) -> None:
        Process camera data and publish to Kafka if conditions are met.
    """

    def __init__(self, num_online: int, num_offline: int) -> None:
        """
        Initialize a CameraDataProcessor instance.

        Parameters:
        - num_online (int): Initial count of online cameras.
        - num_offline (int): Initial count of offline cameras.
        """
        self.num_online = num_online
        self.num_offline = num_offline

    def get_counts(self) -> Tuple[int, int]:
        """
        Get the current counts of online and offline cameras.

        Returns:
        Tuple[int, int]: A tuple containing the counts of online and offline cameras.
        """
        return self.num_online, self.num_offline

    def reset(self) -> Tuple[int, int]:
        """
        Reset the counts of online and offline cameras to zero.

        Returns:
        Tuple[int, int]: A tuple containing the counts of online and offline cameras after the reset.
        """
        self.num_online, self.num_offline = 0, 0

        return self.num_online, self.num_offline

    def publish_camera_data(
        self,
        camera: Dict[str, Any],
        cameras_data: Dict[str | Any | None, str | Any | None],
        producer: KafkaProducer,
        area_of_interest_polygon: Optional[shapely.geometry.Polygon],
        use_geo_fence: bool,
    ) -> None:
        """
        Process camera data and publish to Kafka if conditions are met.

        Parameters:
        - camera (Dict[str, Any]): Camera data dictionary.
        - cameras_data (Dict[str | Any | None, str | Any | None]): Dictionary containing timestamp data for cameras.
        - producer (KafkaProducer): Kafka producer instance.
        - area_of_interest_polygon (shapely.geometry.Polygon): Bounding box area defining cameras to be processed.
        - use_geo_fence (bool): Flag indicating whether geofencing is being used.

        Returns:
        None
        """
        camera_id = camera["id"]

        if not camera_is_online(camera):
            self.num_offline += 1
            print(f"Camera {camera_id} is offline")

        else:
            self.num_online += 1

            try:
                timestamp_str = cameras_data[camera_id.replace("JamCams_", "") + ".mp4"]

            except KeyError:
                print(f"No data for {camera_id}")

                return

            timestamp = parser.parse(timestamp_str)

            if use_geo_fence and not camera_is_in_fence(
                camera, area_of_interest_polygon, use_geo_fence
            ):
                # The camera is outside the fence, don't publish it to the producer topic.
                use_camera = False
            else:
                message = "inside the geofence" if use_geo_fence else "online"
                print(f"\nCamera {camera_id} is {message}")

                use_camera = True

            if use_camera:
                headers = [
                    (
                        "timestamp",
                        str(int(timestamp.timestamp()) * 1000),
                    ),  # Convert to milliseconds
                    ("camera_id", camera_id),
                ]

                try:
                    producer.send(
                        os.environ["output"],
                        value=json.dumps(camera),
                        headers=headers_serializer(headers),
                    ).get(timeout=TIMEOUT)

                    print(f"sent: {camera_id}\n")

                except KafkaError as ex:
                    print(f"Error publishing data to Kafka: {ex}")
                    print(f"Message metadata: {headers}")
