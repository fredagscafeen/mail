import os
import re
import email
import collections
import itertools


class ReportParseError(Exception):
    pass


EmailDeliveryReport = collections.namedtuple(
    'EmailDeliveryReport', 'notification message recipients')


standard_responses = {
    'google.com': [
        # 539 occurrences from 2015-01-29 to 2017-03-18
        ('4.7.0', 'Rate limited',
         'Our system has detected an unusual rate of unsolicited mail ' +
         'originating from your IP address. To protect our users from spam, ' +
         'mail sent from your IP address has been temporarily rate ' +
         'limited.'),
        # 42 occurrences from 2015-01-29 to 2017-03-18
        ('4.7.0', 'Blocked due to spam content/links',
         'Our system has detected that this message is suspicious due to ' +
         'the nature of the content and/or the links within. To best ' +
         'protect our users from spam, the message has been blocked.'),
        # 209 occurrences from 2015-01-29 to 2017-03-18
        ('5.7.0', 'Attachment virus',
         'This message was blocked because its content presents a potential ' +
         'security issue.'),
        # 91 occurrences from 2015-01-29 to 2017-03-18
        ('5.7.1', 'DMARC failure',
         "is not accepted due to domain's DMARC policy."),
        # 4 occurrences from 2015-01-29 to 2017-03-18
        ('5.7.1', 'Blocked due to spam content/links',
         'Our system has detected that this message is likely unsolicited ' +
         'mail. To reduce the amount of spam sent to Gmail, this message ' +
         'has been blocked.'),
        # 29 occurrences from 2015-01-29 to 2017-03-18
        ('5.1.1', 'No such user',
         "The email account that you tried to reach does not exist. Please " +
         "try double-checking the recipient's email address for typos or " +
         "unnecessary spaces."),
    ],
    'hotmail.com': [
        # 87 occurrences from 2015-01-29 to 2017-03-18
        ('5.7.0', 'DMARC failure',
         'could not be delivered due to domain owner policy ' +
         'restrictions.'),
        # 2 occurrences from 2015-01-29 to 2017-03-18
        ('5.7.0', 'Not RFC 5322',
         'Message could not be delivered. Please ensure the message is RFC ' +
         '5322 compliant.'),
        # 360 occurrences from 2015-01-29 to 2017-03-18
        ('5.0.0', 'IP blocked',
         'Please contact your Internet service provider since part of their ' +
         'network is on our block list.'),
        # 126 occurrences from 2015-01-29 to 2017-03-18
        ('5.0.0', 'Mailbox unavailable',
         'Requested action not taken: mailbox unavailable'),
    ],
    'yahoodns.net': [
        # 5 occurrences from 2015-01-29 to 2017-03-18
        ('5.7.9', 'DMARC failure',
         'Message not accepted for policy reasons. See ' +
         'https://help.yahoo.com/kb/postmaster/SLN7253.html'),
    ],
    'sitnet.dk': [
        # 28 occurrences from 2015-01-29 to 2017-03-18
        ('5.7.1', 'Content rejected',
         'Error: content rejected / indhold afvist'),
    ],
    '127.0.0.1': [
        # 196 occurrences from 2015-01-29 to 2017-03-18
        ('5.0.0', 'Emailtunnel 550',
         'Requested action not taken: mailbox unavailable'),
    ],
    # This empty entry makes mail from *.one.com appear as just one.com in logs
    'one.com': [],
}


prefixes = {}
postfixes = {}


def iter_common_prefix(x, y):
    for a, b in zip(x, y):
        if a == b:
            yield a
        else:
            return


def longest_common_prefix(x, y):
    return ''.join(iter_common_prefix(x, y))


def longest_common_postfix(x, y):
    common_postfix_reversed = iter_common_prefix(reversed(x), reversed(y))
    return ''.join(reversed(list(common_postfix_reversed)))


stats = collections.Counter()


def record_stats(host, code, summary, needle, rest):
    if needle:
        prefix = rest[:rest.index(needle)]
        postfix = rest[rest.index(needle):]
        k = (host, summary)
        prefixes[k] = longest_common_postfix(
            prefixes.get(k, prefix), prefix)
        postfixes[k] = longest_common_prefix(
            postfixes.get(k, postfix), postfix)
    stats[host, code, summary] += 1


def dump_stats():
    for host, rules in standard_responses.items():
        for code, summary, needle in rules:
            k = (host, code, summary)
            print(k, stats.pop(k, 0))
    from pprint import pprint
    pprint(stats)
    for k in prefixes.keys():
        print(k, prefixes[k] + postfixes[k])


def abbreviate_recipients(recipients):
    if all('@' in rcpt for rcpt in recipients):
        parts = [rcpt.split('@', 1) for rcpt in recipients]
        parts.sort(key=lambda x: (x[1].lower(), x[0].lower()))
        by_domain = [
            (domain, [a[0] for a in aa])
            for domain, aa in itertools.groupby(
                parts, key=lambda x: x[1])
        ]
        return ', '.join(
            '<%s@%s>' % (','.join(aa), domain)
            for domain, aa in by_domain)
    else:
        return ', '.join('<%s>' % x for x in recipients)


