import os
import re
import email


BY_POSTFIX = r''
SMTP_ID = r'with E?SMTPS? id [+A-Za-z0-9-]+'
FOR = r'(( |\n\t)for <[^@]+@(fredagscafeen)\.(dk|DK)>)?;( |\n\t)'
TIME = r'[A-Za-z0-9, :+]+ \(CES?T\)$'


patterns = [
    r'^from localhost \(localhost\.localdomain \[127\.0\.0\.1\]\)\n\t' +
    BY_POSTFIX +
    SMTP_ID + FOR + TIME,

    r'^from (?P<helo_name>\S+) ' +
    r'\((?P<name>[A-Za-z0-9_.-]+) \[(?P<ip>[0-9.]+)\]\)\n\t' +
    BY_POSTFIX +
    SMTP_ID + FOR + TIME,
]


for f in os.listdir('errorarchive'):
    if not f.endswith('.mail'):
        continue
    with open('errorarchive/%s' % f, 'rb') as fp:
        message = email.message_from_binary_file(fp)
    received = message.get_all('Received')
    if received is None:
        continue  # Probably a test email
    if type(received) != list:
        raise TypeError(received)
    if 'emailtunnel' in str(received[0]):
        continue
    assert len(received) >= len(patterns), (received, f)
    for r, p in zip(received, patterns):
        if not re.match(p, str(r)):
            print(str(r))
            print(p)
            raise ValueError(f)
    mo = re.match(patterns[2], str(received[2]))
    print(*mo.group('helo_name', 'name', 'ip'))
