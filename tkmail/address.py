import re

from emailtunnel import InvalidRecipient
from tkmail.database import Database
from tkmail.config import ADMINS


def get_admin_emails():
    """Resolve the group "admin" or fallback if the database is unavailable.

    The default set of admins is set in the tkmail.database module.
    """

    email_addresses = []
    try:
        db = Database()
        email_addresses = db.get_admin_emails()
    except:
        pass

    if not email_addresses:
        email_addresses = list(ADMINS)

    return email_addresses


def translate_recipient(year, name):
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

    db = Database()
    name = name.replace('$', 'S')  # KA$$ -> KASS hack
    recipient_ids = parse_recipient(name.upper(), db, year)
    email_addresses = db.get_email_addresses(recipient_ids)
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
            personIds = parse_alias(name, db, current_period)
            personIdOps.append((sign or '+', personIds))
        except InvalidRecipient as e:
            invalid_recipients.append(e.args[0])

    if invalid_recipients:
        raise InvalidRecipient(invalid_recipients)

    recipient_ids = set()
    for sign, personIds in personIdOps:
        if sign == '+':  # union
            recipient_ids = recipient_ids.union(personIds)
        else:  # minus
            recipient_ids = recipient_ids.difference(personIds)

    return recipient_ids


def parse_alias(alias, db, current_period):
    """
    Evaluates the alias, returning a non-empty list of person IDs.
    Raise exception if a spam or no match email.
    """

    anciprefix = r"(?P<pre>(?:[KGBOT][KGBOT0-9]*)?)"
    ancipostfix = r"(?P<post>(?:[0-9]{2}|[0-9]{4})?)"
    try:
        groups = db.get_groups()
        matches = []
        for row in groups:
            groupId, groupRegexp, relativ, groupType = row
            groupId = int(groupId)
            if relativ == 1:  # Relativ = true
                regexp = (r'^%s(?P<name>%s)%s$'
                          % (anciprefix, groupRegexp, ancipostfix))
            else:
                regexp = '^(?P<name>%s)$' % groupRegexp
            result = re.match(regexp, alias)
            if result:
                matches.append((groupId, groupType, result))

        if not matches:
            raise InvalidRecipient(alias)

        if len(matches) > 1:
            raise ValueError("The alias %r matches more than one group"
                             % alias)

        groupId, groupType, result = matches[0]

        if groupType == 0:  # Group, without aging
            personIds = db.get_group_members(groupId)
        elif groupType == 1:  # Group with aging
            period = get_period(
                result.group("pre"),
                result.group("post"),
                current_period)
            grad = current_period - period
            personIds = db.get_grad_group_members(groupId, grad)
        elif groupType == 2:  # Titel, with/without aging
            period = get_period(
                result.group("pre"),
                result.group("post"),
                current_period)
            grad = current_period - period
            personIds = db.get_user_by_title(result.group('name'), grad)
        elif groupType == 3:  # Direct user
            personIds = db.get_user_by_id(result.group('name')[6:])
        elif groupType == 4:  # BESTFU hack
            period = get_period(
                result.group("pre"),
                result.group("post"),
                current_period)
            grad = current_period - period
            personIds = (
                db.get_grad_group_members(groupId + 1, grad)
                + db.get_grad_group_members(groupId - 1, grad))
        else:
            raise Exception(
                "Error in table gruppe, type: %s is unknown."
                % groupType)

        if not personIds:
            # No users in the database fit the current alias
            raise InvalidRecipient(alias)

        return personIds

    finally:
        pass


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
