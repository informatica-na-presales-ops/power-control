FROM python:3.12-alpine

RUN /usr/sbin/adduser -g python -D python

USER python
RUN /usr/local/bin/python -m venv /home/python/venv

COPY --chown=python:python requirements.txt /home/python/power-control/requirements.txt
RUN /home/python/venv/bin/pip install --no-cache-dir --requirement /home/python/power-control/requirements.txt

ENV APP_VERSION="2023.2" \
    AWS_DEFAULT_REGION="us-west-2" \
    DRY_RUN="true" \
    LOG_FORMAT="%(levelname)s [%(name)s] %(message)s" \
    LOG_LEVEL="INFO" \
    NOTIFICATION_WAIT_HOURS="12" \
    PATH="/home/python/venv/bin:${PATH}" \
    PROTECTED_OWNERS="" \
    PYTHONDONTWRITEBYTECODE="1" \
    PYTHONUNBUFFERED="1" \
    SEND_EMAIL="false" \
    TEMPLATE_PATH="/home/python/power-control/templates" \
    TRACKING_FILE="/data/power-control.json" \
    TZ="Etc/UTC"

ENTRYPOINT ["/home/python/venv/bin/python"]
CMD ["/home/python/power-control/power_control.py"]

LABEL org.opencontainers.image.source="https://github.com/informatica-na-presales-ops/power-control" \
      org.opencontainers.image.version="${APP_VERSION}"

COPY --chown=python:python power_control.py /home/python/power-control/power_control.py
COPY --chown=python:python templates /home/python/power-control/templates
