from unittest import mock

from xmu_rollcall.ui_stall_watchdog import UiStallWatchdog


def test_stall_records_one_stack_until_heartbeat_resumes_without_locals():
    logs = []
    monitor = UiStallWatchdog(writer=logs.append)
    start = monitor.last_beat
    monitor.note("courseware:collapsed")
    private_value = "sensitive-frame-locals-must-not-appear"
    monitor.probe(start + 6)
    monitor.probe(start + 8)
    assert len(logs) == 1
    assert "UI_STALL" in logs[0] and "courseware:collapsed" in logs[0]
    assert private_value not in logs[0]
    with mock.patch("xmu_rollcall.ui_stall_watchdog.time.monotonic", return_value=start + 9):
        monitor.beat()
    monitor.probe(start + 15)
    assert len(logs) == 2


def test_healthy_beats_and_suspend_resume_do_not_report_stall():
    logs = []
    monitor = UiStallWatchdog(writer=logs.append)
    start = monitor.last_beat
    for seconds in (1, 2, 3):
        with mock.patch("xmu_rollcall.ui_stall_watchdog.time.monotonic", return_value=start + seconds):
            monitor.beat()
        monitor.probe(start + seconds + 0.1)
    monitor.probe(start + 100)
    assert not logs


def test_c_watchdog_is_not_rearmed_without_fresh_ui_heartbeat(tmp_path):
    monitor = UiStallWatchdog(writer=lambda _: None)
    start = monitor.last_beat
    turns = iter([False, False, True])
    with mock.patch("xmu_rollcall.ui_stall_watchdog.CONFIG_DIR", tmp_path), \
         mock.patch("xmu_rollcall.ui_stall_watchdog.time.monotonic", side_effect=[start, start + 4, start + 8]), \
         mock.patch.object(monitor.stopped, "wait", side_effect=lambda _: next(turns)), \
         mock.patch("xmu_rollcall.ui_stall_watchdog.faulthandler.dump_traceback_later") as arm, \
         mock.patch("xmu_rollcall.ui_stall_watchdog.faulthandler.cancel_dump_traceback_later") as cancel:
        monitor._run()
    assert arm.call_count == 1
    assert arm.call_args.args == (8.0,)
    assert arm.call_args.kwargs["repeat"] is False
    assert cancel.call_count >= 1
