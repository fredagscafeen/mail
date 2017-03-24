import emailtunnel
import smtplib
import itertools


def sendmail(host, port, messages):
    client = smtplib.SMTP(host, port)
    client.set_debuglevel(0)
    for from_addr, to_addrs, msg in messages:
        yield
        client.ehlo_or_helo_if_needed()
        yield
        (code, resp) = client.mail(from_addr, [])
        yield
        if code != 250:
            if code == 421:
                client.close()
            else:
                client._rset()
            raise Exception(('SMTPSenderRefused', code, resp, from_addr))
        if isinstance(to_addrs, str):
            to_addrs = [to_addrs]
        for each in to_addrs:
            (code, resp) = client.rcpt(each, [])
            yield
            if (code != 250) and (code != 251):
                raise Exception(('SMTPRecipientsRefused', each, code, resp))
            if code == 421:
                client.close()
                raise Exception(('SMTPRecipientsRefused', senderrs))
        (code, resp) = client.data(msg)
        if code != 250:
            if code == 421:
                client.close()
            else:
                client._rset()
            raise Exception(('SMTPDataError', code, resp))


def main():
    server_host = '127.0.0.1'
    server_port = 8000
    server = emailtunnel.LoggingReceiver(server_host, server_port)
    server.start()

    from_addr = 'test1@local'
    to_addr = 'test2@local'
    msg = '''\
From: {from_addr}\r
To: {to_addr}\r
\r
Hello world!
'''.format(from_addr=from_addr, to_addr=to_addr)

    envelope = [(from_addr, [to_addr], msg)]

    clients = []
    clients.append(itertools.chain(
        sendmail(server_host, server_port, envelope),
        sendmail(server_host, server_port, envelope)))
    clients.append(sendmail(server_host, server_port, 2*envelope))

    done = object()
    while clients:
        # Run one step in each client
        clients[:] = [c for c in clients if next(c, done) is not done]

    server.stop()
    try:
        # Can we still send emails?
        any(sendmail(server_host, server_port, 2*envelope))
    except ConnectionRefusedError:
        # Indeed, server.stop() worked.
        pass
    else:
        raise Exception("Expected ConnectionRefusedError")


if __name__ == "__main__":
    main()
