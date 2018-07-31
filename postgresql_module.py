import psycopg2

class postgresql:
    """
    Class keeping all things related to postgreSQL
    """

    def __init__(self,conn):
        """
        initializing the class with connection parameters and establishing a connection if possible
        """
        self.__conn = conn
        try:
            self.__conn = psycopg2.connect(self.__conn)
        except:
            raise psycopg2.InterfaceError('Could not connect to database!')

    def execute(self,exc,args=None):
        """
        method to execute sql querys via the connection
        """
        self.__exc = exc
        self.__args = args
        self.__cur = self.__conn.cursor()
        try:
            self.__cur.execute(self.__exc,self.__args)
        except:
            raise psycopg2.DatabaseError('Could not execute statement!')
        return self.__cur.fetchall()

    def write(self,exc,values):
        '''
        method to write data to the database
        '''
        self.__exc = exc
        self.__values = values
        self.__cur = self.__conn.cursor()
        try:
            self.__cur.execute(self.__exc,self.__values)
        except:
            raise psycopg2.DatabaseError('Could not write to database!')
        self.__conn.commit()

    ##############################################
    # Deconstruction                             #
    ##############################################
    def closed(self):
        """
        check if the connection is closed
        """
        return bool(self.__conn.closed)

    def close(self):
        """
        close the connection
        """
        if self.__cur:
            self.__cur.close()
        self.__conn.close()

    def __del__(self):
        """
        delete instance of class after connection is closed
        """
        if not self.closed():
            self.close()
