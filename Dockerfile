FROM python:3.12

RUN mkdir /app
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY iss_tracker.py .
COPY test_iss_tracker.py .

RUN chmod +rx iss_tracker.py
RUN chmod +rx test_iss_tracker.py


ENTRYPOINT ["python"]
CMD ["iss_tracker.py"]
