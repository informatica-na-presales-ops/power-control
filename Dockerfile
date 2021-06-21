FROM python:3.9.5-alpine3.13

RUN /usr/sbin/adduser -g python -D python

USER python
RUN /usr/local/bin/python -m venv /home/python/venv

COPY --chown=python:python requirements.txt /home/python/power-control/requirements.txt
RUN /home/python/venv/bin/pip install --no-cache-dir --requirement /home/python/power-control/requirements.txt

ENV ADMIN_EMAIL="" \
    APP_VERSION="2021.1" \
    AWS_ACCESS_KEY_ID="" \
    AWS_DEFAULT_REGION="us-west-2" \
    AWS_SECRET_ACCESS_KEY="" \
    AWS_SES_CONFIGURATION_SET="" \
    DRY_RUN="true" \
    LOG_FORMAT="%(levelname)s [%(name)s] %(message)s" \
    LOG_LEVEL="INFO" \
    NOTIFICATION_WAIT_HOURS="12" \
    PATH="/home/python/venv/bin:${PATH}" \
    PROTECTED_OWNERS="" \
    PYTHONUNBUFFERED="1" \
    SEND_EMAIL="false" \
    SMTP_FROM="" \
    SMTP_HOST="" \
    SMTP_PASSWORD="" \
    SMTP_USERNAME="" \
    TEMPLATE_PATH="/home/python/power-control/templates" \
    TRACKING_FILE="/data/power-control.json" \
    TZ="Etc/UTC"

ENTRYPOINT ["/home/python/venv/bin/python"]
CMD ["/home/python/power-control/power_control.py"]

LABEL org.opencontainers.image.authors="William Jackson <wjackson@informatica.com>" \
      org.opencontainers.image.source="https://github.com/informatica-na-presales-ops/power-control" \
      org.opencontainers.image.version="${APP_VERSION}"

COPY --chown=python:python power_control.py /home/python/power-control/power_control.py
COPY --chown=python:python templates /home/python/power-control/templates
