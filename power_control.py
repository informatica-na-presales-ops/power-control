# Check the RUNNINGSCHEDULE tag on EC2 instances and shut them down if necessary

# A valid RUNNINGSCHEDULE tag value should be in the form: dd:dd:dd:dd:d-d
# That is, five fields separated by colons.

import boto3
import botocore.exceptions
import collections
import datetime
import email.message
import enum
import jinja2
import json
import logging
import os
import pathlib
import pytz
import smtplib
import sys

from typing import Dict, List

log = logging.getLogger(__name__)
if __name__ == '__main__':
    log = logging.getLogger('power_control')


class PowerControlReason(enum.Enum):
    NOT_RUNNING = enum.auto()
    MALFORMED = enum.auto()
    DAY_MISMATCH = enum.auto()
    TIME_MISMATCH = enum.auto()
    ALLOWED = enum.auto()
    NO_OWNER = enum.auto()
    PROTECTED_OWNER = enum.auto()


class Config:
    admin_email: str
    aws_ses_configuration_set: str
    dry_run: bool
    log_format: str
    log_level: str
    notification_wait_hours: int
    protected_owners: List[str]
    send_email: bool
    smtp_from: str
    smtp_host: str
    smtp_password: str
    smtp_username: str
    template_path: str
    tracking_file: str
    tz: str
    version: str

    def __init__(self):
        true_values = ('true', 'yes', 'on', '1')
        self.admin_email = os.getenv('ADMIN_EMAIL')
        self.aws_ses_configuration_set = os.getenv('AWS_SES_CONFIGURATION_SET')
        self.dry_run = os.getenv('DRY_RUN', 'true').lower() in true_values
        self.log_format = os.getenv('LOG_FORMAT', '%(levelname)s [%(name)s] %(message)s')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.notification_wait_hours = int(os.getenv('NOTIFICATION_WAIT_HOURS', 12))
        self.protected_owners = [o.strip().lower() for o in os.getenv('PROTECTED_OWNERS', '').split(',') if o]
        self.send_email = os.getenv('SEND_EMAIL', 'false').lower() in true_values
        self.smtp_from = os.getenv('SMTP_FROM')
        self.smtp_host = os.getenv('SMTP_HOST')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.template_path = os.getenv('TEMPLATE_PATH', '/power-control/templates')
        self.tracking_file = os.getenv('TRACKING_FILE', '/data/power-control.json')
        self.tz = os.getenv('TZ', 'Etc/UTC')
        self.version = os.getenv('APP_VERSION', 'unknown')

    @property
    def notification_times(self) -> Dict[str, datetime.datetime]:
        raw_data = {}
        path = pathlib.Path(self.tracking_file)
        if path.exists():
            with path.open() as f:
                raw_data = json.load(f)
        return {key: datetime.datetime.fromisoformat(value).astimezone(pytz.utc) for key, value in raw_data.items()}

    @notification_times.setter
    def notification_times(self, data: Dict[str, datetime.datetime]):
        path = pathlib.Path(self.tracking_file)
        with path.open('w') as f:
            json.dump({key: value.isoformat() for key, value in data.items()}, f, indent=1, sort_keys=True)


c = Config()
jinja_env = jinja2.Environment(trim_blocks=True, lstrip_blocks=True, loader=jinja2.FileSystemLoader(c.template_path))


def send_email(from_addr, to_addr, subject, body) -> bool:
    """Send an email. Return True if successful, False if not."""
    if c.send_email:
        log.warning(f'Sending email to {to_addr}')
        msg = email.message.EmailMessage()
        msg['X-SES-CONFIGURATION-SET'] = c.aws_ses_configuration_set
        msg['Subject'] = subject
        msg['From'] = from_addr
        msg['To'] = to_addr
        msg.set_content(body, subtype='html')
        with smtplib.SMTP_SSL(host=c.smtp_host) as s:
            s.login(user=c.smtp_username, password=c.smtp_password)
            try:
                s.send_message(msg)
            except smtplib.SMTPRecipientsRefused as e:
                log.error(f'{e}')
                return False
    else:
        log.warning(f'Not sending email to {to_addr}\n{body}')
    return True


