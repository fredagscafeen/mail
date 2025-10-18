import psycopg2
import psycopg2.extras

from datmail.config import HOSTNAME, USERNAME, PASSWORD, DATABASE


class Database(object):
    def __init__(self):
        self._conn = psycopg2.connect(
            host=HOSTNAME,
            database=DATABASE,
            user=USERNAME,
            password=PASSWORD,
            port=5432,
        )
        self._cursor = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    def _execute(self, statement, *args):
        if args:
            sql = statement % args
        else:
            sql = statement

        self._cursor.execute(sql)
        self._conn.commit()

    def _fetchall(self, *args, **kwargs):
        column = kwargs.pop("column", None)
        self._execute(*args)
        rows = self._cursor.fetchall()
        if column is not None:
            return [row[column] for row in rows]
        else:
            return list(rows)

    def get_email_addresses(self, id_list):
        id_string = ",".join(str(each) for each in id_list)
        return self._fetchall(
            """
            SELECT "email" FROM "bartenders_bartender"
            WHERE "id" IN (%s)
            AND "email" != ''
            """,
            id_string,
            column=0,
        )

    def get_admin_emails(self):
        return self._fetchall(
            """
            SELECT "email"
            FROM "auth_user"
            WHERE "auth_user".is_superuser = TRUE
            """,
            column=0,
        )

    def get_mailinglists(self):
        return self._fetchall(
            """
            SELECT "id", "name" FROM "mail_mailinglist"
            """
        )

    def get_mailinglist_members(self, id):
        return self._fetchall(
            """
            SELECT "bartender_id" FROM "mail_mailinglist_members"
            WHERE "mailinglist_id" = %s
            """,
            id,
            column=0,
        )
