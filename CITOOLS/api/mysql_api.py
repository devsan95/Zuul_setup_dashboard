import yaml
import mysql.connector


def init_from_yaml(yaml_path, server_name):
    """
    Init database instance from yaml config file
    :param ymal_path: path of yaml file
    :type ymal_path: basestring
    :param server_name: server name of mysql database
    :type server_name: basestring
    :return: MysqlConnector instance
    """
    with open(yaml_path) as yaml_file:
        obj = yaml.load(yaml_file)
        server = obj[server_name]
        host = server['host']
        user = server['user']
        passwd = server['passwd']
    return MysqlConnector(host=host, user=user, passwd=passwd)


class MysqlConnector(object):

    def __init__(self, host, user, passwd, database=None):
        """
        init method
        :param host: mysql host address
        :type host: basestring
        :param user: database username
        :type user: basestring
        :param passwd: database password
        :type passwd: basestring
        :param database: database name
        :type database: basestring
        """
        self.host = host
        self.user = user
        self.passwd = passwd
        self.database = database
        self.mydb = None
        self.init_server()

    def init_server(self):
        """
        Init mysql server connection
        :return:
        """
        self.mydb = mysql.connector.connect(
            host=self.host,
            user=self.user,
            passwd=self.passwd,
            database=self.database
        ) if self.database else mysql.connector.connect(
            host=self.host,
            user=self.user,
            passwd=self.passwd
        )

    def init_database(self, database):
        """
        Re init mysql database connection to specific database
        :param database: database name
        :type database: basestring
        :return:
        """
        self.database = database
        self.init_server()

    def executor(self, sql, val=None, commit=False, output=False):
        """
        Execute
        :param sql: sql command
        :type sql: basestring
        :param val: value for data insert
        :type val: tuple
        :param commit: commit to database or not
        :type commit: bool
        :param output: return sql output message or not
        :type output: bool
        :return:
        """
        mycursor = self.mydb.cursor()
        print("Executing SQL command: {0}".format(sql))
        if val:
            print("Value: {0}".format(val))
        mycursor.execute(sql, val)
        if commit:
            self.mydb.commit()
        if output:
            return mycursor.fetchall()
        return None

    def insert_info(self, table, values):
        """
        Insert data in to table of database
        :param table: table name
        :type table: basestring
        :param values: values of each columns
        :type values: dict
        :return:
        """
        columns = values.keys()
        sql = "INSERT INTO {table} ({column}) VALUE ({extend})".format(
            table=table,
            column=','.join(columns),
            extend=','.join(['"{0}"'.format(str(values[column])) for column in columns])
        )
        self.executor(sql, commit=True)

    def update_info(self, table, replacements, conditions):
        """
        update value of mysql database table
        :param table: table name
        :type table: basestring
        :param replacements: which values needed to updated to
        :type replacements: dict
        :param conditions: conditon for which row need to be updated
        :type conditions: dict
        :return:
        """
        sql = "UPDATE {table} SET {replacement} WHERE {conditions}".format(
            table=table,
            replacement=', '.join(["{key} = '{value}'".format(key=key, value=value)
                                  for key, value in replacements.items()]),
            conditions='AND '.join(["{name} = '{condition}'".format(name=name, condition=condition)
                                    for name, condition in conditions.items()])
        )
        self.executor(sql, commit=True)
