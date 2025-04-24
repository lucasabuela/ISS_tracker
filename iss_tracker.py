import math
import logging

# library for not printing entire objects when they are too long
import reprlib
from datetime import datetime, timezone

import requests
import xmltodict
import numpy as np
import json
import redis
from flask import Flask, request


# We create an instance of the Flask class :
app = Flask(__name__)
# We modify the logging level of the flask app. It is useful during development but not in production.
logging.getLogger("werkzeug").setLevel(logging.ERROR)


# We add a global error handler. This ensures the error message only contains the custom error messages I wrote, and not werkzeug html debugger.
@app.errorhandler(Exception)
def handle_exception(e):
    return str(e), 500


def load_data():
    """
    This function is used on startup. It checks if there is data in the Redis database.
    If there is data, then no action is taken. If there is no data, then it will retrieve
    the data from the ISS website and load it into the Redis database.
    """
    rd = redis.Redis(host="redis-db", port=6379, db=0)
    # We test if there is data in the redis database.
    if isinstance(rd.get("data_set"), type(None)):

        response = requests.get(
            url="https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml"
        )

        if response.status_code == 200:
            logging.info("Data successfully retrieved from NASA's website")
        else:
            logging.info("Data not retrieved from NASA's website")

        xml_data = response.text
        app.data_set = xmltodict.parse(xml_data)  # Convert xml to a dictionary
        logging.debug(f" Data-set = {reprlib.repr(app.data_set)}")

        app.epochs = app.data_set["ndm"]["oem"]["body"]["segment"]["data"][
            "stateVector"
        ]
        logging.debug(f" state_vectors = {reprlib.repr(app.epochs)}")

        # We load the data into the Redis database
        rd.set("data_set", json.dumps(app.data_set))


def retrieve_data():
    """
    This function queries the Redis database, retrieve the data, and add to the Flask app context both the full data and only the state vectors.
    """
    rd = redis.Redis(host="redis-db", port=6379, db=0)
    app.data_set = json.loads(rd.get(("data_set")))
    app.epochs = app.data_set["ndm"]["oem"]["body"]["segment"]["data"]["stateVector"]
    logging.info("Successful connection with the Redis database")


@app.route("/epochs", methods=["GET"])
def epochs() -> dict:
    """
    A flask route endpoint. Returns a sub-list of the list of epochs of the dataset, ordered chronologically. The list starts at the offest-th epoch of the dataset, and contains limit epochs.  If no arguments are provided, it returns the entire data set.

    Args:
        limit (int): (maximum) number of epochs desired
        offset (int): Rank of the first epoch returned, in the whole dataset. Starts at 0.

    Returns:
        epochs (list): a sub-list of the list of epochs in the dataset

    """
    retrieve_data()

    limit = request.args.get("limit", default=len(app.epochs))
    offset = request.args.get("offset", default=0)

    try:
        limit = int(limit)
    except ValueError:
        return "Invalid limit parameter; limit must be an integer."
    try:
        offset = int(offset)
    except ValueError:
        return "Invalid offset parameter; offset must be an integer."

    # We handle the case where two many epochs are requested.
    if offset + limit > len(app.epochs):
        limit = len(app.epochs) - offset

    return app.epochs[offset : offset + limit + 1]


@app.route("/epochs/<string:epoch>", methods=["GET"])
def epoch_f(epoch: str) -> dict:
    """
    A flask route endpoint. Return the state vectors of a given epoch, identified by its time. Beware, if the time provided is not in the correct format or there isn't an epoch in the dataset whose time matches perfectly the submitted time, an error will be raised. In particular, the epoch nearest in time won't be returned.

    Args:
        epoch (str): The time of the searched epoch. In the format '%Y-%jT%H:%M:%S.%fZ'. For example: '2025-104T12:20:00.000Z'.

    Returns:
        state_vectors (dict): the desired epoch
    """
    retrieve_data()

    # We first test that the time provided is in the correct format.
    logging.debug(f"epoch={epoch}")
    try:
        _epoch = epoch.replace("Z", "")
        _epoch = datetime.strptime(_epoch, "%Y-%jT%H:%M:%S.%f")
    except (AttributeError, ValueError):
        raise Exception("The time provided is not in the correct format.")
    logging.debug("epoch in correct format")
    # We test that there is an epoch in the dataset whose time perfectly matches the submitted time.
    l = [_epoch for _epoch in app.epochs if _epoch["EPOCH"] == epoch]
    if len(l) == 0:
        raise Exception(
            "There is no epoch in the dataset whose time perfectly matches the submitted time."
        )
    else:
        return l[0]


@app.route("/epochs/<string:epoch>/speed", methods=["GET"])
def epoch_speed(epoch: str) -> dict:
    """
    A flask route endpoint. Returns the speed in km/s of the ISS at the time provided, if and only if the time provided is in the correct format and there is an epoch in the dataset whose time matches perfectly the submitted time. If the time provided is not in the correct format or there isn't an epoch in the dataset whose time matches perfectly the submitted time, an error will be raised. In particular, the epoch nearest in time won't be returned.

    Args:
        epoch (str): The time of the searched epoch. In the format '%Y-%jT%H:%M:%S.%fZ'. For example: '2025-104T12:20:00.000Z'.

    Returns:
        speed (float): the speed if the ISS at the time provided, in km/s.
    """
    retrieve_data()

    logging.debug(f"epoch={type(epoch)}")
    _epoch = epoch_f(epoch)
    logging.debug(f"_epoch={_epoch}")
    x_dot, y_dot, z_dot = (
        float(_epoch["X_DOT"]["#text"]),
        float(_epoch["Y_DOT"]["#text"]),
        float(_epoch["Z_DOT"]["#text"]),
    )
    epoch_speed = np.sqrt(x_dot ** (2) + y_dot**2 + z_dot**2)
    return {"speed": epoch_speed, "unit": "km/s"}


