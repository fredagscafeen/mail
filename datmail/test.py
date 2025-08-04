import time
import logging
import smtplib

import email.header

from emailtunnel import SMTPReceiver, Envelope, logger
from datmail.server import DatForwarder
import emailtunnel.send


envelopes = []


def configure_logging():
    stream_handler = logging.StreamHandler(None)
    fmt = '[%(asctime)s %(levelname)s] %(message)s'
    datefmt = None
    formatter = logging.Formatter(fmt, datefmt, '%')
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logger.setLevel(logging.DEBUG)


def deliver_local(message, recipients, sender):
    logger.info("deliver_local: From: %r To: %r Subject: %r" %
                (sender, recipients, str(message.subject)))
    for recipient in recipients:
        if '@' not in recipient:
            raise smtplib.SMTPDataError(0, 'No @ in %r' % recipient)
    envelope = Envelope(message, sender, recipients)
    envelopes.append(envelope)


def forward_local(original_envelope, message, recipients, sender):
    logger.info("forward_local: From: %r To: %r Subject: %r" %
                (sender, recipients, str(message.subject)))
    for recipient in recipients:
        if '@' not in recipient:
            raise smtplib.SMTPDataError(0, 'No @ in %r' % recipient)
    envelope = Envelope(message, sender, recipients)
    envelopes.append(envelope)


def store_failed_local(envelope, description, summary):
    logger.info("Absorb call to store_failed_envelope")

    # The method as_bytes is called in the real implementation;
    # when testing, ensure that it wouldn't raise an exception.
    _b = envelope.message.as_bytes()

    metadata = {
        'mailfrom': envelope.mailfrom,
        'rcpttos': envelope.rcpttos,
        'subject': str(envelope.message.subject),
        'date': envelope.message.get_header('Date'),
        'summary': summary,
    }
    print("Description: %r" % (description,))
    print("metadata =\n%s" % (metadata,))


class DumpReceiver(SMTPReceiver):
    def handle_envelope(self, envelope):
        envelopes.append(envelope)


class RecipientTest(object):
    _recipients = []

    def get_envelopes(self):
        envelopes = []
        for i, recipient in enumerate(self._recipients):
            envelopes.append(
                ('-F', 'recipient_test@localhost',
                 '-f', 'recipient_test@localhost',
                 '-T', '%s@fredagscafeen.dk' % recipient,
                 '-s', '%s_%s' % (id(self), i),
                 '-I', 'X-test-id', self.get_test_id()))
        return envelopes

    def get_test_id(self):
        return str(id(self))

    def check_envelopes(self, envelopes):
        if not envelopes:
            raise AssertionError(
                "No envelopes for test id %r" % self.get_test_id())
        recipients = []
        for i, envelope in enumerate(envelopes):
            recipients += envelope.rcpttos
        self.check_recipients(recipients)

    def check_recipients(self, recipients):
        raise NotImplementedError()


class SameRecipientTest(RecipientTest):
    def __init__(self, *recipients):
        self._recipients = recipients

    def check_recipients(self, recipients):
        if len(recipients) != len(self._recipients):
            raise AssertionError(
                "Bad recipient count: %r vs %r" %
                (recipients, self._recipients))
        if any(x != recipients[0] for x in recipients):
            raise AssertionError("Recipients not the same: %r" % recipients)


class MultipleRecipientTest(RecipientTest):
    def __init__(self, recipient):
        self._recipients = [recipient]

    def check_recipients(self, recipients):
        if len(recipients) <= 1:
            raise AssertionError("Only %r recipients" % len(recipients))


class SingleRecipientTest(RecipientTest):
    def __init__(self, recipient):
        self._recipients = [recipient]

    def check_recipients(self, recipients):
        if len(recipients) != 1:
            raise AssertionError("%r recipients" % len(recipients))


class NoSubjectRewriteTest(object):
    '''
    Test that emails from yahoo.com do not have subjects rewritten.
    '''

    def __init__(self, subject):
        self.subject = subject

    def get_envelopes(self):
        from_address = 'anders@bruunseverinsen.dk'
        return [
            ('-F', from_address,
             '-f', from_address,
             '-T', 'form@fredagscafeen.dk',
             '-s', self.subject,
             '-I', 'X-test-id', self.get_test_id(),
             '-I', 'DKIM-Signature', 'dummy-signature',
            )
        ]

    def check_envelopes(self, envelopes):
        if not envelopes:
            raise AssertionError(
                "No envelopes for test id %r" % self.get_test_id())
        message = envelopes[0].message

        try:
            output_subject_raw = message.get_unique_header('Subject')
        except KeyError as e:
            raise AssertionError('No Subject in message') from e

        input_header = email.header.make_header(
            email.header.decode_header(self.subject))

        input_subject = str(input_header)
        output_subject = str(message.subject)
        expected_subject = input_subject

        if output_subject != expected_subject:
            raise AssertionError(
                'Bad subject: %r == %r turned into %r == %r, '
                'expected %r' % (self.subject, input_subject,
                                 output_subject_raw, output_subject,
                                 expected_subject))

    def get_test_id(self):
        return str(id(self))


