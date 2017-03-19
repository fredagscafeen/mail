import os
import re
import email
import collections
import itertools


EmailDeliveryReport = collections.namedtuple(
    'EmailDeliveryReport', 'notification message')


standard_responses = {
    'google.com': [
        # 539 occurrences from 2015-01-29 to 2017-03-18
        ('421-4.7.0', 'Unusual rate of spam',
         'Our system has detected an unusual rate of unsolicited mail ' +
         'originating from your IP address. To protect our users from spam, ' +
         'mail sent from your IP address has been temporarily rate ' +
         'limited.'),
        # 42 occurrences from 2015-01-29 to 2017-03-18
        ('421-4.7.0', '421 looks like spam',
         'Our system has detected that this message is suspicious due to ' +
         'the nature of the content and/or the links within. To best ' +
         'protect our users from spam, the message has been blocked.'),
        # 209 occurrences from 2015-01-29 to 2017-03-18
        ('552-5.7.0', 'Attachment virus',
         'This message was blocked because its content presents a potential ' +
         'security issue.'),
        # 91 occurrences from 2015-01-29 to 2017-03-18
        ('550-5.7.1', 'DMARC failure',
         "is not accepted due to domain's DMARC policy."),
        # 4 occurrences from 2015-01-29 to 2017-03-18
        ('550-5.7.1', '550 looks like spam',
         'Our system has detected that this message is likely unsolicited ' +
         'mail. To reduce the amount of spam sent to Gmail, this message ' +
         'has been blocked.'),
        # 29 occurrences from 2015-01-29 to 2017-03-18
        ('550-5.1.1', 'No such user',
         "The email account that you tried to reach does not exist. Please " +
         "try double-checking the recipient's email address for typos or " +
         "unnecessary spaces."),
    ],
    'hotmail.com': [
        # 87 occurrences from 2015-01-29 to 2017-03-18
        ('550 5.7.0', 'Domain owner policy restrictions',
         'could not be delivered due to domain owner policy ' +
         'restrictions.'),
        # 2 occurrences from 2015-01-29 to 2017-03-18
        ('550 5.7.0', 'Not RFC 5322',
         'Message could not be delivered. Please ensure the message is RFC ' +
         '5322 compliant.'),
        # 360 occurrences from 2015-01-29 to 2017-03-18
        ('550', 'IP blocked',
         'Please contact your Internet service provider since part of their ' +
         'network is on our block list.'),
        # 126 occurrences from 2015-01-29 to 2017-03-18
        ('550', 'Mailbox unavailable',
         'Requested action not taken: mailbox unavailable'),
    ],
    'yahoodns.net': [
        # 5 occurrences from 2015-01-29 to 2017-03-18
        ('554 5.7.9', 'DMARC failure',
         'Message not accepted for policy reasons. See ' +
         'https://help.yahoo.com/kb/postmaster/SLN7253.html'),
    ],
    'sitnet.dk': [
        # 28 occurrences from 2015-01-29 to 2017-03-18
        ('550 5.7.1', 'Content rejected',
         'Error: content rejected / indhold afvist'),
    ],
    '127.0.0.1': [
        # 196 occurrences from 2015-01-29 to 2017-03-18
        ('550', 'Emailtunnel 550',
         'Requested action not taken: mailbox unavailable (in reply to end ' +
         'of DATA command)'),
    ],
    'one.com': [],
}


prefixes = {}
postfixes = {}


def longest_common_prefix(x, y):
    def f():
        for a, b in zip(x, y):
            if a == b:
                yield a
            else:
                return

    return ''.join(f())


def longest_common_postfix(x, y):
    def f():
        for a, b in zip(reversed(x), reversed(y)):
            if a == b:
                yield a
            else:
                return

    return ''.join(reversed(list(f())))


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


def parse_recipient_error(message):
    pattern = (
        r'^host (?P<hostname>[^ []+)\[(?P<hostip>[^] ]+)\] said: ' +
        r'(?P<code>\d+(?:[- ][0-9.]+)?) (?P<rest>.*)')
    mo = re.match(pattern, message)
    if not mo:
        # record_stats(None, None, None, None, message)
        return message

    actual_host = mo.group('hostname')
    code = mo.group('code')
    rest = mo.group('rest')

    if actual_host.endswith('.google.com'):
        # For some reason errors from Google repeat the code inside the message
        # at unpredictable positions (determined from line breaks before
        # Postfix's rewrapping of the message), so we just remove them.
        rest = rest.replace(code + ' ', '')
        rest = rest.replace(code.replace('-', ' ') + ' ', '')

    for host, rules in standard_responses.items():
        if actual_host == host or actual_host.endswith('.' + host):
            for code_, summary, needle in rules:
                if code == code_ and needle in rest:
                    # record_stats(host, code, summary, needle, rest)
                    return '%s (%s from %s)' % (summary, code, host)

            if host == 'one.com':
                rest = re.sub(' \([0-9a-f-]+\) \(in reply.*', '', rest)

            # record_stats(host, code, None, None, rest)
            return '"%s" (%s from %s)' % (rest, code, host)
    # record_stats(actual_host, code, None, None, rest)
    return message


def parse_notification(message):
    paragraphs = re.split(r'\n\n+', message.strip('\n'))
    paragraphs = [re.sub(r'\s+', ' ', p.strip()) for p in paragraphs]

    individual_error = '^<([^>]*)>:\s*(.*)$'
    friendly_paragraphs = []
    recipients = {}
    for orig_paragraph in paragraphs:
        paragraph = re.sub(r'\s+', ' ', orig_paragraph.strip())
        mo = re.match(individual_error, paragraph)
        if mo:
            rcpt, message = mo.groups()
            recipients.setdefault(
                parse_recipient_error(message), []).append(rcpt)
        else:
            friendly_paragraphs.append(orig_paragraph)
    friendly_text = '\n\n'.join(friendly_paragraphs)
    retried = 'It will be retried until it is' in friendly_text

    recipients_str = '; '.join('%s: %s' %
                               (abbreviate_recipients(recipients),
                                message)
                               for message, recipients in recipients.items())
    if retried:
        return '%s; message will be retried' % recipients_str
    else:
        return recipients_str


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
    notification_message, report, undelivered_part = report_parts
    notification_desc = notification_message.get('Content-Description')
    if notification_desc != 'Notification':
        raise Exception()
    report_desc = report.get('Content-Description')
    if report_desc not in ('Delivery report', 'Delivery error report'):
        raise Exception()
    undelivered_desc = undelivered_part.get('Content-Description')
    undelivered_descs = ('Undelivered Message',
                         'Undelivered Message Headers')
    if undelivered_desc not in undelivered_descs:
        raise Exception()
    if notification_message.is_multipart():
        raise Exception()
    notification_str = notification_message.get_payload()
    if not isinstance(notification_str, str):
        raise Exception()
    notification = parse_notification(notification_str)
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
    return EmailDeliveryReport(notification, undelivered_message)


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
        parsed = parse_delivery_report(message)
        if parsed:
            yield base, parsed
