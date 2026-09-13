// Delivery only. Core owns due-time, quiet-hours, scope and retry decisions.
function startScheduleNotifications({ client, Notification, reveal, intervalMs = 5000 }) {
  let stopped = false;
  let busy = false;
  const active = new Set();
  async function poll() {
    if (stopped || busy || !Notification.isSupported()) return;
    busy = true;
    try {
      const claim = await client.call("notification-action", { action: "claim" });
      if (!claim.ok || !claim.delivery || stopped) return;
      const { id, leaseToken } = claim.delivery;
      const authorized = await client.call("notification-action", { action: "authorize", id, leaseToken });
      if (!authorized.ok || stopped) return;
      let settled = false;
      const notice = new Notification({ title: "Kuro · 排程提醒", body: String(authorized.title || "有安排需要查看"), silent: false });
      active.add(notice);
      const finish = async (result) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        await client.call("notification-action", { action: "ack", id, leaseToken, result });
      };
      const timer = setTimeout(() => void finish("unknown"), 8000);
      notice.once("show", () => void finish("delivered"));
      notice.once("failed", () => { active.delete(notice); void finish("failed"); });
      notice.once("close", () => active.delete(notice));
      notice.on("click", () => reveal());
      notice.show();
    } finally { busy = false; }
  }
  const timer = setInterval(() => void poll().catch(() => undefined), intervalMs);
  timer.unref?.();
  void poll().catch(() => undefined);
  return () => { stopped = true; clearInterval(timer); for (const notice of active) notice.close(); active.clear(); };
}
module.exports = { startScheduleNotifications };
