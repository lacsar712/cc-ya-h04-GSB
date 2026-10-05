"""列表与同机最近查询共用的排序约定。

全链路唯一约定：id 越大越新，新的排前（id DESC）。
入队落盘、列表顶序、同机最近查询都以此为准，保证两路一致。
"""


def list_order_sql() -> str:
    return "ORDER BY id DESC"


def newest_first(rows):
    """列表顶序：新的在前。SQL 已按 id DESC 排好，此处不再倒置。"""
    return list(rows)


def commit_and_latest_split() -> bool:
    """入队提交与最近查询不再分离：同一事务提交后两路立即可见。"""
    return False


def same_turbine_pick(rows):
    """rows 按新到旧排列时，最近一条是队首；空则 None，不编造编号。"""
    return rows[0] if rows else None