def parse_schedule(schedule: str):
    tokens = schedule.split(':')
    if not len(tokens) == 5:
        return False
    try:
        start_time = datetime.time.fromisoformat(f'{tokens[0]}:{tokens[1]}')
        stop_time = datetime.time.fromisoformat(f'{tokens[2]}:{tokens[3]}')
    except ValueError:
        return False
    day_tokens = tokens[4].split('-')
    if not len(day_tokens) == 2:
        return False
    try:
        first_day = int(day_tokens[0])
        last_day = int(day_tokens[1])
    except ValueError:
        return False
    if last_day < first_day:
        return False
    if first_day < 1 or first_day > 7 or last_day < 1 or last_day > 7:
        return False
    return start_time, stop_time, first_day, last_day


def get_tag(instance, tag_key):
    if instance.tags is None:
        return ''
    for tag in instance.tags:
        if tag['Key'] == tag_key:
            return tag['Value']
    return ''


def get_instance_owner(instance):
    return get_tag(instance, 'OWNEREMAIL').strip().lower() or '(no owner)'


def get_running_schedule(instance):
    return get_tag(instance, 'RUNNINGSCHEDULE') or '(no schedule)'


def instance_is_running(instance):
    return instance.state['Name'] == 'running'


def get_instance_name(instance):
    return get_tag(instance, 'Name') or '(no name)'


def get_instance_dict(instance, region):
    return {
        'id': instance.id,
        'name': get_instance_name(instance),
        'owner': get_instance_owner(instance),
        'region': region,
        'running_schedule': get_running_schedule(instance)
    }


def do_power_control(instance, current_day, current_time) -> PowerControlReason:
    if not instance_is_running(instance):
        log.info(f'{instance.id}: skipping because this instance is not running')
        return PowerControlReason.NOT_RUNNING

    owner = get_instance_owner(instance)
    if owner == '(no owner)':
        log.info(f'{instance.id}: skipping because this instance has no owner')
        return PowerControlReason.NO_OWNER

    if owner in c.protected_owners:
        log.info(f'{instance.id}: skipping because instance owner is protected')
        return PowerControlReason.PROTECTED_OWNER

    schedule = parse_schedule(get_running_schedule(instance))
    if not schedule:
        log.info(f'{instance.id}: skipping because RUNNINGSCHEDULE is not in the correct form')
        return PowerControlReason.MALFORMED

    start_time, stop_time, first_day, last_day = schedule

    if current_day < first_day or current_day > last_day:
        log.warning(f'{instance.id}: stopping because today is outside RUNNINGSCHEDULE')
        return PowerControlReason.DAY_MISMATCH

    if current_time < start_time or current_time > stop_time:
        log.warning(f'{instance.id}: stopping because current time is outside RUNNINGSCHEDULE')
        return PowerControlReason.TIME_MISMATCH

    log.info(f'{instance.id}: skipping because this instance is allowed at this time')
    return PowerControlReason.ALLOWED


def process_notification_times(instances: List[Dict], utc_now: datetime.datetime) -> List[Dict]:
    """Compare a list of instances to the record of when we last sent a notification for each instance. If an instance
    has been notified about less than 12 hours ago, remove it from the list because we don't want to send another
    notification yet."""

    # First we take the record of notification times and clear out any instances that we sent notifications for over 12
    # hours ago
    notification_times = c.notification_times
    notification_times_pruned = {}
    for instance_id, time in notification_times.items():
        if time + datetime.timedelta(hours=c.notification_wait_hours) > utc_now:
            notification_times_pruned[instance_id] = time

    # Now we go through our instances that we might want to send notifications for and drop any that we sent
    # notifications for in the last 12 hours
    new_list = []
    for instance in instances:
        instance_id = instance['id']
        if instance_id in notification_times_pruned:
            log.warning(f'{instance_id}: will be stopped but not notified!')
        else:
            notification_times_pruned[instance_id] = utc_now
            new_list.append(instance)

    c.notification_times = notification_times_pruned
    return new_list


