import type { WorkPanelBridge } from "./work-panel/types";

export type Identity = {client: string; actor: string; history: string; context: string; revision: number};
type RecordValue = Record<string, unknown>;
export type Port = {submit(raw: string): void; response: {connect(cb: (raw: string) => void): void}; event: {connect(cb: (raw: string) => void): void}};
const contract = "kuro.qt.work.v1";
const failure = (error: string, unknownResult = false) => ({ok: false, error, unknownResult, retry: false});
const same = (a: Identity | null, b: Identity | null) => !!a && !!b && ["client", "actor", "history", "context", "revision"].every(k => a[k as keyof Identity] === b[k as keyof Identity]);
function validIdentity(v: unknown): v is Identity {
  if (!v || typeof v !== "object") return false;
  const row = v as RecordValue;
  return ["client", "actor", "history", "context"].every(k => typeof row[k] === "string") && Number.isSafeInteger(row.revision);
}

export class OwnerTransport {
  identity: Identity | null = null;
  private sequence = 0;
  private session = crypto.randomUUID();
  private pending = new Map<string, {expected: Identity | null; method: string; done(value: RecordValue): void; timer: ReturnType<typeof setTimeout>}>();
  private listeners = new Map<string, Set<(v: any) => void>>();
  private lastData: RecordValue | null = null;
  constructor(private port: Port, private timeout = 25000) {
    port.response.connect(raw => this.response(raw));
    port.event.connect(raw => this.event(raw));
  }
  on(name: string, callback: (v: any) => void): () => void {
    const set = this.listeners.get(name) || new Set(); set.add(callback); this.listeners.set(name, set);
    return () => { set.delete(callback); };
  }
  notify(name: string, value: unknown): void {
    for (const callback of this.listeners.get(name) || []) callback(value);
  }
  private adoptIdentity(identity: Identity): void {
    const changed = !same(this.identity, identity);
    this.identity = identity;
    if (changed) {
      this.lastData = null;
      this.notify("onIdentityChange", identity);
    }
  }
  async hello(): Promise<void> {
    const result = await this.call("hello");
    if (!result.ok || !this.identity) throw new Error("Qt owner handshake failed");
  }
  call(method: string, payload: RecordValue = {}): Promise<any> {
    if (!this.identity && method !== "hello") return Promise.resolve(failure("owner_not_ready"));
    const id = `web-${this.session}-${++this.sequence}`;
    const expected = this.identity ? {...this.identity} : null;
    return new Promise(done => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        done(failure("bridge_timeout_no_retry", !method.startsWith("get") && method !== "hello"));
      }, method === "applyProfile" ? 100000 : this.timeout);
      this.pending.set(id, {expected, method, done, timer});
      this.port.submit(JSON.stringify({contract, id, expected, method, payload}));
    });
  }
  private response(raw: string): void {
    let reply: any;
    try { reply = JSON.parse(raw); } catch { return; }
    const item = this.pending.get(reply?.id);
    if (!item || reply.contract !== contract || !validIdentity(reply.identity)) return;
    if (item.method !== "hello" && !same(reply.expected, item.expected)) return;
    clearTimeout(item.timer); this.pending.delete(reply.id);
    // A late reply cannot roll the identity backward after an event changed it.
    if (this.identity && reply.identity.revision < this.identity.revision) {
      item.done(failure("stale_response", reply.result?.unknownResult === true)); return;
    }
    const transitions = ["hello", "selectHistory", "createHistory", "deleteHistory", "applyProfile"];
    if (item.method === "sendText" && !item.expected?.history && reply.result?.createdHistory === true &&
        ["actor", "client", "context"].every(key => reply.identity[key] === item.expected?.[key as keyof Identity])) transitions.push("sendText");
    if (item.method === "getHistories" && !item.expected?.history && reply.result?.historyUid === reply.identity.history &&
        ["actor", "client", "context"].every(key => reply.identity[key] === item.expected?.[key as keyof Identity])) transitions.push("getHistories");
    if (!transitions.includes(item.method) && !same(reply.identity, item.expected)) {
      item.done(failure("stale_context", reply.result?.unknownResult === true)); return;
    }
    let result = reply.result;
    if (!result || typeof result !== "object" || typeof result.ok !== "boolean") {
      item.done(failure("invalid_owner_result")); return;
    }
    try {
      this.adoptIdentity(reply.identity);
      if (item.method === "getData") {
        if (result.ok) this.lastData = result;
        else if (this.lastData) result = {...this.lastData, ...result, transportStale: true};
        for (const callback of this.listeners.get("onData") || []) callback(result);
      }
      if (item.method === "getState") {
        for (const callback of this.listeners.get("onState") || []) callback(result);
      }
    } finally {
      // A presentation exception remains observable, but cannot orphan a
      // validated owner reply after its timeout and pending entry were removed.
      item.done(result);
    }
  }
  private event(raw: string): void {
    let event: any;
    try { event = JSON.parse(raw); } catch { return; }
    if (event?.contract !== contract || !validIdentity(event.identity) || !["onState", "onData", "onChatState"].includes(event.name)) return;
    if (this.identity && event.identity.revision < this.identity.revision) return;
    this.adoptIdentity(event.identity);
    if (event.name === "onData") {
      if (event.value?.ok) this.lastData = event.value;
      else if (this.lastData) event.value = {...this.lastData, ...event.value, transportStale: true};
    }
    for (const callback of this.listeners.get(event.name) || []) callback(event.value);
  }
}

