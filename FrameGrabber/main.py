"""
This module defines an asynchronous Kafka consumer for processing camera feed messages and publishing frames to Kafka.

It includes functions for processing images from a camera feed, handling Kafka messages, and defining the main execution flow.

Author: [Your Name]

Usage:
- Ensure that the required environment variables are set by calling 'load_environment_variables()'.
- Run the main function 'main()' to start processing messages from the specified Kafka topic.

Example:
```python
# Set up environment variables
load_environment_variables()

# Run the main function to start processing Kafka messages
asyncio.run(main())
"""

import json
import os
import threading
import traceback
from datetime import datetime
from threading import Thread
from typing import Dict, Union

import cv2
import redis
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from utils.utils import headers_serializer, load_environment_variables

load_environment_variables()

STRING_ENCODING = os.environ.get("PYTHONIOENCODING", "utf-8")
TIMEOUT = int(os.environ.get("timeout_duration", "2"))


redis_client = redis.StrictRedis(
    host=os.environ["redis_host"], port=os.environ["redis_port"], db=0
)


def process_image_from_message(
    camera: Dict[str, Union[str, float]], timestamp: int, producer: KafkaProducer
) -> None:
    """
    Process images from a camera feed and publish frames to Kafka.

    Parameters:
    - camera (Dict[str, Union[str, float]]): Camera information containing 'id', 'lon', 'lat', and 'additionalProperties' (containing 'videoUrl'),
      including 'id', 'lon', 'lat', 'additionalProperties' (containing 'videoUrl').
    - timestamp (int): UNIX timestamp of Kafka message containing camera information.
    - producer (KafkaProducer): Kafka producer instance.

    Returns:
    - None

    The function reads video frames from the specified 'videoUrl', encodes them as JPEG images,
    and publishes the frames along with metadata to a Kafka topic. It also checks and updates
    the last processed timestamp for the camera in a Redis database to avoid duplicate processing.

    Raises:
    - KafkaError: If there is an error while publishing data to Kafka.
    ```
    """
    camera_id = camera["id"]
    lon = float(camera["lon"])
    lat = float(camera["lat"])

    camera_video_feed = list(
        filter(lambda x: x["key"] == "videoUrl", camera["additionalProperties"])
    )[0]

    last_image_state = redis_client.get(camera_id) or 0
    last_image_state = int(last_image_state)

    if timestamp <= last_image_state:
        print(
            f"{camera_id} image from {datetime.utcfromtimestamp(timestamp/1000)} has been processed. Skipping..."
        )
        return

    redis_client.set(camera_id, timestamp)
    print(
        f"Processing {camera_id} image from {datetime.utcfromtimestamp(timestamp/1000)}"
    )

    video_stream = cv2.VideoCapture(camera_video_feed["value"])
    total_frames = int(video_stream.get(cv2.CAP_PROP_FRAME_COUNT))
    num_frames_being_sent = 1 + total_frames // int(os.environ.get("frame_rate", 10))

    redis_client.set(f"num_{camera_id}_frames", num_frames_being_sent)

    frame_count = 0

    success, image = video_stream.read()
    while success:
        frame = cv2.imencode(".jpg", image)
        if len(frame) <= 1:
            print("no data")
            continue

        frame_bytes = frame[1]

        success, image = video_stream.read()
        frame_count += 1

        if (frame_count - 1) % int(os.environ.get("frame_rate", 10)) == 0:
            headers = [
                ("timestamp", timestamp),
                ("camera_id", camera_id),
                ("lon", lon),
                ("lat", lat),
                ("frame_count", frame_count - 1),
            ]

            try:
                producer.send(
                    os.environ["output"],
                    value=frame_bytes.tobytes(),
                    headers=headers_serializer(headers),
                ).get(timeout=TIMEOUT)

            except KafkaError as ex:
                print(f"Error publishing data to Kafka: {ex}")
                print(f"Message metadata: {headers}")


def process_messages(stop_event: threading.Event) -> None:
    """
    This function sets up a Kafka producer and consumer, continuously polls for messages from the Kafka topic,
    and processes each message by extracting video frames and sending them to the Kafka producer.

    Args:
    - stop_event (threading.Event): An event to signal the termination of the processing thread.

    Returns:
    - None
    """
    # Define the Kafka producer
    producer = KafkaProducer(
        bootstrap_servers=f"{os.environ['kafka_host']}:{os.environ['kafka_port']}",
        client_id="kafka-python-producer-jamcams-frame-grabber",
    )

    # Define the Kafka consumer
    consumer = KafkaConsumer(
        os.environ["input"],
        bootstrap_servers=f"{os.environ['kafka_host']}:{os.environ['kafka_port']}",
        value_deserializer=lambda v: v.decode(STRING_ENCODING),
        enable_auto_commit=False,
        group_id="kafka-python-consumer-jamcams-camera-feed",
    )

    try:
        while not stop_event.is_set():
            for message in consumer:
                camera = json.loads(message.value)
                timestamp = message.timestamp
                process_image_from_message(camera, timestamp, producer)

            consumer.commit()

    finally:
        consumer.close()
        producer.close()


# Create an event to signal the main thread to stop
stop_event = threading.Event()


def main() -> None:
    """
    Creates a thread to start processing messages and handle termination signals.
    """
    try:
        thread = Thread(target=process_messages, args=(stop_event,))
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
