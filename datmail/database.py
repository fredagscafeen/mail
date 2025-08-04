import MySQLdb
from datmail.config import HOSTNAME, USERNAME, PASSWORD, DATABASE
import pickle
import base64


class Database(object):
    def __init__(self):
        self._mysql = MySQLdb.connect(host=HOSTNAME, user=USERNAME,
                                      passwd=PASSWORD, db=DATABASE)
        self._cursor = self._mysql.cursor()

    def _execute(self, statement, *args):
        if args:
            sql = statement % args
        else:
            sql = statement

        self._cursor.execute(sql)

    def _fetchall(self, *args, **kwargs):
        column = kwargs.pop('column', None)
        self._execute(*args)
        rows = self._cursor.fetchall()
        if column is not None:
            return [row[column] for row in rows]
        else:
            return list(rows)

    def get_email_addresses(self, id_list):
        # TODO:
        id_string = ','.join(str(each) for each in id_list)
        return self._fetchall("""
            SELECT `email` FROM `idm_profile`
            WHERE `id` IN (%s)
            AND `allow_direct_email` = TRUE
            AND `email` != ""
            """, id_string, column=0)

    def get_admin_emails(self):
        # TODO:
        return self._fetchall("""
            SELECT `idm_profile`.`email`
            FROM `idm_profile`, `idm_group`, `idm_profile_groups`
            WHERE `idm_group`.name = "ADMIN"
            AND `idm_profile_groups`.`group_id`=`idm_group`.`id`
            AND `idm_profile_groups`.`profile_id`= `idm_profile`.`id`
            """, column=0)

    def get_best_members(self, period):
        return self._fetchall("""
            SELECT `bartender_id` FROM `board_members`
            WHERE `period` = '%s'
            """, period, column=0)

    def get_current_best_period(self):
        rows = self._fetchall("""
            SELECT `board_member_period` FROM `bartenders`
        """)
        if len(rows) == 0:
            raise Exception("No current best period found!")
        current = rows[0]
        return current
