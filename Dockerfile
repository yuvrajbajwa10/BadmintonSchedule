# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13.0rc1
FROM python:${PYTHON_VERSION}-alpine as base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a non-privileged user with a home directory
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/home/appuser" \
    --shell "/bin/sh" \
    --uid "${UID}" \
    appuser

# Set the working directory to the user's home
WORKDIR /home/appuser

# Download dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python -m pip install -r requirements.txt

# Switch to the non-privileged user
USER appuser

RUN mkdir -p /home/appuser/data
RUN chown -R appuser:appuser /home/appuser
RUN chmod -R 755 /home/appuser/data
VOLUME [ "/home/appuser/data" ]

# Copy the source code into the container
COPY --chown=appuser:appuser . .

# Expose the port that the application listens on
EXPOSE 5000

# Run the application
CMD gunicorn --bind 0.0.0.0:5000 app:app