# PerfLab Context

PerfLab describes repeatable model performance experiments and the immutable evidence produced by each execution.

## Language

**Test Plan（测试计划）**:
A saved benchmark configuration together with its start time, repetition policy, and lifecycle state.
_Avoid_: New test, scheduled task, benchmark job

**Run Record（运行记录）**:
One immutable execution produced when a test plan is triggered, whether by its schedule or a manual rerun. A test plan can produce many run records. Deleting a plan does not delete its run records.
_Avoid_: Plan instance, test plan

**Overview（概览）**:
The workspace-wide operational summary across all test plans and their current or latest run records. It highlights what is running, completed, failed, or scheduled next; it does not perform detailed performance analysis.
_Avoid_: Run details, analytics dashboard

**Analysis Dashboard（分析看板）**:
A performance-analysis view that aggregates and compares metrics from multiple run records, normally scoped to one test plan and switchable by metric, provider, model, concurrency, and time range.
_Avoid_: Overview, run record list

**Scenario（场景）**:
One model service combined with one concurrency level inside a run record.
_Avoid_: Task, case

**Pause（暂停）**:
Suspends future scheduled triggers while allowing an already active run record to finish.
_Avoid_: Stop, cancel

**Stop（停止）**:
Disables future scheduled triggers and cancels any active run records belonging to the plan.
_Avoid_: Pause
