import os
import re
import email


REPORT_FROM = 'MAILER-DAEMON@pulerau.scitechtinget.dk (Mail Delivery System)'
MIME_REPORT = 'multipart/report; report-type=delivery-status'
counter = {'Apple<appleid@id.apple.com>': 0,
           '"Instagram" <no-reply@mail.instagram.com>': 0,
           '<*@facebookmail.com>': 0,
           'Apple<appleid_dkda@email.apple.com>': 0,
           '<*@linkedin.com>': 0}


real_emails = 0

for f in sorted(os.listdir('errorarchive')):
    if not f.endswith('.mail'):
        continue
    with open('errorarchive/%s' % f, 'rb') as fp:
        message = email.message_from_binary_file(fp)
    if not message.get('Content-Type', '').startswith(MIME_REPORT):
        continue
    if message.get('From') != REPORT_FROM:
        continue
    assert message.is_multipart()
    payloads = {pl.get('Content-Description'): pl for pl in message.get_payload()}
    try:
        headers = payloads.pop('Undelivered Message Headers')
        assert payloads.setdefault('Undelivered Message', headers) is headers
    except KeyError:
        pass
    payloads.pop('Delivery report', None)
    payloads.pop('Delivery error report', None)
    assert set(payloads.keys()) == set(['Notification', 'Undelivered Message']), payloads
    notification = payloads['Notification']
    assert not notification.is_multipart()
    notification = notification.get_payload()
    if 'DMARC' in notification:
        undelivered = payloads['Undelivered Message']
        pl = undelivered.get_payload()
        if isinstance(pl, list):
            undelivered_message, = pl
        else:
            undelivered_message = email.message_from_string(pl)
        from_ = undelivered_message['From']
        if from_.endswith('@facebookmail.com>'):
            counter['<*@facebookmail.com>'] += 1
            continue
        elif from_.endswith('@linkedin.com>'):
            counter['<*@linkedin.com>'] += 1
            continue
        else:
            try:
                counter[from_] += 1
            except KeyError:
                pass
            else:
                continue
        real_emails += 1
        print(real_emails, f)
        for k, v in undelivered_message.items():
            if k.lower() in ('return-path', 'received') or k.startswith('List-'):
                continue
            if k.lower() in ('from', 'date', 'subject') or 'TAAGEKAMMERET' in str(v).upper():
                h = email.header.make_header(email.header.decode_header(v))
                print('%s: %s' % (k, h))
        print('', flush=True)
print(counter)