export function makeOwnerBridge(t: OwnerTransport): WorkPanelBridge {
  const call = (method: string, payload: RecordValue = {}) => t.call(method, payload);
  let notifications: any = null;
  t.on("onIdentityChange", () => {
    notifications = null;
    t.notify("onNotificationCapability", null);
  });
  return {
    schedule: async (action, payload = {}) => {
      if (action === "notification-action") {
        if (notifications?.consumerWriteContract !== "kuro.core.notification-command.v1")
          return failure("notification_write_contract_unavailable");
        const expectedRevision = payload.action === "preferences" ? notifications.preferencesRevision
          : notifications.items?.find((row: any) => row.id === payload.id)?.revision;
        if (typeof expectedRevision !== "string") return failure("read_notification_before_confirming");
        payload = {...payload, expectedRevision, idempotencyKey: crypto.randomUUID()};
      }
      const result = await call("schedule", {action, payload});
      if (action === "notifications") { notifications = result?.ok ? result : null; t.notify("onNotificationCapability", notifications); }
      if (action === "notification-action") notifications = null; // Re-read before another action; never retry unknown.
      return result;
    },
    getState: () => call("getState"), getData: () => call("getData"),
    getChatState: () => call("getChatState"), getChatHistory: () => call("getChatHistory"),
    getProfile: () => call("getProfile"), applyProfile: payload => call("applyProfile", payload),
    getHistories: (historyUid = "") => call("getHistories", {historyUid}),
    createHistory: () => call("createHistory"), selectHistory: historyUid => call("selectHistory", {historyUid}),
    deleteHistory: (historyUid, historyTitle = "") => call("deleteHistory", {historyUid, historyTitle}),
    getMemories: () => call("getMemories"), memoryAction: (action, payload = {}) => call("memoryAction", {action, payload}),
    getTools: () => call("getTools"), sendText: (text, attachments) => call("sendText", {text, attachments}),
    refreshMail: () => call("refreshMail"), getMailMessage: messageId => call("getMailMessage", {messageId}),
    control: (action, payload = {}) => call("control", {action, payload}),
    closeWindow: () => { void call("closeWindow"); }, minimizeWindow: () => { void call("minimizeWindow"); },
    toggleMaximizeWindow: () => { void call("toggleMaximizeWindow"); },
    onState: cb => t.on("onState", cb), onData: cb => t.on("onData", cb), onChatState: cb => t.on("onChatState", cb)
  };
}
