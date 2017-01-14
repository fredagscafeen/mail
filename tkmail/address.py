import re
import functools
from collections import namedtuple

from emailtunnel import InvalidRecipient
import tkmail.database
from tkmail.config import ADMINS


GroupAliasBase = namedtuple('GroupAlias', 'name'.split())
PeriodAliasBase = namedtuple('PeriodAlias', 'kind period root'.split())
DirectAliasBase = namedtuple('DirectAlias', 'pk'.split())


class GroupAlias(GroupAliasBase):
    def __str__(self):
        return self.name


class PeriodAlias(PeriodAliasBase):
    def __str__(self):
        return '%s%s' % (self.kind, self.period)


class DirectAlias(DirectAliasBase):
    def __str__(self):
        return 'DIRECTUSER%s' % self.pk


def get_admin_emails():
    """Resolve the group "admin" or fallback if the database is unavailable.

    The default set of admins is set in the tkmail.database module.
    """

    email_addresses = []
    try:
        db = tkmail.database.Database()
        email_addresses = db.get_admin_emails()
    except:
        pass

    if not email_addresses:
        try:
            db = tkmail.database.DatabaseTkfolk()
            email_addresses = db.get_admin_emails()
        except:
            pass

    if not email_addresses:
        email_addresses = list(ADMINS)

    return email_addresses


def translate_recipient(year, name, list_ids=False):
    """Translate recipient `name` in GF year `year`.

    >>> translate_recipient(2010, "K3FORM")
    ["mathiasrav@gmail.com"]

    >>> translate_recipient(2010, "GFORM14")
    ["mathiasrav@gmail.com"]

    >>> translate_recipient(2010, "BEST2013")
    ["mathiasrav@gmail.com", ...]

    >>> translate_recipient(2006, 'FUAA')
    ['sidse...']

    >>> translate_recipient(2011, 'FUIØ')
    ['...@post.au.dk']

    >>> translate_recipient(2011, 'FUIOE')
    ['...@post.au.dk']
    """

    name = name.replace('$', 'S')  # KA$$ -> KASS hack
    db = tkmail.database.Database()
    recipient_ids, origin = parse_recipient(name.upper(), db, year)
    assert isinstance(recipient_ids, list) and isinstance(origin, list)
    assert len(recipient_ids) == len(origin)
    email_addresses = db.get_email_addresses(recipient_ids)
    if list_ids:
        return email_addresses, dict(zip(email_addresses, origin))
    else:
        return email_addresses


def parse_recipient(recipient, db, current_period):
    """
    Evaluate each address which is divided by + and -.
    Collects the resulting sets of not matched and the set of spam addresses.
    And return the set of person indexes that are to receive the email.
    """

    personIdOps = []
    invalid_recipients = []
    for sign, name in re.findall(r'([+-]?)([^+-]+)', recipient):
        try:
            personIds, source = parse_alias(name, db, current_period)
            personIdOps.append((sign or '+', personIds, source))
        except InvalidRecipient as e:
            invalid_recipients.append(e.args[0])

    if invalid_recipients:
        raise InvalidRecipient(invalid_recipients)

    recipient_ids = set()
    origin = {}
    for sign, personIds, source in personIdOps:
        if sign == '+':  # union
            recipient_ids = recipient_ids.union(personIds)
            for p in personIds:
                origin[p] = source
        else:  # minus
            recipient_ids = recipient_ids.difference(personIds)
            for p in personIds:
                origin.pop(p, None)

    recipient_ids = sorted(recipient_ids)
    return recipient_ids, [origin[r] for r in recipient_ids]


def parse_alias_group(alias, db, current_period):
    groups = db.get_groups()
    matches = []
    for groupId, name, groupRegexp in groups:
        groupId = int(groupId)
        regexp = '^(?P<name>%s)$' % groupRegexp
        mo = re.match(regexp, alias)
        if mo:
            # We cannot use a lambda that closes over groupId
            # since the captured groupId would change in the next iteration.
            matches.append(
                (functools.partial(db.get_group_members, groupId),
                 GroupAlias(name)))

    if len(matches) > 1:
        raise ValueError("The alias %r matches more than one group"
                         % alias)

    if matches:
        return matches[0]
    return None, None