class NoListUnsubscribeTest(object):
    '''
    Test that emails with "h=list-unsubscribe" in DKIM-Signature
    do not have List-Unsubscribe added.
    '''

    def get_envelopes(self):
        from_address = 'dkim@test.local'
        return [
            ('-F', from_address,
             '-f', from_address,
             '-T', 'form@fredagscafeen.dk',
             '-s', 'test',
             '-I', 'X-test-id', self.get_test_id(),
             '-I', 'DKIM-Signature',
             '''v=1; a=rsa-sha256; d=ummy;s=tupid; c=relaxed/relaxed; \
             q=dns/txt; t=est; h=feedback-id:list-unsubscribe:reply-to; \
             bh=test; b=test''',
            )
        ]

    def check_envelopes(self, envelopes):
        if not envelopes:
            raise AssertionError(
                "No envelopes for test id %r" % self.get_test_id())
        message = envelopes[0].message

        try:
            message.get_unique_header('List-Unsubscribe')
        except KeyError as e:
            return
        else:
            raise AssertionError('Expected no List-Unsubscribe header')

    def get_test_id(self):
        return str(id(self))


class RejectSubjectTest(object):
    def __init__(self, subject):
        self.subject = subject

    def get_envelopes(self):
        return [
            ('-F', 'reject-subject-test@localhost',
             '-f', 'reject-subject-test@localhost',
             '-T', 'admin@fredagscafeen.dk',
             '-s', self.subject,
             '-I', 'Subject', self.subject,
             '-I', 'X-test-id', self.get_test_id())
        ]

    def check_envelopes(self, envelopes):
        if envelopes:
            for e in envelopes:
                subject = e.message.subject
                print(subject)
                print(subject.encode())
            raise AssertionError('Subject %r not rejected' % (self.subject,))

    def get_test_id(self):
        return str(id(self))


class RejectHeaderTest(object):
    def __init__(self, field, value):
        self.field = field
        self.value = value

    def get_envelopes(self):
        return [
            ('-F', 'reject-header-test@localhost',
             '-f', 'reject-header-test@localhost',
             '-T', 'admin@fredagscafeen.dk',
             '-s', self.get_test_id(),
             '-I', self.field, self.value,
             '-I', 'X-test-id', self.get_test_id())
        ]

    def check_envelopes(self, envelopes):
        if envelopes:
            for e in envelopes:
                print(e.message.get_all_headers(self.field))
            raise AssertionError('Header %s: %r not rejected' %
                                 (self.field, self.value))

    def get_test_id(self):
        return str(id(self))


class ErroneousSubjectTest(object):
    def __init__(self, subject):
        self.subject = subject

    def get_envelopes(self):
        return [
            ('-F', 'subject-test@localhost',
             '-f', 'subject-test@localhost',
             '-T', 'form@fredagscafeen.dk',
             '-s', self.subject,
             '-I', 'X-test-id', self.get_test_id())
        ]

    def check_envelopes(self, envelopes):
        if not envelopes:
            raise AssertionError(
                "No envelopes for test id %r" % self.get_test_id())

    def get_test_id(self):
        return str(id(self))


class NoSubjectTest(object):
    def get_envelopes(self):
        return [
            ('-F', 'no-subject-test@localhost',
             '-f', 'no-subject-test@localhost',
             '-T', 'form@fredagscafeen.dk',
             '-I', 'X-test-id', self.get_test_id())
        ]

    def check_envelopes(self, envelopes):
        if not envelopes:
            raise AssertionError(
                "No envelopes for test id %r" % self.get_test_id())

    def get_test_id(self):
        return str(id(self))


class ListHeaderTest(object):
    def get_envelopes(self):
        return [
            ('-F', 'list-header-test@localhost',
             '-f', 'list-header-test@localhost',
             '-T', 'form+best@fredagscafeen.dk',
             '-I', 'X-test-id', self.get_test_id())
        ]

    def check_envelopes(self, envelopes):
        if not envelopes:
            raise AssertionError(
                "No envelopes for test id %r" % self.get_test_id())
        e1, e2 = envelopes
        m1, m2 = e1.message, e2.message

        headers = 'Sender List-Id List-Unsubscribe List-Help List-Subscribe'
        for h in headers.split():
            try:
                v1 = m1.get_unique_header(h)
                v2 = m2.get_unique_header(h)
            except KeyError as e:
                raise AssertionError('No %s in message' % h) from e
            assert ('bestfu' in v1.lower()) == ('bestfu' in v2.lower())

    def get_test_id(self):
        return str(id(self))


