
import datmail.config as config


def extract_original_sender(mailfrom):
    """
    Decode SRS-rewritten senders like:
        SRS0=HASH=TTL=orig-domain=orig-local@forwarder
    into orig-local@orig-domain; if not an SRS form, return the input.
    Surrounding angle brackets are tolerated.
    """
    try:
        if not isinstance(mailfrom, str):
            return mailfrom
        # Strip surrounding angle brackets if present
        m = mailfrom.strip()
        if m.startswith("<") and m.endswith(">"):
            m = m[1:-1].strip()
        # Split local part and domain
        if "@" not in m:
            return mailfrom
        local, domain = m.rsplit("@", 1)
        # If local part looks like SRS, try to recover original
        if local.upper().startswith("SRS"):
            parts = local.split("=")
            # Expect at least: SRS*, HASH, TTL, orig-domain, orig-local
            if len(parts) >= 3:
                orig_local = parts[-1]
                orig_domain = parts[-2]
                return "%s@%s" % (orig_local, orig_domain)
    except Exception:
        # On any failure, fall back to the original string
        pass
    return mailfrom

def get_dsn_redirect_recipient(envelope):
    """
    Determine the recipient for DSN reports based on the envelope's message headers.
    If the message has a Content-Type indicating it's a delivery status report, or if the subject indicates a delivery status and the mailfrom is "<>", return the configured DSN recipient.
    Otherwise, return None.
    """
    try:
        content_type = envelope.message.get_unique_header("Content-Type")
    except KeyError:
        content_type = ""

    ctype_report = content_type.startswith("multipart/report")
    ctype_delivery = "report-type=delivery-status" in content_type
    if ctype_report and ctype_delivery:
        return config.DSN_RECIPIENT

    subject_str = str(envelope.message.subject)
    delivery_status_subject = (
        "Delayed Mail" in subject_str
        or "Undelivered Mail Returned to Sender" in subject_str
    )
    if envelope.mailfrom == "<>" and delivery_status_subject:
        return config.DSN_RECIPIENT
    
    return None