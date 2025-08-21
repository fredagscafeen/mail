import re
from collections import namedtuple

from emailtunnel import InvalidRecipient

import datmail.database
from datmail.config import ADMINS

GroupAliasBase = namedtuple("GroupAlias", "name")


class GroupAlias(GroupAliasBase):
    def __str__(self):
        return "%s" % (self.name)


def get_admin_emails():
    """Resolve the group "admin" or fallback if the database is unavailable.

    The default set of admins is set in the datmail.database module.
    """

    email_addresses = []
    try:
        db = datmail.database.Database()
        email_addresses = db.get_admin_emails()
    except:
        pass

    if not email_addresses:
        email_addresses = list(ADMINS)

    return email_addresses


def translate_recipient(name, list_ids=False):
    """Translate recipient `name`.

    >>> translate_recipient("best")
    ["anders@bruunseverinsen.dk", ...]
    """

    db = datmail.database.Database()
    recipient_ids, origin = parse_recipient(name.lower(), db)
    assert isinstance(recipient_ids, list) and isinstance(origin, list)
    assert len(recipient_ids) == len(origin)
    email_addresses = db.get_email_addresses(recipient_ids)
    if list_ids:
        return email_addresses, dict(zip(email_addresses, origin))
    else:
        return email_addresses


def parse_recipient(recipient, db):
    """
    Evaluate each address which is divided by + and -.
    Collects the resulting sets of not matched and the set of spam addresses.
    And return the set of person indexes that are to receive the email.
    """

    personIdOps = []
    invalid_recipients = []
    for sign, name in re.findall(r"([+-]?)([^+-]+)", recipient):
        try:
            personIds, source = parse_alias(name, db)
            personIdOps.append((sign or "+", personIds, source))
        except InvalidRecipient as e:
            invalid_recipients.append(e.args[0])

    if invalid_recipients:
        raise InvalidRecipient(invalid_recipients)

    recipient_ids = set()
    origin = {}
    for sign, personIds, source in personIdOps:
        if sign == "+":  # union
            recipient_ids = recipient_ids.union(personIds)
            for p in personIds:
                origin[p] = source
        else:  # minus
            recipient_ids = recipient_ids.difference(personIds)
            for p in personIds:
                origin.pop(p, None)

    recipient_ids = sorted(recipient_ids)
    if not recipient_ids:
        raise InvalidRecipient(recipient)
    return recipient_ids, [origin[r] for r in recipient_ids]


def parse_alias_group(alias, db):
    mailinglists = db.get_mailinglists()
    for id, name in mailinglists:
        if name == alias:

            def f():
                return db.get_mailinglist_members(id)

            return f, GroupAlias(alias)
    return None, None


def parse_alias(alias, db):
    """
    Evaluates the alias, returning a non-empty list of person IDs.
    Raise exception if a spam or no match email.
    """

    # Try these functions until one matches
    matchers = [
        parse_alias_group,
    ]

    for f in matchers:
        match, canonical = f(alias, db)
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