def group_by_region(instances: List[Dict]) -> Dict[str, List[Dict]]:
    result = collections.defaultdict(list)
    for instance in instances:
        region_instances = result[instance['region']]
        region_instances.append(instance)
        result[instance['region']] = region_instances
    return result


def group_by_owner(instances: List[Dict]) -> Dict[str, List[Dict]]:
    result = collections.defaultdict(list)
    for instance in instances:
        owner_instances = result[instance['owner']]
        owner_instances.append(instance)
        result[instance['owner']] = owner_instances
    return result


def main():
    logging.basicConfig(format=c.log_format, level=logging.DEBUG, stream=sys.stdout)
    log.debug(f'power-control {c.version}')
    if not c.log_level == 'DEBUG':
        log.debug(f'Setting log level to {c.log_level}')
    logging.getLogger().setLevel(c.log_level)

    log.info(f'PROTECTED_OWNERS: {c.protected_owners}')
    log.info(f'TZ: {c.tz}')
    zone = pytz.timezone(c.tz)
    utc_now = pytz.utc.localize(datetime.datetime.utcnow())
    now = utc_now.astimezone(zone)
    current_day = now.isoweekday()
    current_time = now.time()
    log.info(f'Current day is {now:%A} ({current_day})')
    log.info(f'Current time is {current_time:%H:%M}')

    session = boto3.session.Session()
    results = collections.defaultdict(list)
    for region in session.get_available_regions('ec2'):
        log.info(f'Checking {region}')
        ec2 = boto3.resource('ec2', region_name=region)
        try:
            for instance in ec2.instances.all():
                reason = do_power_control(instance, current_day, current_time)
                results_for_reason = results[reason]
                results_for_reason.append(get_instance_dict(instance, region))
                results[reason] = results_for_reason
        except botocore.exceptions.ClientError as e:
            log.critical(e)
            log.critical(f'Skipping {region}')

    instances_to_stop = results[PowerControlReason.DAY_MISMATCH] + results[PowerControlReason.TIME_MISMATCH]
    instances_to_notify = process_notification_times(instances_to_stop, utc_now)
    instances_to_notify_grouped = group_by_owner(instances_to_notify)

    notified_owners = []
    problem_owners = []
    for owner, instances in instances_to_notify_grouped.items():
        # Notify owners that instances are going to be stopped
        owner_template = jinja_env.get_template('owner-notification.html')
        ctx = {
            'config': c,
            'instances': instances
        }
        owner_report = owner_template.render(ctx=ctx)
        success = send_email(c.smtp_from, owner, 'Automatically stopping your environments', owner_report)
        if success:
            notified_owners.append(owner)
        else:
            problem_owners.append(owner)

    admin_template = jinja_env.get_template('admin-report.html')
    ctx = {
        'config': c,
        'instances_allowed': results[PowerControlReason.ALLOWED],
        'instances_malformed_exist': len(results[PowerControlReason.MALFORMED]) > 0,
        'instances_malformed': results[PowerControlReason.MALFORMED],
        'instances_no_owner_exist': len(results[PowerControlReason.NO_OWNER]) > 0,
        'instances_no_owner': results[PowerControlReason.NO_OWNER],
        'instances_not_running': results[PowerControlReason.NOT_RUNNING],
        'instances_protected_owner': results[PowerControlReason.PROTECTED_OWNER],
        'instances_to_stop': instances_to_stop,
        'notified_owners': notified_owners,
        'notified_owners_exist': len(notified_owners) > 0,
        'problem_owners': problem_owners,
        'problem_owners_exist': len(problem_owners) > 0,
        'run_time': f'{now:%A} ({current_day}) {current_time:%H:%M}'
    }
    admin_report = admin_template.render(ctx=ctx)
    if len(instances_to_notify) > 0:
        send_email(c.smtp_from, c.admin_email, 'NA Presales Power Control Run Report', admin_report)

    if not c.dry_run:
        for region, instances in group_by_region(instances_to_stop).items():
            ec2 = boto3.resource('ec2', region_name=region)
            ec2.instances.filter(InstanceIds=[i['id'] for i in instances]).stop()


if __name__ == '__main__':
    main()
