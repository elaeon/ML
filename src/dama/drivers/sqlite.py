from dama.abc.driver import AbsDriver
from dama.connexions.sqlite import Table
from dama.fmtypes import fmtypes_map
from dama.utils.logger import log_config
from dama.utils.decorators import cache
from dama.utils.core import Chunks, Shape
from dama.connexions.core import GroupManager
from collections import OrderedDict
import numpy as np
import sqlite3

log = log_config(__name__)


class Sqlite(AbsDriver):
    persistent = True
    ext = 'sqlite3'
    insert_by_rows = True

    def __getitem__(self, item):
        return self.absconn[item]

    def __setitem__(self, key, value):
        self.absconn[key] = value

    def __contains__(self, item):
        return self.exists()

    def open(self):
        self.conn = sqlite3.connect(self.url, check_same_thread=False)
        self.attrs = {}
        if self.mode == "w":
            self.destroy()
        return self

    def close(self):
        self.conn.close()
        self.attrs = None

    def manager(self, chunks: Chunks):
        # self.chunksize = chunks
        groups = [(group, self[group]) for group in self.groups]
        return GroupManager.convert(groups, chunks=chunks)

    @property
    def absconn(self):
        return Table(self.conn, self.dtypes, name= self.login.table)

    def exists(self) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (self.login.table, ))
        result = cur.fetchone()
        return result is not None

    def destroy(self):
        cur = self.conn.cursor()
        try:
            cur.execute("DROP TABLE {name}".format(name= self.login.table))
        except sqlite3.ProgrammingError as e:
            log.debug(e)
        except sqlite3.OperationalError as e:
            log.error(e)
        self.conn.commit()

    @property
    @cache
    def dtypes(self) -> np.dtype:
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info('{}')".format(self.login.table))
        dtypes = OrderedDict()
        types = {"text": np.dtype("object"), "integer": np.dtype("int"),
                 "float": np.dtype("float"), "boolean": np.dtype("bool"),
                 "timestamp": np.dtype('datetime64[ns]')}

        for column in cur.fetchall():
            dtypes[column[1]] = types.get(column[2].lower(), np.dtype("object"))

        if "id" in dtypes:
            del dtypes["id"]

        cur.close()
        if len(dtypes) > 0:
            return np.dtype(list(dtypes.items()))

    @property
    def groups(self) -> tuple:
        return self.absconn.groups

    def set_schema(self, dtypes: np.dtype, idx: list = None, unique_key: list = None):
        if not self.exists():
            columns_types = ["id INTEGER PRIMARY KEY"]
            if unique_key is not None:
                one_col_unique_key = [column for column in unique_key if isinstance(column, str)]
                more_col_unique_key = [columns for columns in unique_key if isinstance(columns, list)]
            else:
                one_col_unique_key = []
                more_col_unique_key = []
            for group, (dtype, _) in dtypes.fields.items():
                fmtype = fmtypes_map[dtype]
                if group in one_col_unique_key:
                    columns_types.append("{col} {type} UNIQUE".format(col=group, type=fmtype.db_type))
                else:
                    columns_types.append("{col} {type}".format(col=group, type=fmtype.db_type))
            if len(more_col_unique_key) > 0:
                for key in more_col_unique_key:
                    columns_types.append("unique ({})".format(",".join(key)))
            cols = "("+", ".join(columns_types)+")"
            cur = self.conn.cursor()
            cur.execute("""
                CREATE TABLE {name}
                {columns};
            """.format(name=self.login.table, columns=cols))
            if isinstance(idx, list):
                for index in idx:
                    if isinstance(index, tuple):
                        index_columns = ",".join(index)
                        index_name = "_".join(index)
                    else:
                        index_columns = index
                        index_name = index
                    index_q = "CREATE INDEX {i_name}_{name}_index ON {name} ({i_columns})".format(
                        name=self.login.table, i_name=index_name, i_columns=index_columns)
                    cur.execute(index_q)
            self.conn.commit()
            cur.close()

    def set_data_shape(self, shape):
        pass

    def spaces(self) -> list:
        return ["data", "metadata"]

    def cast(self, value):
        return value

    @property
    def shape(self) -> Shape:
        return self.absconn.shape
