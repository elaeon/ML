from dama.utils.config import get_settings
from dama.utils.numeric_functions import humanize_bytesize
from dama.exceptions import DataDoesNotFound

settings = get_settings("paths")
settings.update(get_settings("vars"))


def run(args):
    from dama.measures import ListMeasure
    from dama.data.ds import Data
    from dama.drivers.sqlite import Sqlite
    from dama.utils.core import Login, Metadata

    login = Login(table=settings["data_tag"])
    driver = Sqlite(login=login, path=settings["metadata_path"], mode="r")
    if args.info:
        with Data.load(args.hash[0], metadata_driver=driver) as dataset:
            try:
                dataset.info()
            except DataDoesNotFound:
                print("Resource does not exists.")
    elif args.rm:
        from dama.data.it import Iterator
        with Metadata(driver) as metadata:
            if "all" in args.hash:
                data = metadata.data()[["name", "hash", "is_valid"]]
                data = data[data["is_valid"] == True]
                it = Iterator(data)
                to_delete = []
                for row in it:
                    df = row.to_df()
                    if df.values[0][0] is None:
                        continue
                    print(df.values)
                    to_delete.append(df["hash"].values[0])
                print(len(to_delete))
            else:
                metadata.invalid(args.hash[0])
        print("Done.")
    elif args.sts:
        with Data.load(args.hash[0], metadata_driver=driver) as dataset:
            print(dataset.stadistics())
    else:
        from dama.utils.miscellaneous import str2slice
        import sqlite3
        headers = ["hash", "name", "driver", "group_name", "size", "num_groups", "datetime UTC"]
        page = str2slice(args.items)
        if args.exclude_cols is not None:
            headers = ListMeasure.exclude_columns(headers, args.exclude_cols)
        with Metadata(driver) as metadata:
            try:
                query = "SELECT COUNT(*) FROM {} WHERE is_valid=?".format(login.table)
                total = metadata.query(query, (True, ))
            except sqlite3.OperationalError as e:
                print(e)
            else:
                data = metadata.data()
                if args.group_name is None and args.driver is None:
                    data = data[data["is_valid"] == True][page]
                elif args.group_name is not None and args.driver is None:
                    data = data[(data["is_valid"] == True) & (data["group_name"] == args.group_name)][page]
                elif args.group_name is None and args.driver is not None:
                    data = data[(data["is_valid"] == True) & (data["driver_name"] == args.driver)][page]
                else:
                    data = data[(data["is_valid"] == True) & (data["group_name"] == args.group_name) &\
                                (data["driver_name"] == args.driver)][page]
                df = data.to_df()
                df.rename(columns={"timestamp": "datetime UTC", "driver_name": "driver"}, inplace=True)
                df["size"] = df["size"].apply(humanize_bytesize)
                print("Using metadata {}".format(metadata.driver.url))
                print("Total {} / {}".format(len(df), total[0][0]))
                list_measure = ListMeasure(headers=headers, measures=df[headers].values)
                print(list_measure.to_tabulate())
