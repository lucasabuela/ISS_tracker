import logging
from datetime import datetime, timezone
import json
import requests
import numpy as np
import redis
from iss_tracker import (
    retrieve_data,
    data_time_range,
    get_datetime_from_index,
    dich_index_finder,
    epoch_speed,
    closest_epoch,
)

state_vectors1 = [
    {
        "EPOCH": "2025-001T00:00:00.001Z",
        "X_DOT": {"@units": "km/s", "#text": "-2.3085318325285802"},
        "Y_DOT": {"@units": "km/s", "#text": "4.5299650289252096"},
        "Z_DOT": {"@units": "km/s", "#text": "5.73411165850138"},
    }
]
state_vectors2 = [
    {
        "EPOCH": "2025-001T00:00:00.001Z",
        "X_DOT": {"@units": "km/s", "#text": "-2.3085318325285802"},
        "Y_DOT": {"@units": "km/s", "#text": "4.5299650289252096"},
        "Z_DOT": {"@units": "km/s", "#text": "5.73411165850138"},
    },
    {
        "EPOCH": "2025-002T00:00:00.001Z",
        "X_DOT": {"@units": "km/s", "#text": "-5"},
        "Y_DOT": {"@units": "km/s", "#text": "4"},
        "Z_DOT": {"@units": "km/s", "#text": "5"},
    },
]
state_vectors3 = [
    {"EPOCH": "2025-001T00:00:00.000Z"},
    {"EPOCH": "2025-002T00:00:00.000Z"},
    {"EPOCH": "2025-003T00:00:00.000Z"},
]
state_vectors4 = [
    {"EPOCH": "2025-001T00:00:00.000Z"},
    {"EPOCH": "2025-002T00:00:00.000Z"},
    {"EPOCH": "2025-003T00:00:00.000Z"},
    {"EPOCH": "2025-004T00:00:00.000Z"},
]
state_vectors5 = [
    {"EPOCH": "2024-001T00:00:00.000Z"},
    {"EPOCH": "2025-001T00:00:00.000Z"},
]
state_vectors6 = [
    {"EPOCH": "2024-001T00:00:00.000Z"},
    {"EPOCH": "2025-001T00:00:00.000Z"},
    {"EPOCH": "9999-001T00:00:00.000Z"},
]


def test_retrieve_data():
    rd = redis.Redis(host="redis-db", port=6379, db=0)
    assert isinstance(json.loads(rd.get("data_set")), dict)


def test_data_time_range():
    response = requests.get(url="http://flask-app:5000/data_time_range")
    assert response.status_code == 200
    assert isinstance(response.text, str)


def test_epochs():
    response1 = requests.get(url="http://flask-app:5000/epochs")
    assert response1.status_code == 200
    assert isinstance(response1.json(), list)
    # Let's verify the structure of the epoch.
    try:
        _ = response1.json()[0]["EPOCH"]
        _ = response1.json()[0]["X"]
        _ = response1.json()[0]["X_DOT"]
        _ = response1.json()[0]["Y"]
        _ = response1.json()[0]["Y_DOT"]
        _ = response1.json()[0]["Z"]
        _ = response1.json()[0]["Z_DOT"]
    except (KeyError, TypeError):
        assert (
            False
        ), "Some of the expected dictionary paths are missing or not correctly structured."

    # Now let's test the query parameters functionality.
    response2 = requests.get(url="http://flask-app:5000/epochs?limit=1&offset=1")
    assert response2.status_code == 200
    assert isinstance(response2.json(), list)
    assert len(response2.json()) == 2

    _INF = 10**10
    response3 = requests.get(url=f"http://flask-app:5000/epochs?limit={_INF}")
    assert response3.status_code == 200
    assert isinstance(response3.json(), list)


