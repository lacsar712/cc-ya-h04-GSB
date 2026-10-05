from h04_extra_trap import decorate_list, split_armed


def client_order(rows):
    """前端不再二次倒置：直接使用服务端返回的顶序。"""
    return decorate_list(rows)


def armed() -> bool:
    return split_armed()