def abbreviate_diagnostic_message(remote_mta, status, message):
    code = message[:3]

    # Remove leading "550" and any occurrence of e.g. "421-4.7.0" inside
    # the diagnostic message. Google in particular repeats the status
    # and code multiple times; others just have it in the beginning.
    message = re.sub('^%s |%s[- ]%s ' % (code, code, status), '', message)

    for host, rules in standard_responses.items():
        if remote_mta == host or remote_mta.endswith('.' + host):
            for status_, summary, needle in rules:
                if status == status_ and needle in message:
                    # record_stats(host, status, summary, needle, message)
                    return '%s (%s-%s from %s)' % (summary, code, status, host)

            if host == 'one.com':
                message = re.sub(' \([0-9a-f-]+\)$', '', message)

            # record_stats(host, status, None, None, message)
            return '%s (%s-%s from %s)' % (message, code, status, host)
    # record_stats(remote_mta, code, None, None, message)

    return '%s (%s-%s from %s)' % (message, code, status, remote_mta)


RecipientStatus = collections.namedtuple(
    'RecipientStatus',
    'recipient action status diagnostic_code remote_mta will_retry')


def parse_typed_field(header, key, required_type=None, required=True):
    if header is None or isinstance(header, str):
        value = header
    else:
        value = header.get(key)
    if not value:
        if required:
            raise ReportParseError('Header %r is required' % key)
        elif required_type:
            return None
        else:
            return None, None
    try:
        type, text = value.split(';', 1)
    except ValueError:
        raise Exception()
    if required_type is None:
        return type.strip().lower(), text.strip()
    elif type.strip().lower() != required_type:
        raise ReportParseError('Expected header %r of type %r, not %r' %
                               (key, required_type, type))
    return text.strip()


def parse_report_message(report_message):
    if report_message.get_content_type() != 'message/delivery-status':
        raise Exception()
    report_desc = report_message.get('Content-Description')
    if report_desc not in ('Delivery report', 'Delivery error report'):
        raise Exception()
    if not report_message.is_multipart():
        raise Exception()
    message_status = report_message.get_payload()[0]
    recipients_fields = report_message.get_payload()[1:]

    reporting_mta = parse_typed_field(
        message_status, 'Reporting-MTA', 'dns')

    statuses = []
    for recipient_fields in recipients_fields:
        if recipient_fields.items() == []:
            # Broken reports from Exch08.uni.au.dk
            continue
        recipient = parse_typed_field(
            recipient_fields, 'Final-Recipient', 'rfc822')

        action = (recipient_fields.get('Action') or '').lower()
        ACTIONS = 'failed delayed delivered relayed expanded'.split()
        if action not in ACTIONS:
            raise Exception()
        status = recipient_fields.get('Status') or ''
        if status[:2] not in ('2.', '4.', '5.'):
            raise Exception()
        remote_mta = parse_typed_field(
            recipient_fields, 'Remote-MTA', 'dns', required=False)
        diagnostic_code = recipient_fields.get('Diagnostic-Code')
        will_retry = bool(recipient_fields.get('Will-Retry-Until'))

        statuses.append(RecipientStatus(
            recipient, action, status, diagnostic_code, remote_mta, will_retry))

    return reporting_mta, statuses


def notification_from_report(report):
    reporting_mta, statuses = report
    n = {}
    for status in statuses:
        diagnostic_type, diagnostic_text = parse_typed_field(
            re.sub(r'\s+', ' ', status.diagnostic_code or ''),
            'status.diagnostic_code')
        if diagnostic_type == 'smtp':
            message = abbreviate_diagnostic_message(
                status.remote_mta or '',
                status.status,
                diagnostic_text)
        else:
            message = diagnostic_text
        if status.will_retry:
            message += '; message will be retried'
        n.setdefault(message, []).append(status.recipient)
    return '; '.join(
        '%s: %s' % (abbreviate_recipients(recipients), message)
        for message, recipients in n.items())


def parse_delivery_report(message):
    report_from = (
        'MAILER-DAEMON@pulerau.scitechtinget.dk (Mail Delivery System)')
    mime_report = 'multipart/report; report-type=delivery-status'
    if not message.get('Content-Type', '').startswith(mime_report):
        return
    if message.get('From') != report_from:
        return
    if not message.is_multipart():
        raise Exception()
    report_parts = message.get_payload()
    if len(report_parts) != 3:
        raise Exception()
    notification_message, report_message, undelivered_part = report_parts
    report = parse_report_message(report_message)
    recipients = [r.recipient for r in report[1]]
    notification = notification_from_report(report)
    undelivered_desc = undelivered_part.get('Content-Description')
    undelivered_descs = ('Undelivered Message',
                         'Undelivered Message Headers')
    if undelivered_desc not in undelivered_descs:
        raise Exception()
    if undelivered_desc == 'Undelivered Message':
        if not undelivered_part.is_multipart():
            raise Exception()
        if undelivered_part['Content-Type'] != 'message/rfc822':
            raise Exception()
        if len(undelivered_part.get_payload()) != 1:
            raise Exception()
        undelivered_message, = undelivered_part.get_payload()
    else:
        if undelivered_part.is_multipart():
            raise Exception()
        if undelivered_part['Content-Type'] != 'text/rfc822-headers':
            raise Exception()
        undelivered_message = email.message_from_string(
            undelivered_part.get_payload())
    return EmailDeliveryReport(notification, undelivered_message, recipients)


def email_delivery_reports():
    repo_root = os.path.abspath(
        os.path.dirname(os.path.dirname(__file__)))
    path = os.path.join(repo_root, 'errorarchive')
    for filename in sorted(os.listdir(path)):
        base, ext = os.path.splitext(filename)
        if ext != '.mail':
            continue
        filepath = os.path.join(path, filename)
        with open(filepath, 'rb') as fp:
            message = email.message_from_binary_file(fp)
        try:
            parsed = parse_delivery_report(message)
        except ReportParseError as exn:
            print(base, exn)
            continue
        except Exception as exn:
            print(base, exn)
            raise

        if parsed:
            yield base, parsed