@app.route("/now", methods=["GET"])
def now() -> dict:
    """
    A flask route endpoint. Looks for the the closest epoch in the dataset to the time at which the program is executed. Returns this time and the speed of the iss at that time.

    Returns:
        closest_epoch (str) : the closest epoch in the dataset to the time at which the program is executed. In the format '%Y-%jT%H:%M:%S.%fZ'. For example: '2025-104T12:20:00.000Z'.
        closest_speed (float): the speed if the ISS at this time, in km/s.
    """
    retrieve_data()

    _closest_epoch = closest_epoch(app.epochs)
    _closest_speed = epoch_speed(_closest_epoch["EPOCH"])["speed"]
    return {"closest_epoch": _closest_epoch["EPOCH"], "closest_speed": _closest_speed}


@app.route("/data_time_range", methods=["GET"])
def data_time_range():
    """
    This function prints a statement about the range of data in the downloaded dataset.
    """
    retrieve_data()

    start_timestamp = app.data_set["ndm"]["oem"]["body"]["segment"]["metadata"][
        "START_TIME"
    ]
    stop_timestamp = app.data_set["ndm"]["oem"]["body"]["segment"]["metadata"][
        "STOP_TIME"
    ]
    logging.debug(f" start_timestamp = {reprlib.repr(start_timestamp)}")
    logging.debug(f" stop_timestamp = {reprlib.repr(stop_timestamp)}")
    # The timestamps are strings.

    start_year = start_timestamp[:4]
    stop_year = stop_timestamp[:4]
    start_day = start_timestamp[5:8]
    stop_day = stop_timestamp[5:8]
    start_time = start_timestamp[9:19]
    stop_time = stop_timestamp[9:19]
    return f"The data ranges from the {start_day}th day of {start_year} at {start_time} to the {stop_day}th day of {stop_year} at {stop_time}"


def closest_epoch(state_vectors: list) -> dict:
    """
    This function returns and prints the full epoch (time stamp, state vectors, and velocities) closest to the time when the program is executed.

    Args:
        state_vectors (list): the list of iss state vectors (epoch, position and velocity)

    Returns:
        closest_epoch (dict) : the full epoch closest to the time when the program is executed
    """
    current_time = datetime.now(timezone.utc)
    logging.debug(f" current_time = {current_time}")

    # The state_vectors list is sorted by ascending epoch, thus one can use dichomotic search.
    closest_epoch_index = dich_index_finder(
        state_vectors=state_vectors, searched_time=current_time
    )
    closest_epoch = state_vectors[closest_epoch_index]
    print(f"The closest epoch in the dataset is {closest_epoch}")
    return closest_epoch


def dich_index_finder(state_vectors: list, searched_time: datetime) -> int:
    """
    This function returns the index of the epoch in the list of epochs whose timestamp is closest to searched_time.

    Args:
        state_vectors (list): a list of of full epochs
        searched_time (datetime.datetime): the searched time, in the format : YYYY-MM-DD HH:MM:SS.microseconds(6 characters)

    Returns:
        closest_index (int): the index of the epoch in state_vectors whose timestamp is closest to searched_time
    """

    left_index = 0
    right_index = len(state_vectors) - 1
    current_index = 0

    while right_index - left_index >= 2:

        current_index = left_index + math.floor((right_index - left_index) / 2)
        current_value = get_datetime_from_index(
            state_vectors=state_vectors, index=current_index
        )

        if current_value < searched_time:
            left_index = current_index
            right_index = right_index
        if current_value == searched_time:
            return current_index
        if current_value > searched_time:
            left_index = left_index
            right_index = current_index

    # at this point, right_index = left_index + 1. We now calculate the distance (time) between the searched time, the left time and the right time.
    distance_left = get_datetime_from_index(state_vectors, left_index) - searched_time
    # distance_left is a timedelta object. We have to convert it to a number.
    distance_left = np.abs(distance_left.total_seconds())
    logging.debug(f" distance_left = {distance_left}")

    distance_right = get_datetime_from_index(state_vectors, right_index) - searched_time
    distance_right = np.abs(distance_right.total_seconds())
    logging.debug(f" distance_right = {distance_right}")

    if distance_left < distance_right:
        return left_index
    else:
        return right_index


def get_datetime_from_index(state_vectors: list, index: int) -> datetime:
    """
    This function is a small utility to declutter dich_index_finder. From the index of a full epoch in the provided list of epochs, it returns the timestamp of this epoch. Most importantly, it modifies its format to one that allows for comparison.

    Args:
        state_vectors (list): the list of full epochs
        index (int): the index of the epoch of interest

    Returns:
        datetime1 (datetime.datetime): the datetime of the epoch of interest
    """
    datetime1_str = state_vectors[index]["EPOCH"]
    # Currently, datetime1 is a string.
    datetime1_str = datetime1_str.replace("Z", "")
    datetime1 = datetime.strptime(datetime1_str, "%Y-%jT%H:%M:%S.%f")
    # Currently, datetime1 doesn't include the timezone (which is necessary for comparison). It was the "Z" (which indicated zero offset from the Universal Coordinated Time) but we had to delete it to turn datetime1 into a datetime.datetime object.
    datetime1 = datetime1.replace(tzinfo=timezone.utc)
    return datetime1


def main():
    # We define an instance of logging
    logging.basicConfig(level="INFO")

    load_data()

    # We run the Flask instance.
    app.run(debug=False, host="0.0.0.0", port=5000)


if __name__ == "__main__":
    main()
