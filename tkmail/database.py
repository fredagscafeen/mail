# import pkg_resources ##required on my setup to use MySQLdb
# pkg_resources.require("MySQL-python")  ##required on my setup to use MySQLdb
# import MySQLdb as mdb
import mysql.connector
from tkmail.config import HOSTNAME, USERNAME, PASSWORD, DATABASE


def fix_at_escapes(addresses):
    return [addy.strip().replace('&#064;', '@') for addy in addresses]


class DatabaseTkfolk(object):
    tkfolk_schema = """
        id      int(11)      NO   None  primary, auto_increment
        navn    varchar(50)  YES  None
        email   varchar(50)  YES  None
        accepteremail
                char(3)      YES  ja
        accepterdirektemail
                char(3)      NO   Ja
        gade    varchar(50)  YES  None
        husnr   varchar(15)  YES  None
        postnr  varchar(10)  YES  None
        postby  varchar(25)  YES  None
        land    varchar(50)  YES  None
        gone    char(3)      NO   nej
        tlf     varchar(20)  YES  None
        note    text         YES  None
        """

    def __init__(self):
        if HOSTNAME not in ('127.0.0.1', 'localhost'):
            raise ValueError('Non-local hostname not supported by ' +
                             'mysql.connector')
        self._mysql = mysql.connector.Connect(
            user=USERNAME, password=PASSWORD, database=DATABASE)

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

    def get_people(self, **kwargs):
        column_list = ("id navn email accepteremail accepterdirektemail "
                       "gade husnr postnr postby land gone tlf note".split())
        columns = ', '.join("`%s`" % column for column in column_list)

        clauses = []
        for k, v in kwargs.items():
            if k == 'id__in':
                id_string = ','.join('"%s"' % each for each in v)
                clauses.append(('`id` IN %s', id_string))
            else:
                raise TypeError('unknown kwarg "%s"' % k)

        if clauses:
            where_clause = ' AND '.join(expr for expr, param in clauses)
        else:
            where_clause = "1"

        format_args = [param for expr, param in clauses]

        rows = self._fetchall(
            "SELECT %s FROM `tkfolk` WHERE %s"
            % (columns, where_clause),
            *format_args)

        return [dict(zip(column_list, row)) for row in rows]

    def get_email_addresses(self, id_list):
        id_string = ','.join(str(each) for each in id_list)
        return fix_at_escapes(self._fetchall("""
            SELECT `email` FROM `tkfolk`
            WHERE `id` IN (%s)
            AND `accepterdirektemail`='Ja'
            """, id_string, column=0))

    def get_admin_emails(self):
        return fix_at_escapes(self._fetchall("""
            SELECT `tkfolk`.`email`
            FROM `tkfolk`, `grupper`,`gruppemedlemmer`
            WHERE `grupper`.`navn`='admin'
            AND `gruppemedlemmer`.`gruppeid`=`grupper`.`id`
            AND `gruppemedlemmer`.`personid`= `tkfolk`.`id`
            """, column=0))

    def get_groups(self):
        """Get the groups.

        >>> db = Database()
        >>> sorted(db.get_groups())
        [(3, 'FUCK', 0, 0), (4, 'HEST', 0, 0), (5, 'KET', 0, 0),
        (6, 'SPIRIL(?:L?EN)?', 0, 0), (7, '(?:FORM)?JUNTA(?:EN)?', 0, 0),
        (8, 'N(?:AEST)?FORMATION(?:EN)?', 0, 0),
        (9, '(?:CERM)?LAUG(?:ET)?', 0, 0), (10, 'REVY(?:EN)?', 0, 0),
        (11, 'J50', 0, 0), (12, '(ENGINEERING|TK-?E)', 0, 0),
        (13, 'ADMIN(?:ISTRATOR(?:ERNE|EN)?)?', 0, 0),
        (21, 'WEB(?:MASTER(?:EN|NE)?)?', 0, 0), (22, 'REVYBAND(?:ET)?', 0, 0),
        (23, 'REVYCREW', 0, 0), (24, 'REVYSPAM', 0, 0),
        (25, 'REVIS(ION|OR)', 0, 0), (27, 'G*S?SR', 0, 0),
        (28, 'REVYTEKNIK', 0, 0), (30, 'FILF', 0, 0), (110, 'BEST', 1, 1),
        (111, 'BESTFU', 1, 4), (112, 'FU', 1, 1),
        (113, 'FU(?!CK|LD)[A-Z]{2,4}', 1, 2), (114, 'EFU[A-Z]{2,4}', 1, 2),
        (115, 'FORM', 1, 2), (116, 'NF', 1, 2), (117, 'CERM', 1, 2),
        (118, 'VC', 1, 2), (119, 'SEKR', 1, 2), (120, 'PR', 1, 2),
        (121, 'KASS', 1, 2), (122, 'USERID[0-9]+', 0, 3),
        (126, '(8|OTT(END)?E)', 0, 0), (128, 'J60', 0, 0),
        (129, 'J60KOOR', 0, 0), (130, 'INKA', 1, 2), (131, 'HAPPENING', 0, 0),
        (132, 'TKIT', 0, 0), (134, '(TK)?SY', 0, 0), (136, 'ABEN', 0, 0),
        (137, 'J60REVY', 0, 0)]
        """

        return self._fetchall("""
            SELECT `id`,`regexp`,`relativ`,`type` FROM grupper
            """)

    def get_group_members(self, group_id):
        return self._fetchall("""
            SELECT `personid` FROM `gruppemedlemmer`
            WHERE `gruppeid`='%s'
            """, group_id, column=0)

    def get_grad_group_members(self, group_id, grad):
        return self._fetchall("""
            SELECT `personid` FROM `gradgruppemedlemmer`
            WHERE `gruppeid`='%s' AND `grad`='%s'
            """, group_id, grad, column=0)

    def get_user_by_title(self, title, grad):
        return self._fetchall("""
            SELECT `personid` FROM `titler`
            WHERE `inttitel`='%s' AND `grad`='%s'
            """, title, grad, column=0)

    def get_user_by_id(self, user_id):
        return self._fetchall("""
            SELECT `id` FROM `tkfolk`
            WHERE `id`='%s'
            """, user_id, column=0)

    def get_all_best(self):
        """Get all BEST members.

        >>> db = Database()
        >>> db.get_all_best()
        [('Martin Sand Nielsen', 'FORM', 1),
        ('Jacob Albæk Schnedler ', 'NF', 2),
        ('Henrik Lund Mortensen ', 'INKA', 3),
        ('Mathias Jaquet Mavraganis', 'KA$$', 4),
        ('Jonas Kielsholm', 'CERM', 5),
        ('Peter Lystlund Matzen', 'VC', 6),
        ('Alexandra Fabricius Porsgaard', 'PR', 7),
        ('Camilla Ulbæk Pedersen', 'SEKR', 8)]
        """

        return self._fetchall("""
            SELECT tkfolk.navn, best.titel, best.sortid
            FROM titler, best, tkfolk
            WHERE titler.grad = 0
            AND best.orgtitel = titler.orgtitel
            AND titler.personid = tkfolk.id
            ORDER BY `best`.`sortid` ASC
        """)
