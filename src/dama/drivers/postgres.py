from dama.abc.driver import AbsDriver
from dama.groups.postgres import Table
from dama.fmtypes import fmtypes_map
from dama.utils.logger import log_config
from dama.utils.decorators import cache
import numpy as np
import psycopg2

log = log_config(__name__)


class Postgres(AbsDriver):
    persistent = True
    ext = 'sql'
    data_tag = None
    metadata_tag = None

    def __contains__(self, item):
        return self.exists()

    def open(self):
        self.conn = psycopg2.connect(
            "dbname={db_name} user={username}".format(db_name=self.login.resource, username=self.login.username))
        self.conn.autocommit = False
        self.attrs = {}
        if self.mode == "w":
            self.destroy()
        return self

    def close(self):
        self.conn.close()
        self.attrs = None

    @property
    def absgroup(self):
        return Table(self.conn, self.dtypes, name=self.data_tag)

    def exists(self) -> bool:
        cur = self.conn.cursor()
        cur.execute("select exists(select relname from pg_class where relname='{name}')".format(name=self.data_tag))
        return True if cur.fetchone()[0] else False

    def destroy(self):
        cur = self.conn.cursor()
        try:
            cur.execute("DROP TABLE {name}".format(name=self.data_tag))
        except psycopg2.ProgrammingError as e:
            log.debug(e)
        self.conn.commit()

    @property
    @cache
    def dtypes(self) -> np.dtype:
        from collections import OrderedDict
        cur = self.conn.cursor()
        query = "SELECT * FROM information_schema.columns WHERE table_name=%(table_name)s ORDER BY ordinal_position"
        cur.execute(query, {"table_name": self.data_tag})
        dtypes = OrderedDict()
        types = {"text": np.dtype("object"), "integer": np.dtype("int"),
                 "double precision": np.dtype("float"), "boolean": np.dtype("bool"),
                 "timestamp without time zone": np.dtype('datetime64[ns]')}

        for column in cur.fetchall():
            dtypes[column[3]] = types.get(column[7], np.dtype("object"))

        cur.close()
        if "id" in dtypes:
            del dtypes["id"]

        if len(dtypes) > 0:
            return np.dtype(list(dtypes.items()))

    def set_schema(self, dtypes: np.dtype, idx: list = None, unique_key=None):
        idx = None
        if not self.exists():
            columns_types = ["id serial PRIMARY KEY"]
            for group, (dtype, _) in dtypes.fields.items():
                fmtype = fmtypes_map[dtype]
                columns_types.append("{col} {type}".format(col=group, type=fmtype.db_type))
            cols = "("+", ".join(columns_types)+")"
            cur = self.conn.cursor()
            cur.execute("""
                CREATE TABLE {name}
                {columns};
            """.format(name=self.data_tag, columns=cols))
            if isinstance(idx, list):
                for index in idx:
                    if isinstance(index, tuple):
                        index_columns = ",".join(index)
                        index_name = "_".join(index)
                    else:
                        index_columns = index
                        index_name = index
                    index_q = "CREATE INDEX {i_name}_{name}_index ON {name} ({i_columns})".format(
                        name=self.data_tag, i_name=index_name, i_columns=index_columns)
                    cur.execute(index_q)
            self.conn.commit()

    def set_data_shape(self, shape):
        pass

    def insert(self, table_name: str, data):
        table = Table(self.conn, self.dtypes, name=table_name)
        table.insert(data)

    def spaces(self) -> list:
        return ["data", "metadata"]
