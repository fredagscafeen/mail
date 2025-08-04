from datmail.delivery_reports import email_delivery_reports, dump_stats


# prefixes = {}
# postfixes = {}


for errorname, report in email_delivery_reports():
    print(errorname, report.notification)
dump_stats()
