import { AlertTriangle, ArrowRight, CalendarClock, Clock3, PlayCircle } from "lucide-react";
import { tr, type Language } from "../i18n";
import type { Run, TestPlan } from "../types";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

function formatTime(value: string, language: Language) {
  return new Intl.DateTimeFormat(language, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function Status({ value, language }: { value: string; language: Language }) {
  const label: Record<string, string> = { queued: "等待中", running: "运行中", active: "已启动", paused: "已暂停", stopped: "已停止", completed: "已完成", error: "异常", failed: "失败", cancelled: "已取消" };
  const style = value === "active" ? "running" : value === "error" ? "failed" : value;
  return <span className={`status status-${style}`}><i />{tr(language, label[value] ?? value)}</span>;
}

export function Overview({ plans, runs, language, onOpenRun, onOpenPlans, onOpenDashboard }: {
  plans: TestPlan[];
  runs: Run[];
  language: Language;
  onOpenRun: (run: Run) => void;
  onOpenPlans: () => void;
  onOpenDashboard: () => void;
}) {
  const t = (value: string) => tr(language, value);
  const now = Date.now();
  const since = now - 24 * 60 * 60 * 1000;
  const activePlans = plans.filter((plan) => plan.status === "active");
  const liveRuns = runs.filter((run) => run.status === "queued" || run.status === "running");
  const completedToday = runs.filter((run) => run.status === "completed" && new Date(run.updated_at).getTime() >= since);
  const failedToday = runs.filter((run) => run.status === "failed" && new Date(run.updated_at).getTime() >= since);
  const upcoming = plans.filter((plan) => plan.status === "active" && plan.next_run_at).sort((a, b) => new Date(a.next_run_at!).getTime() - new Date(b.next_run_at!).getTime()).slice(0, 5);
  const attention = [
    ...plans.filter((plan) => plan.schedule_error).map((plan) => ({ id: `plan-${plan.id}`, title: plan.name, detail: plan.schedule_error!, kind: t("调度异常"), run: undefined as Run | undefined })),
    ...runs.filter((run) => run.status === "failed").slice(0, 5).map((run) => ({ id: `run-${run.id}`, title: run.name, detail: run.error || t("运行失败，请检查场景详情"), kind: t("运行失败"), run })),
  ].slice(0, 5);
  const recent = runs.filter((run) => TERMINAL.has(run.status)).slice(0, 6);

  return <div className="overview-page">
    <section className="metric-grid overview-metrics" aria-label={t("工作区运行态势")}>
      <article><span>{t("活跃测试计划")}</span><strong>{activePlans.length}</strong><small>{plans.length} {t("个计划")}</small></article>
      <article><span>{t("正在运行")}</span><strong>{liveRuns.length}</strong><small>{t("等待中与运行中的记录")}</small></article>
      <article><span>{t("近 24 小时已完成")}</span><strong>{completedToday.length}</strong><small>{t("独立运行记录")}</small></article>
      <article><span>{t("近 24 小时失败")}</span><strong className={failedToday.length ? "metric-danger" : ""}>{failedToday.length}</strong><small>{failedToday.length ? t("需要检查失败原因") : t("当前没有失败记录")}</small></article>
    </section>

    <div className="overview-grid">
      <section className="panel overview-panel overview-live">
        <div className="panel-head"><div><p className="eyebrow">LIVE RUNS</p><h2>{t("正在运行")}</h2><p>{t("查看当前执行进度和正在处理的场景。")}</p></div><PlayCircle aria-hidden="true" /></div>
        <div className="overview-list">{liveRuns.map((run) => {
          const progress = run.total_scenarios ? run.completed_scenarios / run.total_scenarios * 100 : 0;
          const active = run.scenarios.find((scenario) => scenario.status === "running");
          return <button className="overview-run-row" key={run.id} onClick={() => onOpenRun(run)}>
            <span><strong>{run.name}</strong><small>{active ? `${active.provider_name || active.provider} · c=${active.concurrency}` : run.benchmark}</small></span>
            <span className="overview-run-progress"><i style={{ width: `${progress}%` }} /></span>
            <span className="overview-run-count">{run.completed_scenarios}/{run.total_scenarios}</span>
            <ArrowRight aria-hidden="true" />
          </button>;
        })}{!liveRuns.length && <div className="overview-empty">{t("当前没有正在执行的运行记录")}</div>}</div>
      </section>

      <section className="panel overview-panel">
        <div className="panel-head"><div><p className="eyebrow">UPCOMING</p><h2>{t("即将运行")}</h2><p>{t("按下一次触发时间排序。")}</p></div><CalendarClock aria-hidden="true" /></div>
        <div className="overview-list">{upcoming.map((plan) => <button className="overview-list-row" key={plan.id} onClick={onOpenPlans}>
          <span><strong>{plan.name}</strong><small>{plan.benchmark}</small></span><time>{formatTime(plan.next_run_at!, language)}</time><ArrowRight aria-hidden="true" />
        </button>)}{!upcoming.length && <div className="overview-empty">{t("暂无即将触发的测试计划")}</div>}</div>
      </section>

      <section className="panel overview-panel">
        <div className="panel-head"><div><p className="eyebrow">ATTENTION</p><h2>{t("需要关注")}</h2><p>{t("调度异常与最近失败的运行。")}</p></div><AlertTriangle aria-hidden="true" /></div>
        <div className="overview-list">{attention.map((item) => <button className="overview-list-row attention" key={item.id} onClick={() => item.run ? onOpenRun(item.run) : onOpenPlans()}>
          <span><strong>{item.title}</strong><small>{item.detail}</small></span><em>{item.kind}</em><ArrowRight aria-hidden="true" />
        </button>)}{!attention.length && <div className="overview-empty success-empty">{t("当前没有需要关注的异常")}</div>}</div>
      </section>

      <section className="panel overview-panel">
        <div className="panel-head"><div><p className="eyebrow">RECENT ACTIVITY</p><h2>{t("最近活动")}</h2><p>{t("最近结束的运行记录。")}</p></div><Clock3 aria-hidden="true" /></div>
        <div className="overview-list">{recent.map((run) => <button className="overview-list-row" key={run.id} onClick={() => onOpenRun(run)}>
          <span><strong>{run.name}</strong><small>{formatTime(run.updated_at, language)} · {run.completed_scenarios}/{run.total_scenarios} {t("个场景")}</small></span><Status value={run.status} language={language} /><ArrowRight aria-hidden="true" />
        </button>)}{!recent.length && <div className="overview-empty">{t("暂无最近活动")}</div>}</div>
        {recent.length > 0 && <button className="overview-panel-link" onClick={onOpenDashboard}>{t("进入分析看板")}<ArrowRight aria-hidden="true" /></button>}
      </section>
    </div>
  </div>;
}