def parse_alias_bestfu_group(alias, db, current_period):
    anciprefix = r"(?P<pre>(?:[KGBOT][KGBOT0-9]*)?)"
    ancipostfix = r"(?P<post>(?:[0-9]{2}|[0-9]{4})?)"
    pattern = '^%s(?P<kind>BEST|FU|BESTFU)%s$' % (anciprefix, ancipostfix)
    mo = re.match(pattern, alias)
    if mo is not None:
        period = get_period(
            mo.group("pre"),
            mo.group("post"),
            current_period)
        kind = mo.group('kind')
        if kind == 'BESTFU':
            f = lambda: (db.get_bestfu_members('BEST', period) +
                         db.get_bestfu_members('FU', period))
        else:
            f = lambda: db.get_bestfu_members(kind, period)
        return f, PeriodAlias(kind, period, root=None)
    return None, None


def parse_alias_bestfu_single(alias, db, current_period):
    anciprefix = r"(?P<pre>(?:[KGBOT][KGBOT0-9]*)?)"
    ancipostfix = r"(?P<post>(?:[0-9]{2}|[0-9]{4})?)"
    letter = '[A-Z]|Æ|Ø|Å|AE|OE|AA'
    letter_map = dict(AE='Æ', OE='Ø', AA='Å')
    title_patterns = [
        ('BEST', 'CERM|FORM|INKA|KASS|NF|PR|SEKR|VC'),
        ('FU', '(?P<a>E?FU)(?P<b>%s)(?P<c>%s)' % (letter, letter)),
    ]

    for kind, p in title_patterns:
        pattern = '^%s(?P<root>%s)%s$' % (anciprefix, p, ancipostfix)
        mo = re.match(pattern, alias)
        if mo is not None:
            period = get_period(
                mo.group("pre"),
                mo.group("post"),
                current_period)
            root = mo.group('root')
            if kind == 'FU':
                fu_kind = mo.group('a')
                letter1 = mo.group('b')
                letter2 = mo.group('c')
                assert root == fu_kind + letter1 + letter2
                # Translate AE OE AA
                letter1_int = letter_map.get(letter1, letter1)
                letter2_int = letter_map.get(letter2, letter2)
                root = fu_kind + letter1_int + letter2_int
            source = PeriodAlias(kind, period, root)
            return (lambda: db.get_user_by_title(root, period)), source
    return None, None


def parse_alias_direct_user(alias, db, current_period):
    mo = re.match(r'^DIRECTUSER(\d+)$', alias)
    if mo is not None:
        pk = int(mo.group(1))
        return (lambda: db.get_user_by_id(pk)), DirectAlias(pk)
    return None, None


def parse_alias(alias, db, current_period):
    """
    Evaluates the alias, returning a non-empty list of person IDs.
    Raise exception if a spam or no match email.
    """

    # Try these functions until one matches
    matchers = [
        parse_alias_group,
        parse_alias_bestfu_group,
        parse_alias_bestfu_single,
        parse_alias_direct_user,
    ]

    for f in matchers:
        match, canonical = f(alias, db, current_period)
        if match is not None:
            break
    else:
        raise InvalidRecipient(alias)

    # Perform database lookup according to matched alias
    person_ids = match()
    if not person_ids:
        # No users in the database fit the matched alias
        raise InvalidRecipient(alias)
    return person_ids, canonical


def get_period(prefix, postfix, current_period):
    """
    current_period is the year where the current BEST was elected.
    Assumes current_period <= 2056.
    Returns the corresponding period of prefix, postfix and current_period.
    (Calculates as the person have the prefix in year postfix)
    """

    if not postfix:
        period = current_period
    else:
        if len(postfix) == 4:
            first, second = int(postfix[0:2]), int(postfix[2:4])
            # Note that postfix 1920, 2021 and 2122 are technically ambiguous,
            # but luckily there was no BEST in 1920 and this script hopefully
            # won't live until the year 2122, so they are not actually
            # ambiguous.
            if (first + 1) % 100 == second:
                # There should be exactly one year between the two numbers
                if first > 56:
                    period = 1900 + first
                else:
                    period = 2000 + first
            elif first in (19, 20):
                # 19xx or 20xx
                period = int(postfix)
            else:
                raise InvalidRecipient(postfix)
        elif len(postfix) == 2:
            year = int(postfix[0:2])
            if year > 56:  # 19??
                period = 1900 + year
            else:  # 20??
                period = 2000 + year
        else:
            raise InvalidRecipient(postfix)

    # Now evaluate the prefix:
    prefix_value = dict(K=-1, G=1, B=2, O=3, T=1)
    grad = 0
    for base, exponent in re.findall(r"([KGBOT])([0-9]*)", prefix):
        exponent = int(exponent or 1)
        grad += prefix_value[base] * exponent

    return period - grad
