const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const { createCoreClient, registerCoreIpc } = require("../pet-electron/src/main-process/core-client");

test("Core client requires configuration and rejects arbitrary actions", async () => {
  const client = createCoreClient({});
  assert.equal((await client.call("status")).error, "core_not_configured");
  assert.equal((await client.call("shutdown")).error, "invalid_request");
});

test("Core identity verified before mutation, token stays in transport", async (t) => {
  const calls = [];
  let identity = "ours";
  const server = http.createServer((req,res) => {
    calls.push({route:req.url, auth:req.headers.authorization});
    res.setHeader("Content-Type","application/json");
    res.end(JSON.stringify(req.url === "/status" ? {ok:true,service:"kuro-core",schema:3,contract:"kuro.core.schedule.v1",instanceId:identity} : {ok:true}));
  });
  await new Promise(resolve => server.listen(0,"127.0.0.1",resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const client = createCoreClient({url:`http://127.0.0.1:${server.address().port}`,token:"private",instance:"ours"});
  assert.equal((await client.call("view",{start:"2026-09-12",end:"2026-09-13",timezone:"Asia/Taipei"})).ok,true);
  assert.ok(calls.every(c => c.auth === "Bearer private" && !c.route.includes("private")));
  identity = "other";
  assert.equal((await client.call("mutate",{})).error,"core_identity_mismatch");
  assert.equal(calls.at(-1).route,"/status");
});

test("Schedule IPC rejects another window or subframe", async () => {
  let handler;
  const webContents = {mainFrame:{}};
  registerCoreIpc({handle:(_name,fn)=>{handler=fn;}},{call:async()=>({ok:true})},()=>({isDestroyed:()=>false,webContents}));
  assert.equal((await handler({sender:{},senderFrame:{}},"status")).error,"unauthorized_sender");
  assert.equal((await handler({sender:webContents,senderFrame:{}},"status")).error,"unauthorized_sender");
  assert.equal((await handler({sender:webContents,senderFrame:webContents.mainFrame},"status")).ok,true);
  for (const action of ["claim","authorize","ack"]) {
    assert.equal((await handler({sender:webContents,senderFrame:webContents.mainFrame},"notification-action",{action})).ok,false);
  }
});

test("Core unavailable is explicit, never a successful empty view", async () => {
  const client = createCoreClient({url:"http://127.0.0.1:1",token:"private",instance:"ours",timeoutMs:100});
  const result = await client.call("view",{});
  assert.equal(result.ok,false);
  assert.equal(result.error,"core_unavailable");
  assert.equal(result.items,undefined);
});