def test_epoch_f():
    # Test when the time is not in the correct format
    response1 = requests.get(url="http://flask-app:5000/epochs/a_bad_time_format")
    assert response1.status_code == 500
    assert response1.text == "The time provided is not in the correct format."
    # Test when the time is not in the dataset
    response2 = requests.get(url="http://flask-app:5000/epochs/2000-001T00:00:00.001Z")
    assert (
        response2.text
        == "There is no epoch in the dataset whose time perfectly matches the submitted time."
    )
    # Test supposed to work. We have to know a time at which an epoch exists in the datadet. For this, we use the epochs function.
    an_epoch_present_in_the_dataset = requests.get(
        url="http://flask-app:5000/epochs?limit=1"
    ).json()[0]
    current_time = an_epoch_present_in_the_dataset["EPOCH"]
    response3 = requests.get(url=f"http://flask-app:5000/epochs/{current_time}")
    assert response3.json() == an_epoch_present_in_the_dataset


def test_epoch_speed():
    # Test when the time is not in the correct format
    response1 = requests.get(url="http://flask-app:5000/epochs/a_bad_time_format/speed")
    assert response1.status_code == 500
    assert response1.text == "The time provided is not in the correct format."
    # Test when the time is not in the dataset
    response2 = requests.get(
        url="http://flask-app:5000/epochs/2000-001T00:00:00.001Z/speed"
    )
    assert (
        response2.text
        == "There is no epoch in the dataset whose time perfectly matches the submitted time."
    )
    # Test supposed to work. We have to know a time at which an epoch exists in the datadet. For this, we use the epochs function.
    an_epoch_present_in_the_dataset = requests.get(
        url="http://flask-app:5000/epochs?limit=1"
    ).json()[0]
    # We calculate the correct speed at this epoch.
    x_dot, y_dot, z_dot = (
        float(an_epoch_present_in_the_dataset["X_DOT"]["#text"]),
        float(an_epoch_present_in_the_dataset["Y_DOT"]["#text"]),
        float(an_epoch_present_in_the_dataset["Z_DOT"]["#text"]),
    )
    correct_speed = np.sqrt(x_dot**2 + y_dot**2 + z_dot**2)
    current_time = an_epoch_present_in_the_dataset["EPOCH"]
    response3 = requests.get(url=f"http://flask-app:5000/epochs/{current_time}/speed")
    assert response3.json()["speed"] == correct_speed


def test_now():
    response = requests.get(url="http://flask-app:5000/now")
    assert response.status_code == 200
    assert isinstance(response.json(), dict)

    # We test that the epoch found is in the dataset
    found_closest_epoch = response.json()["closest_epoch"]
    response2 = requests.get(url=f"http://flask-app:5000/epochs/{found_closest_epoch}")
    assert response2.status_code == 200


def test_get_datetime_from_index():
    index = 0
    datetime1 = datetime(
        year=2025, month=1, day=1, microsecond=1000, tzinfo=timezone.utc
    )
    assert (
        get_datetime_from_index(state_vectors=state_vectors1, index=index) == datetime1
    )


def test_dich_index_finder():

    # Let's construct a test current time. The easiest way to do it here is to use get_datetime_from_index, thus we define a state_vectors for this purpose.
    state_vectors_utility = [{"EPOCH": "2025-002T01:00:00.000Z"}]
    searched_time = get_datetime_from_index(state_vectors_utility, 0)

    assert (
        dich_index_finder(state_vectors=state_vectors1, searched_time=searched_time)
        == 0
    )
    assert dich_index_finder(state_vectors2, searched_time) == 1
    assert dich_index_finder(state_vectors3, searched_time) == 1
    assert dich_index_finder(state_vectors4, searched_time) == 1


def test_closest_epoch(capsys):
    closest_epoch(state_vectors1)
    captured = capsys.readouterr()
    assert captured.out == f"The closest epoch in the dataset is {state_vectors1[0]}\n"
    closest_epoch(state_vectors5)
    captured = capsys.readouterr()
    assert captured.out == f"The closest epoch in the dataset is {state_vectors5[1]}\n"
    closest_epoch(state_vectors6)
    captured = capsys.readouterr()
    assert captured.out == f"The closest epoch in the dataset is {state_vectors6[1]}\n"


def main():
    """
    This function is used to make tests AND having access to the logging messages (which is not the cas when using pytest).
    """
    logging.basicConfig(level="DEBUG")
    closest_epoch(state_vectors1)


if __name__ == "__main__":
    main()