class ToHeaderTest(object):
    def __init__(self, to_addr):
        self.to_addr = to_addr

    def get_envelopes(self):
        return [
            ('-F', 'to-header-test@localhost',
             '-f', 'to-header-test@localhost',
             '-T', 'form@fredagscafeen.dk',
             '-I', 'To', self.to_addr,
             '-I', 'X-test-id', self.get_test_id())
        ]

    def check_envelopes(self, envelopes):
        if not envelopes:
            raise AssertionError(
                "No envelopes for test id %r" % self.get_test_id())

    def get_test_id(self):
        return str(id(self))


class ReferencesHeaderTest(object):
    def get_envelopes(self):
        return [
            ('-F', 'references-header-test@localhost',
             '-f', 'references-header-test@localhost',
             '-T', 'form@fredagscafeen.dk',
             '-I', 'References', '<space test>',
             '-I', 'X-test-id', self.get_test_id())
        ]

    def check_envelopes(self, envelopes):
        if not envelopes:
            raise AssertionError(
                "No envelopes for test id %r" % self.get_test_id())
        e, = envelopes
        v, = e.message.get_all_headers('References')
        if '<spacetest>' not in v:
            raise AssertionError('Did not fix References')

    def get_test_id(self):
        return str(id(self))


def main():
    configure_logging()
    relayer_port = 11110
    dumper_port = 11111
    relayer = DatForwarder('localhost', relayer_port,
                          'localhost', dumper_port)
    # dumper = DumpReceiver('localhost', dumper_port)
    relayer.deliver = deliver_local
    relayer.forward = forward_local
    relayer.store_failed_envelope = store_failed_local
    relayer.start()

    tests = [
        #SameRecipientTest('FORM13', 'FORM2013', 'FORM1314', 'gFORM14'),
        #SameRecipientTest('FORM', 'BEST-CERM-INKA-KASS-nf-PR-SEKR-VC'),
        MultipleRecipientTest('best'),
        MultipleRecipientTest('alle'),
        #MultipleRecipientTest('FU'),
        MultipleRecipientTest('ADMIN'),
        #MultipleRecipientTest('engineering'),
        #MultipleRecipientTest('revy+revyteknik'),
        #MultipleRecipientTest('form+fu'),
        NoSubjectRewriteTest('Test'),
        NoListUnsubscribeTest(),
        # Invalid encoding a; should be skipped by ecre in email.header
        ErroneousSubjectTest('=?UTF-8?a?hello_world?='),
        # Invalid base64 data; email.header raises an exception
        ErroneousSubjectTest('=?UTF-8?b?hello_world?='),
        # Invalid start byte in UTF-8
        ErroneousSubjectTest('=?UTF-8?B?UkVBTCBEaWdpdGFsIGNoYXNpbmcgcGF5bWVudCCjNjkxMC40Nw==?='),
        NoSubjectTest(),
        ListHeaderTest(),
        RejectSubjectTest('=?unknown-8bit?b?VW5k?='),
        RejectSubjectTest('Undelivered Mail Returned to Sender'),
        ToHeaderTest('=?utf8?q?f=C3=B8o=2Cb=C3=A6ar?= <foo@bar>'),
        # The following is disabled since emailtunnel.send can't send this
        # Content-Type.
        # RejectHeaderTest('Content-Type',
        #                  'multipart/report; report-type=delivery-status'),
        ReferencesHeaderTest(),
        #SingleRecipientTest('FUOUE17'),
    ]
    test_envelopes = {
        test.get_test_id(): []
        for test in tests
    }

    for test in tests:
        for envelope in test.get_envelopes():
            envelope = [str(x) for x in envelope]
            envelope += ['--relay', 'localhost:%s' % relayer_port]
            print(repr(envelope))
            emailtunnel.send.main(*envelope, body='Hej')

    logger.debug("Sleep for a bit...")
    time.sleep(1)
    logger.debug("%s envelopes" % len(envelopes))

    for envelope in envelopes:
        try:
            header = envelope.message.get_unique_header('X-test-id')
        except KeyError:
            logger.error("Envelope without X-test-id")
            continue
        test_envelopes[header].append(envelope)

    failures = 0
    for i, test in enumerate(tests):
        for envelope in test_envelopes[test.get_test_id()]:
            received_objects = envelope.message.get_all_headers('Received')
            received = [str(o) for o in received_objects]
            print(repr(received))
        try:
            test_id = test.get_test_id()
            e = test_envelopes[test_id]
            test.check_envelopes(e)
        except AssertionError as e:
            logger.exception("Test %s failed: %s" % (i, e))
            failures += 1
        else:
            logger.info("Test %s succeeded" % i)

    if failures:
        logger.error("%s failures", failures)
    else:
        logger.info("All tests succeeded")

    logger.info("datmail.test finished")
    relayer.stop()


if __name__ == "__main__":
    main()
