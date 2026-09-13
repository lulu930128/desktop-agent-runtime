import type { WorkPanelBridge } from "./types";

type Item = {title:string; notes:string; kind:string; timezone:string; allDay:boolean; start?:string; end?:string; due?:string; trackCompletion:boolean; recurrence:Record<string,unknown>|null; notification:{enabled:boolean;minutesBefore:number;allDayTime:string;channel:string}};
type Entry = {id:string;scheduleId:string;occurrenceDate:string;revision:number;item:Item;state:string;timeState:string;overdue:boolean;recurring:boolean};
type View = {ok:boolean;error?:string;items?:Entry[];coverage?:string;hasMore?:boolean;nextOffset?:number;startDate?:string;endDateExclusive?:string;timezone?:string;limitations?:string[]};
type Notice = {id:string;title:string;state:string;dueAt:string;channel:string};

function el<K extends keyof HTMLElementTagNameMap>(tag:K,cls="",label=""):HTMLElementTagNameMap[K] {
  const node=document.createElement(tag);node.className=cls;node.textContent=label;return node;
}
function btn(label:string,callback:()=>void,cls="quiet-button"):HTMLButtonElement {
  const node=el("button",cls,label);node.type="button";node.onclick=callback;return node;
}
function shift(value:string,days:number):string { const date=new Date(`${value}T12:00:00Z`);date.setUTCDate(date.getUTCDate()+days);return date.toISOString().slice(0,10); }
function errorText(result:Record<string,unknown>):string {
  if(result.error==="conflict")return "這筆安排已變更，或既有例外無法一起修改。草稿已保留，請重新讀取後確認修改範圍。";
  if(result.error==="invalid_request")return `請檢查時間、時區與重複規則。${String(result.message||"")}`;
  return "目前無法連接排程服務。請重試，或從 Launcher 確認服務狀態。";
}

