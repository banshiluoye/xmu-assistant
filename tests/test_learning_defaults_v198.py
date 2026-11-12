from datetime import datetime, timedelta

from test_learning_ui import window  # noqa: F401
from xmu_rollcall.learning import LearningTask, LOCAL_TZ


def test_default_deadline_hides_expired_but_keeps_undated_and_future(window):
    now = datetime.now(LOCAL_TZ)
    values = [LearningTask(str(i), "course", "课程", "作业", "homework", date)
              for i, date in enumerate(((now-timedelta(days=1)).isoformat(), (now+timedelta(days=1)).isoformat(), ""))]
    window.learning_tasks = {task.key: task for task in values}
    assert window.learning_deadline.currentText() == "未过期"
    assert {task.activity_id for task in window._filtered_learning_tasks()} == {"1", "2"}
    window.learning_deadline.setCurrentText("已逾期")
    assert window._filtered_learning_tasks() == [values[0]]
    window.learning_deadline.setCurrentText("全部截止时间")
    assert len(window._filtered_learning_tasks()) == 3


def test_learning_follows_courseware_and_submitted_uses_signed_color(window):
    assert window.nav_titles.index("学习待办") == window.nav_titles.index("课程课件") + 1
    window._show_page(window.nav_titles.index("学习待办"))
    assert window.learning_table.isVisibleTo(window.pages)
    task = LearningTask("1", "course", "课程", "作业", "homework", status="已提交")
    window.learning_tasks = {task.key: task}
    for mode in ("light", "dark", "light"):
        window._apply_theme(mode)
        cell = window.learning_table.item(0, 4)
        assert cell.foreground().color().name() == window._ui_palette()["status_signed_fg"]
