from h04_extra_trap import decorate_list, order_clause, split_armed
from order_skew import same_turbine_pick


def test_list_order_is_newest_first():
    # 列表顶序：id DESC，新单置顶，不再沉底
    assert order_clause() == "ORDER BY id DESC"


def test_decorate_list_keeps_newest_first():
    # 服务端已按新到旧排好，装饰层不得再倒置
    assert decorate_list([3, 2, 1]) == [3, 2, 1]


def test_commit_and_latest_not_split():
    # 入队落盘与最近查询同路，入队瞬间两路一致
    assert split_armed() is False


def test_same_turbine_pick_takes_newest_head():
    rows = [{"id": 5, "turbine_code": "W01"}, {"id": 2, "turbine_code": "W01"}]
    assert same_turbine_pick(rows) == {"id": 5, "turbine_code": "W01"}


def test_same_turbine_pick_empty_is_none():
    # 该机尚无单据时返回 None（接口层转 404），不得编造编号
    assert same_turbine_pick([]) is None