export class SchedulePanel {
  readonly root=el("section","local-schedule");
  private view:View={ok:false};
  private start="";
  private followingToday=true;
  private span=1;
  private timezone="";
  private loading=false;
  private generation=0;
  private dialog:HTMLDialogElement|null=null;
  private notices:Notice[]=[];
  private noticesTruncated=false;
  private notificationsUnavailable=false;
  private preferences:Record<string,unknown>|null=null;
  constructor(private bridge:WorkPanelBridge) {
    this.root.id="local-schedule";
    this.render();
    queueMicrotask(()=>void this.refresh());
    window.setInterval(()=>{if(this.root.isConnected && !document.hidden && !this.dialog && !this.root.contains(document.activeElement))void this.refresh(false);},15000);
  }
  private async call(action:Parameters<WorkPanelBridge["schedule"]>[0],payload:Record<string,unknown>={}) {
    try{return await this.bridge.schedule(action,payload);}catch{return {ok:false,error:"core_unavailable"};}
  }
  private async refresh(materialize=true,more=false) {
    const generation=++this.generation;
    this.loading=true;if(!this.dialog)this.render();
    const health=await this.call("status");
    if(generation!==this.generation)return;
    if(!health.ok){this.view={ok:false,error:String(health.error)};this.loading=false;this.render();return;}
    if(this.followingToday || !this.start)this.start=String(health.today);
    this.timezone ||= String(health.timezone);
    const end=shift(this.start,this.span);
    if(materialize)await this.call("materialize",{through:shift(end,1)});
    const [result,notifications]=await Promise.all([this.call("view",{start:this.start,end,timezone:this.timezone,limit:100,offset:more?this.view.nextOffset||0:0}),this.call("notifications")]);
    if(generation!==this.generation)return;
    const incoming=result as unknown as View;
    this.view=more && incoming.ok ? {...incoming,items:[...(this.view.items||[]),...(incoming.items||[])]}:incoming;
    if(notifications.ok){this.notices=(notifications.items||[]) as Notice[];this.noticesTruncated=Boolean(notifications.hasMore);this.preferences=notifications.preferences as Record<string,unknown>;}
    else {this.notices=[];this.preferences=null;}
    this.notificationsUnavailable=!notifications.ok || health.notificationScheduler==="failed";
    this.loading=false;this.render();
  }
  private render() {
    this.root.replaceChildren();
    const heading=el("div","block-heading");heading.append(el("h2","","時間表"),btn("新增安排",()=>this.edit()));
    this.root.append(heading);
    const toolbar=el("div","schedule-toolbar");
    const date=el("input");date.type="date";date.value=this.start;date.setAttribute("aria-label","查看日期");date.onchange=()=>{if(date.value){this.followingToday=false;this.start=date.value;void this.refresh();}};
    const range=el("select");range.setAttribute("aria-label","日期範圍");
    for(const [value,label] of [[1,"單日"],[7,"七日"]] as const){const o=el("option","",label);o.value=String(value);range.append(o);}range.value=String(this.span);range.onchange=()=>{this.span=Number(range.value);void this.refresh();};
    toolbar.append(date,range,btn("今天",()=>{this.followingToday=true;this.start="";this.span=1;void this.refresh();}),btn("重新整理",()=>void this.refresh()),btn("提醒設定",()=>this.editPreferences()));
    this.root.append(toolbar);
    if(this.loading)this.root.append(el("p","schedule-status","正在讀取安排…"));
    if(!this.view.ok){this.root.append(el("p","schedule-status is-error",this.loading?"連接排程服務中…":"排程服務目前無法使用，不能確認是否有安排。"));return;}
    if(this.notificationsUnavailable)this.root.append(el("p","schedule-status is-error","提醒狀態暫時無法確認，請稍後重新整理。安排清單仍可查看。"));
    if(this.view.coverage!=="complete")this.root.append(el("p","schedule-status","歷史安排仍在整理中，清單尚未完整。請稍候重新整理。"));
    if(this.view.limitations?.includes("dst_occurrences_skipped"))this.root.append(el("p","schedule-status","部分重複時段因日光節約時間不存在而略過，請調整該系列時間。"));
    const entries=this.view.items||[];
    const groups:[string,(e:Entry)=>boolean][]=[
      ["未完成／逾期",e=>e.overdue],["全天",e=>!e.overdue&&e.state==="pending"&&e.item.allDay],
      ["進行中／稍後",e=>!e.overdue&&e.state==="pending"&&!e.item.allDay],["已完成／略過",e=>e.state!=="pending"]];
    for(const [label,match] of groups){const selected=entries.filter(match);if(!selected.length)continue;
      const group=label==="已完成／略過"?el("details","schedule-group"):el("div","schedule-group");
      group.append(el(label==="已完成／略過"?"summary":"h3","",`${label} · ${selected.length}`));
      for(const entry of selected)group.append(this.row(entry));this.root.append(group);
    }
    if(!entries.length && !this.loading)this.root.append(el("p","schedule-empty",this.view.coverage==="complete"?"這段時間沒有安排。可以新增固定行程、特殊安排或待辦期限。":"尚未取得完整安排，請稍候。"));
    if(this.view.hasMore)this.root.append(btn("載入更多",()=>void this.refresh(false,true)));
    if(this.notices.length){const box=el("details","schedule-reminders");box.append(el("summary","",`提醒紀錄 · ${this.notices.length}`));
      if(this.noticesTruncated)box.append(el("p","schedule-status","僅顯示最近 100 筆提醒，較早紀錄仍保存在本機。"));
      const labels:Record<string,string>={ready:"待查看",suppressed:"勿擾中",missed:"錯過提醒時段",unknown:"送達結果不明",failed:"配送失敗",delivered:"已送至桌面",snoozed:"稍後提醒",claimed:"準備配送",dispatching:"配送中"};
      for(const notice of this.notices){const row=el("div","reminder-row");row.append(el("strong","",notice.title),el("span","",labels[notice.state]||notice.state));
        row.append(btn("已讀",()=>void this.noticeAction(notice,"dismiss")),btn("10 分鐘後",()=>void this.noticeAction(notice,"snooze",10)),btn("30 分鐘後",()=>void this.noticeAction(notice,"snooze",30)),btn("自訂",()=>void this.noticeAction(notice,"snooze")));box.append(row);}this.root.append(box);}
  }
  private row(entry:Entry) {
    const row=el("article","local-schedule-row");row.dataset.scheduleId=entry.scheduleId;
    const copy=el("div","schedule-row-copy");copy.append(el("strong","",entry.item.title));
    const format=(value:string|undefined)=>!value?"":entry.item.allDay?value:value.replace("T"," ").replace(/([+-]\d\d:\d\d|Z)$/," ");
    const when=entry.item.kind==="deadline"?`期限 ${format(entry.item.due)}`:`${format(entry.item.start)} → ${format(entry.item.end)}${entry.item.allDay?"（結束日不含）":""}`;
    copy.append(el("span","",when),el("small","",`${entry.item.kind==="study"?"學習安排":entry.item.kind==="deadline"?"待辦期限":"行程"} · ${entry.item.timezone}${entry.recurring?" · 固定行程":""}${entry.item.notification.enabled?" · 提醒已開":""}`));
    const actions=el("div","schedule-row-actions");actions.append(btn("編輯",()=>this.edit(entry)));
    if(entry.item.trackCompletion)actions.append(btn(entry.state==="pending"?"完成":"恢復未完成",()=>void this.mutateState(entry,entry.state==="pending"?"complete":"reopen")));
    if(entry.item.trackCompletion&&entry.state==="pending")actions.append(btn("略過",()=>void this.mutateState(entry,"skip")));
    actions.append(btn("取消",()=>this.cancel(entry)));
    row.append(copy,actions);return row;
  }
  private async mutateState(entry:Entry,action:string) {
    const result=await this.call("mutate",{action,id:entry.scheduleId,expectedRevision:entry.revision,scope:"this",occurrenceDate:entry.occurrenceDate,confirmed:true,idempotencyKey:crypto.randomUUID()});
    if(!result.ok)window.alert(errorText(result));await this.refresh();
  }
  private cancel(entry:Entry) {
    const dialog=this.modal("取消安排");const body=el("p","",`取消「${entry.item.title}」？紀錄會保留。`);const scope=this.select([["this","只取消這次"],["future","這次及以後"],["all","整個系列"]]);if(!entry.recurring)scope.value="this";
    const error=el("p","schedule-status is-error");const submit=btn("確認取消",async()=>{submit.disabled=true;const result=await this.call("mutate",{action:"cancel",id:entry.scheduleId,expectedRevision:entry.revision,scope:scope.value,...(scope.value!=="all"?{occurrenceDate:entry.occurrenceDate}:{}),confirmed:true,idempotencyKey:crypto.randomUUID()});if(!result.ok){error.textContent=errorText(result);submit.disabled=false;}else{dialog.close();await this.refresh();}});
    dialog.append(body,...(entry.recurring?[this.field("範圍",scope)]:[]),error,submit);dialog.showModal();
  }
  private modal(title:string) {
    this.dialog?.close();const dialog=el("dialog","schedule-dialog");const head=el("div","block-heading");head.append(el("h2","",title),btn("關閉",()=>dialog.close()));dialog.append(head);
    dialog.addEventListener("close",()=>{dialog.remove();if(this.dialog===dialog)this.dialog=null;});document.body.append(dialog);this.dialog=dialog;return dialog;
  }
  private field(label:string,node:HTMLElement) {const field=el("label","schedule-field");field.append(el("span","",label),node);return field;}
  private select(options:string[][]) {const node=el("select");for(const [value,label] of options){const o=el("option","",label);o.value=value;node.append(o);}return node;}
  private input(type:string,value="") {const node=el("input");node.type=type;node.value=value;return node;}
  private async edit(entry?:Entry) {
    let record=entry?await this.call("item",{id:entry.scheduleId}):null;
    if(record&&!record.ok){window.alert(errorText(record));return;}
    const dialog=this.modal(entry?"編輯安排":"新增安排");const form=el("form","schedule-form");
    const title=this.input("text");title.required=true;title.maxLength=300;
    const notes=el("textarea");notes.maxLength=2000;notes.rows=2;
    const kind=this.select([["event","一般行程"],["study","學習安排"],["deadline","待辦期限"]]);
    const timezone=this.input("text",this.timezone);timezone.required=true;
    const allDay=this.input("checkbox");const start=this.input("datetime-local");const end=this.input("datetime-local");start.required=true;end.required=true;
    const completion=this.input("checkbox");const recurring=this.select([["","不重複"],["daily","每天"],["weekly","每週"],["monthly","每月指定日期"]]);
    const interval=this.input("number","1");interval.min="1";interval.max="120";
    const ending=this.select([["","持續重複"],["count","次數"],["until","截止日期"]]);const count=this.input("number","10");count.min="1";count.max="100000";const until=this.input("date");
    const weekdays=el("div","schedule-weekdays");const dayInputs:HTMLInputElement[]=[];for(let i=0;i<7;i++){const input=this.input("checkbox");dayInputs.push(input);weekdays.append(this.field(["一","二","三","四","五","六","日"][i],input));}
    const notify=this.input("checkbox");const before=this.input("number","10");before.min="0";before.max="10080";const at=this.input("time","09:00");const channel=this.select([["panel","面板"],["desktop","桌面與面板"]]);
    const scope=this.select([["this","只改這次"],["future","這次及以後"],["all","整個系列"]]);
    const endField=this.field("結束（全天的結束日不含）",end);const recurrenceBox=el("fieldset");const recurrenceDetails=el("div","schedule-form-grid");recurrenceDetails.append(this.field("每幾天／週／月",interval),this.field("結束規則",ending),this.field("次數",count),this.field("截止日期",until),weekdays);recurrenceBox.append(this.field("重複規則",recurring),recurrenceDetails);
    const notifyBox=el("fieldset");notifyBox.append(this.field("需要提醒",notify),this.field("提前幾分鐘（0 為準時）",before),this.field("全天提醒時間",at),this.field("通知位置",channel));
    const update=()=>{start.type=end.type=allDay.checked?"date":"datetime-local";endField.hidden=kind.value==="deadline";end.required=!endField.hidden;recurrenceBox.hidden=Boolean(entry)&&scope.value==="this";recurrenceDetails.hidden=!recurring.value;weekdays.hidden=recurring.value!=="weekly";count.disabled=ending.value!=="count";until.disabled=ending.value!=="until";before.disabled=at.disabled=channel.disabled=!notify.checked;at.parentElement!.hidden=!allDay.checked;};
    const fill=(item:Item)=>{title.value=item.title;notes.value=item.notes||"";kind.value=item.kind;timezone.value=item.timezone;allDay.checked=item.allDay;update();start.value=(item.due||item.start||"").slice(0,item.allDay?10:16);end.value=(item.end||"").slice(0,item.allDay?10:16);completion.checked=item.trackCompletion;recurring.value=String(item.recurrence?.frequency||"");interval.value=String(item.recurrence?.interval||1);ending.value=item.recurrence?.count?"count":item.recurrence?.until?"until":"";count.value=String(item.recurrence?.count||10);until.value=String(item.recurrence?.until||"");dayInputs.forEach((node,i)=>node.checked=((item.recurrence?.weekdays||[]) as number[]).includes(i));notify.checked=item.notification.enabled;before.value=String(item.notification.minutesBefore);at.value=item.notification.allDayTime;channel.value=item.notification.channel;update();};
    const seed:Item=entry?.item||{title:"",notes:"",kind:"event",timezone:this.timezone||Intl.DateTimeFormat().resolvedOptions().timeZone,allDay:false,start:`${this.start||new Date().toISOString().slice(0,10)}T09:00`,end:`${this.start||new Date().toISOString().slice(0,10)}T10:00`,trackCompletion:false,recurrence:null,notification:{enabled:false,minutesBefore:10,allDayTime:"09:00",channel:"panel"}};
    fill(seed);scope.onchange=()=>{const master=record!.item as Item;fill(scope.value==="all"?master:{...entry!.item,recurrence:scope.value==="future"?master.recurrence:null});};
    allDay.onchange=()=>{const s=start.value.slice(0,10),e=end.value.slice(0,10);update();start.value=allDay.checked?s:`${s}T09:00`;end.value=allDay.checked?(e===s?shift(e,1):e):`${e}T10:00`;};
    kind.onchange=()=>{completion.checked=kind.value!=="event";update();};recurring.onchange=ending.onchange=notify.onchange=update;
    if(entry?.recurring)form.append(this.field("修改範圍",scope));
    form.append(this.field("名稱",title),this.field("類型",kind),this.field("時區",timezone),this.field("全天",allDay),this.field("開始／截止",start),endField,this.field("追蹤完成狀態",completion),recurrenceBox,notifyBox,this.field("備註",notes));
    const error=el("p","schedule-status is-error");error.setAttribute("role","alert");const save=el("button","primary-button",entry?"儲存變更":"建立安排");save.type="submit";
    const reload=btn("重新讀取版本（保留草稿）",async()=>{if(!entry)return;const latest=await this.call("item",{id:entry.scheduleId});if(!latest.ok){error.textContent=errorText(latest);return;}record=latest;error.textContent="已讀取最新版本，草稿仍保留。請確認內容與修改範圍，再儲存。";});
    form.append(error,...(entry?[reload]:[]),save);let pendingKey="",pendingPayload="";
    form.onsubmit=async(event)=>{event.preventDefault();if(save.disabled)return;save.disabled=true;error.textContent="";
      const item:Record<string,unknown>={title:title.value,notes:notes.value,kind:kind.value,timezone:timezone.value,allDay:allDay.checked,trackCompletion:completion.checked,notification:{enabled:notify.checked,minutesBefore:Number(before.value),allDayTime:at.value,channel:channel.value}};
      if(kind.value==="deadline")item.due=start.value;else{item.start=start.value;item.end=end.value;}
      item.recurrence=(!entry||scope.value!=="this")&&recurring.value?{frequency:recurring.value,interval:Number(interval.value),...(recurring.value==="weekly"?{weekdays:dayInputs.flatMap((node,i)=>node.checked?[i]:[])}:{}),...(ending.value==="count"?{count:Number(count.value)}:ending.value==="until"?{until:until.value}:{})}:null;
      const prepared=await this.call("prepare",{item});if(!prepared.ok){error.textContent=errorText(prepared);save.disabled=false;return;}
      const payload={action:entry?"update":"create",confirmed:true,item:prepared.item,...(entry?{id:entry.scheduleId,expectedRevision:record!.revision,scope:scope.value,...(scope.value!=="all"?{occurrenceDate:entry.occurrenceDate}:{})}:{})};
      const identity=JSON.stringify(payload);if(identity!==pendingPayload){pendingPayload=identity;pendingKey=crypto.randomUUID();}
      const result=await this.call("mutate",{...payload,idempotencyKey:pendingKey});if(!result.ok){error.textContent=errorText(result);save.disabled=false;return;}dialog.close();await this.refresh();};
    dialog.append(form);dialog.showModal();title.focus();
  }
  private async noticeAction(notice:Notice,action:string,minutes?:number) {
    let until=minutes?new Date(Date.now()+minutes*60000).toISOString():"";
    if(action==="snooze"&&!minutes){const value=window.prompt("幾分鐘後提醒？（1–10080）","60");if(value===null)return;const n=Number(value);if(!Number.isInteger(n)||n<1||n>10080)return;until=new Date(Date.now()+n*60000).toISOString();}
    const result=await this.call("notification-action",{action,id:notice.id,confirmed:true,...(action==="snooze"?{until}:{})});if(!result.ok)window.alert(errorText(result));await this.refresh(false);
  }
  private editPreferences() {
    if(!this.preferences){window.alert("請先連接排程服務。");return;}const p=this.preferences;const dialog=this.modal("提醒設定");const enabled=this.input("checkbox");enabled.checked=Boolean(p.quietEnabled);const start=this.input("time",String(p.quietStart));const end=this.input("time",String(p.quietEnd));const tz=this.input("text",String(p.timezone));const error=el("p","schedule-status is-error");
    dialog.append(this.field("啟用勿擾（面板仍保留提醒）",enabled),this.field("開始",start),this.field("結束",end),this.field("勿擾時區",tz),error,btn("儲存設定",async()=>{const result=await this.call("notification-action",{action:"preferences",confirmed:true,preferences:{quietEnabled:enabled.checked,quietStart:start.value,quietEnd:end.value,timezone:tz.value}});if(!result.ok){error.textContent=errorText(result);return;}dialog.close();await this.refresh(false);}));dialog.showModal();
  }
}
