from ansible.plugins.callback import CallbackBase
from datetime import datetime
import json
import os


class CallbackModule(CallbackBase):

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'advanced_html_report'

    def __init__(self):
        super(CallbackModule, self).__init__()

        self.results = {}
        self.task_start_times = {}

    def v2_playbook_on_task_start(self, task, is_conditional):

        task_name = task.get_name()

        self.task_start_times[task_name] = datetime.now()

    def _record_result(self, result, status):

        host = result._host.get_name()

        task_name = result.task_name

        start_time = self.task_start_times.get(task_name)

        end_time = datetime.now()

        duration = 0

        if start_time:

            duration = round(
                (end_time - start_time).total_seconds(),
                2
            )

        if host not in self.results:
            self.results[host] = []

        failed_reason = ""

        if status == "FAILED":

            failed_reason = result._result.get(
                "msg",
                "Unknown Error"
            )

        skip_reason = ""

        if status == "SKIPPED":

            skip_reason = result._result.get(
                "skip_reason",
                ""
            )

        self.results[host].append({

            "task": task_name,

            "status": status,

            "duration": duration,

            "changed": result._result.get(
                "changed",
                False
            ),

            "failed_reason": failed_reason,

            "skip_reason": skip_reason,

            "start_time": str(start_time),

            "end_time": str(end_time)
        })

    def v2_runner_on_ok(self, result):

        self._record_result(
            result,
            "PASSED"
        )

    def v2_runner_on_failed(
        self,
        result,
        ignore_errors=False
    ):

        self._record_result(
            result,
            "FAILED"
        )

    def v2_runner_on_skipped(self, result):

        self._record_result(
            result,
            "SKIPPED"
        )

    def v2_runner_on_unreachable(self, result):

        self._record_result(
            result,
            "UNREACHABLE"
        )

    def v2_playbook_on_stats(self, stats):

        os.makedirs(
            "reports",
            exist_ok=True
        )

        with open(
            "reports/report.json",
            "w"
        ) as f:

            json.dump(
                self.results,
                f,
                indent=4
            )
