import re
from collections import namedtuple, defaultdict

from emailtunnel import InvalidRecipient, logger

import datmail.django_api_client
from datmail.config import ADMINS

GroupAliasBase = namedtuple("GroupAlias", "name")


class GroupAlias(GroupAliasBase):
    def __str__(self):
        return "%s" % (self.name)


def get_admin_emails():
    """Resolve the group "admin" or fallback if the django API is unavailable.

    The default set of admins is set in the datmail.config module.
    """

    email_addresses = []
    try:
        api_client = datmail.django_api_client.DjangoAPIClient()
        email_addresses, _ = api_client.get_admin_emails()
    except:
        pass

    if not email_addresses:
        email_addresses = [admin[1] for admin in ADMINS]

    return email_addresses, []


def translate_recipient(name, list_group_origins=False):
    """Translate recipient `name`.

    >>> translate_recipient("best")
    ["anders@bruunseverinsen.dk", ...]
    """

    api_client = datmail.django_api_client.DjangoAPIClient()

    recipient_emails, group_origins = parse_recipient(name.lower(), api_client)
    assert isinstance(recipient_emails, list) and isinstance(group_origins, list)
    assert len(recipient_emails) == len(group_origins)
    if list_group_origins:
        return recipient_emails, dict(zip(recipient_emails, group_origins))
    else:
        return recipient_emails


def parse_recipient(recipient, api_client):
    """
    Evaluate each address which is divided by + and -.
    Collects the resulting sets of not matched and the set of spam addresses.
    And return the set of person indexes that are to receive the email.
    """

    personEmailOps = []
    invalid_recipients = []
    for sign, name in re.findall(r"([+-]?)([^+-]+)", recipient):
        try:
            emailList, groupAlias, listId, isOnlyInternal = parse_alias(name, api_client)
            personEmailOps.append((sign or "+", emailList, groupAlias))
        except InvalidRecipient as e:
            invalid_recipients.append(e.args[0])

    if invalid_recipients:
        raise InvalidRecipient(invalid_recipients)

    # Mapping: email -> groupAlias that included this email
    email_origins = {}
    recipient_emails = set()
    for sign, emailList, groupAlias in personEmailOps:
        for email in emailList:
            if sign == "+":
                recipient_emails.add(email)
                email_origins[email] = groupAlias
            else:                
                email_origins[email] = None
                # If no more groups claim this email, remove it from the recipient set
                if not email_origins[email]:
                    recipient_emails.discard(email)

    recipient_emails = sorted(recipient_emails)
    if not recipient_emails:
        raise InvalidRecipient(recipient)
    return recipient_emails, [email_origins[r] for r in recipient_emails]


def parse_alias_group(alias, api_client):
    list_info = None
    try:
        list_info = api_client.get_mailinglist_info(alias)
    except Exception:
        logger.exception("Error fetching mailing list info for alias %r", alias)
        return None, None, None, None # API error, so not a valid alias
    
    if list_info is None:
        return None, None, None, None # No such alias, so not a valid alias

    members = list_info.get("members")
    if not members:
        return None, None, None, None # No members, so not a valid alias

    email_list = [m.get("email") for m in members if isinstance(m.get("email"), str)]

    return email_list, GroupAlias(alias), list_info.get("id"), list_info.get("isOnlyInternal")


def parse_alias(alias, api_client):
    """
    Evaluates the alias, returning a non-empty list of person IDs.
    Raise exception if a spam or no match email.
    """

    # Try these functions until one matches
    matchers = [
        parse_alias_group,
    ]

    for f in matchers:
        email_list, group_alias, list_id, is_only_internal = f(alias, api_client)
        if email_list is not None:
            break
    else:
        raise InvalidRecipient(alias)

    return email_list, group_alias, list_id, is_only_internal
