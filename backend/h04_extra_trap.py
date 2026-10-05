from order_skew import commit_and_latest_split, list_order_sql, newest_first


def decorate_list(rows):
    return newest_first(rows)


def order_clause() -> str:
    return list_order_sql()


def split_armed() -> bool:
    return commit_and_latest_split()


def expose_list(rows: list) -> list:
    return decorate_list(rows)
