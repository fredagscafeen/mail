import os
import re
import email


patterns = [
    r'^from localhost \(localhost\.localdomain \[127\.0\.0\.1\]\)\n\t' +
    r'by pulerau\.scitechtinget\.dk \(Postfix\) with ESMTP id [0-9A-F]+' +
    r'(\n\tfor <[^@]+@(taagekammeret|TAAGEKAMMERET)\.(dk|DK)>)?;( |\n\t)[A-Za-z0-9, :+]+ \(CES?T\)$',
    r'^from pulerau\.scitechtinget\.dk \(\[127\.0\.0\.1\]\)\n\t' +
    r'by localhost \(pulerau\.scitechtinget\.dk \[127\.0\.0\.1\]\) \(amavisd-new, port 10024\)\n\t' +
    r'with ESMTP id [+A-Za-z0-9-]+(( |\n\t)for <[^@]+@(taagekammeret|TAAGEKAMMERET)\.(dk|DK)>)?;( |\n\t)' +
    r'[A-Za-z0-9, :+]+ \(CES?T\)$',
    r'^from (?P<helo_name>\S+) \((?P<name>[A-Za-z0-9_.-]+) \[(?P<ip>[0-9.]+)\]\)\n\t' +
    r'by pulerau\.scitechtinget\.dk \(Postfix\) with E?SMTPS? id [0-9A-F]+' +
    r'(\n\tfor <[^@]+@(taagekammeret|TAAGEKAMMERET)\.(dk|DK)>)?;( |\n\t)[A-Za-z0-9, :+]+ \(CES?T\)$',

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
    if 'MAILER-DAEMON@pulerau.scitechtinget.dk' in str(message.get('From')):
        continue
    assert len(received) >= len(patterns), (received, f)
    for r, p in zip(received, patterns):
        if not re.match(p, str(r)):
            print(str(r))
            print(p)
            raise ValueError(f)
    mo = re.match(patterns[2], str(received[2]))
    print(*mo.group('helo_name', 'name', 'ip'))
