FROM python:3.7.4-alpine3.10

COPY requirements.txt /power-control/requirements.txt

RUN /usr/local/bin/pip install --no-cache-dir --requirement /power-control/requirements.txt

COPY . /power-control

ENV ADMIN_EMAIL="" \
    APP_VERSION="1.0.2" \
    AWS_ACCESS_KEY_ID="" \
    AWS_DEFAULT_REGION="us-west-2" \
    AWS_SECRET_ACCESS_KEY="" \
    AWS_SES_CONFIGURATION_SET="" \
    DRY_RUN="true" \
    LOG_FORMAT="%(levelname)s [%(name)s] %(message)s" \
    LOG_LEVEL="INFO" \
    NOTIFICATION_WAIT_HOURS="12" \
    PROTECTED_OWNERS="" \
    PYTHONUNBUFFERED="1" \
    SEND_EMAIL="false" \
    SMTP_FROM="" \
    SMTP_HOST="" \
    SMTP_PASSWORD="" \
    SMTP_USERNAME="" \
    TEMPLATE_PATH="/power-control/templates" \
    TRACKING_FILE="/data/power-control.json" \
    TZ="Etc/UTC"

ENTRYPOINT ["/usr/local/bin/python", "/power-control/power_control.py"]

LABEL org.opencontainers.image.authors="William Jackson <wjackson@informatica.com>" \
      org.opencontainers.image.version="${APP_VERSION}"
