FROM python:3.7-slim

WORKDIR /app

COPY *.py /app/

ENTRYPOINT [ "python", "./generate_executors_report.py"]

CMD [ "--help" ]