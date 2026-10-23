"""Bounded Hub GET producer and pure snapshot projection; no Hub DB imports."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import http.client
import json
import os
import socket
import threading
import time

from .contracts import AvailabilityStatus as A, ConnectionStatus as C, FreshnessStatus as F
from .contracts import Observation, isoformat_utc, parse_datetime
from .work_contracts import ActionKind, EvidenceKind, SourceEvidence
from .work_evidence import WorkEvidenceRead, bounded_text, identity, stable_id

HUBS = {'japanese_study': ('japanese-study-hub', 18791, 'JSTUDY_API_TOKEN'),
        'english_study': ('english-study-hub', 18887, 'ESTUDY_API_TOKEN')}
PATHS = ('/health', '/api/v1/summary', '/api/v1/reviews/due?limit=20', '/api/v1/study/plan?limit=20')
MAX_BYTES = 131072


def validate_hubs(value):
    if value is None: value = {}
    if not isinstance(value, dict) or set(value)-set(HUBS): raise ValueError('Unknown Hub source')
    result = {}
    for source in HUBS:
        options = value.get(source, {})
        if not isinstance(options, dict) or set(options)-{'enabled', 'interval_seconds', 'ttl_seconds'}:
            raise ValueError('Invalid Hub options')
        options = {'enabled': False, 'interval_seconds': 300, 'ttl_seconds': 600, **options}
        if type(options['enabled']) is not bool: raise ValueError('Hub enabled must be boolean')
        for key in ('interval_seconds', 'ttl_seconds'):
            if type(options[key]) is not int or not 60 <= options[key] <= 86400:
                raise ValueError('Hub timing must be 60..86400 seconds')
        result[source] = options
    return result


class HubReadError(Exception):
    pass


class HubClient:
    """Fixed loopback/paths, no redirects/proxies/retries; interruptible deadline."""
    def __init__(self):
        self.lock = threading.Lock()
        self.active = None
        self.closed = False

    @staticmethod
    def _abort(connection, sock=None):
        sock = sock or connection.sock
        if sock:
            try: sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        connection.close()

    def close(self):
        with self.lock:
            self.closed = True
            if self.active: self._abort(self.active[0],self.active[1][0])

    def get(self, source, path, stop):
        if source not in HUBS or path not in PATHS: raise ValueError('Hub request not allowlisted')
        connection = http.client.HTTPConnection('127.0.0.1', HUBS[source][1], timeout=1)
        transport=[None]
        expired=threading.Event()
        deadline=time.monotonic()+1.5
        response=None
        with self.lock:
            if self.closed or stop.is_set(): raise HubReadError('cancelled')
            if self.active is not None: raise HubReadError('busy')
            self.active = (connection,transport)
        def expire():
            expired.set()
            self._abort(connection,transport[0])
        def check_cancelled():
            if stop.is_set() or self.closed: raise HubReadError('cancelled')
            if expired.is_set() or time.monotonic()>=deadline: raise HubReadError('timeout')
        timer = threading.Timer(1.5, expire); timer.daemon = True
        timer.start()
        try:
            # Credentials are inherited by the owner only; never read config/secrets files.
            token = os.environ.get(HUBS[source][2], '')
            headers = {'Accept': 'application/json', 'Connection': 'close'}
            if token: headers['Authorization'] = 'Bearer ' + token
            connection.connect()
            # Retain the socket reference when HTTPResponse takes its makefile.
            transport[0]=connection.sock
            # A deadline/close must not let HTTPConnection silently reconnect.
            connection.auto_open = 0
            check_cancelled()
            connection.request('GET', path, headers=headers)
            response = connection.getresponse()
            check_cancelled()
            if response.status in (401, 403): raise HubReadError('auth_required')
            if response.status != 200: raise HubReadError('http_failure')
            if response.getheader('Content-Encoding', 'identity') != 'identity': raise HubReadError('encoding_rejected')
            data = bytearray()
            while True:
                check_cancelled()
                # Windows shutdown may not wake an in-flight select immediately.
                # A 200ms body-idle bound also makes close cooperative within 500ms.
                transport[0].settimeout(min(.2,max(.001,deadline-time.monotonic())))
                part = response.read1(min(4096, MAX_BYTES+1-len(data)))
                check_cancelled()
                data.extend(part)
                if len(data)>MAX_BYTES: raise HubReadError('too_large')
                if not part: break
            payload = json.loads(data.decode('utf-8'))
            if not isinstance(payload, dict) or payload.get('ok') is not True: raise HubReadError('invalid_contract')
            check_cancelled()
            return payload
        except (OSError, http.client.HTTPException, ValueError, UnicodeError) as exc:
            if isinstance(exc, PermissionError): raise
            check_cancelled()
            raise HubReadError('transport_or_payload_failure') from None
        finally:
            timer.cancel(); timer.join()
            if response is not None: response.close()
            connection.close()
            if transport[0] is not None: transport[0].close()
            with self.lock: self.active = None


def timestamp(value):
    if value in (None, ''): return None
    try: return parse_datetime(value, field_name='hub.timestamp')
    except (ValueError, TypeError, OverflowError): return None


def observation(source, now, *, stamp=None, until=None, availability=A.MISSING,
                freshness=F.UNKNOWN, connection=C.UNKNOWN, limitations=(), details=None):
    details = details or {}
    return Observation.create(integration_id=source, kind='source_status', source_ref=source+':hub',
        title=source, summary='Canonical source read only; no local learning or market calculations.',
        observed_at=stamp, received_at=now, valid_until=until, availability=availability,
        declared_freshness=freshness, connection=connection, limitations=tuple(limitations),
        details=details, idempotency_key=identity(source,'snapshot',json.dumps([isoformat_utc(stamp),details,list(limitations)],sort_keys=True)))


class HubIntegration:
    def __init__(self, source, options, client=None):
        self.source, self.options = source, validate_hubs({source: options})[source]
        self.client = client or HubClient()
        self.lock = threading.Lock()
        self.snapshot = None
        self.error = None
        self.pending = []
        self.next_read = 0.0
        self.cycle_started = 0.0
        self.closed = False

    def close(self):
        self.closed = True; self.client.close()

    def tick(self, stop):
        """One bounded GET per Core transport tick; never called by a GET route."""
        if self.closed or stop.is_set() or not self.options['enabled']: return
        now = time.monotonic()
        if now < self.next_read: return
        if not self.pending: self.cycle_started = now
        if now-self.cycle_started > 60:
            self.pending = []; self.error = 'cycle_expired'
            self.next_read = now+self.options['interval_seconds']; return
        try:
            part = self.client.get(self.source, PATHS[len(self.pending)], stop)
            if stop.is_set() or self.closed: return
            if not self.pending and part.get('service') != HUBS[self.source][0]: raise HubReadError('source_identity_mismatch')
            self.pending.append(part)
            if len(self.pending)==4:
                received = datetime.now(timezone.utc)
                # Validate before publication; malformed data never replaces a usable snapshot.
                project_hub(self.source,self.pending[1:],received,received,self.options['ttl_seconds'])
                with self.lock: self.snapshot=(self.pending[1:],received); self.error=None
                self.pending=[]; self.next_read=now+self.options['interval_seconds']
        except PermissionError:
            with self.lock: self.error='permission_denied'
            self.closed=True
            self.client.close()
            raise
        except (HubReadError, ValueError, TypeError) as exc:
            with self.lock: self.error=str(exc) if isinstance(exc,HubReadError) else 'invalid_contract'
            self.pending=[]; self.next_read=now+self.options['interval_seconds']

    def work(self, now):
        with self.lock: snapshot,error=self.snapshot,self.error
        if not self.options['enabled']:
            return WorkEvidenceRead((),observation(self.source,now,limitations=('disabled',),
                details={'enabled':False}))
        if self.closed and not error: error='reader_closed'
        if snapshot is None:
            state=A.AUTH_REQUIRED if error=='auth_required' else A.OFFLINE if error else A.MISSING
            return WorkEvidenceRead((),observation(self.source,now,availability=state,
                connection=C.AUTH_REQUIRED if error=='auth_required' else C.DISCONNECTED if error else C.UNKNOWN,
                limitations=(error or 'snapshot_pending',),details={'enabled':True}))
        result=project_hub(self.source,*snapshot,now,self.options['ttl_seconds'])
        if error:
            state=A.AUTH_REQUIRED if error=='auth_required' else A.OFFLINE
            obs=replace(result.observation,availability=state,connection=C.AUTH_REQUIRED if error=='auth_required' else C.DISCONNECTED,
                        limitations=(*result.observation.limitations,error))
            return WorkEvidenceRead(tuple(replace(e,availability=state,connection=obs.connection) for e in result.evidence),obs)
        return result

    def read(self, query):
        if query: raise ValueError('Hub does not accept query fields')
        return source_result(self.work(datetime.now(timezone.utc)))


def source_result(result, *, as_of=None):
    result = bounded_evidence(result, 8000)
    o=result.observation
    as_of = as_of or datetime.now(timezone.utc)
    return {'contract':'kuro.core.integration.readonly.v1','sourceId':o.integration_id,
        'availability':o.availability.value,'freshness':o.effective_freshness(as_of=as_of).value,
        'connection':o.connection.value,'observedAt':isoformat_utc(o.observed_at),
        'receivedAt':isoformat_utc(o.received_at),'projectedAt':isoformat_utc(as_of),
        'validUntil':isoformat_utc(o.valid_until),
        'limitations':list(o.limitations),'details':dict(o.details),
        'evidence':[e.to_dict() for e in result.evidence]}


def bounded_evidence(result, budget):
    """Bound output, not the retained snapshot. Never silently drop work evidence."""
    kept=[]; used=0
    for evidence in result.evidence:
        size=len(json.dumps(evidence.to_dict(),ensure_ascii=False,allow_nan=False).encode('utf-8'))
        if used+size>budget: break
        kept.append(evidence); used+=size
    if len(kept)==len(result.evidence): return result
    observation=result.observation
    state=A.PARTIAL if observation.availability is A.AVAILABLE else observation.availability
    observation=replace(observation,availability=state,
        limitations=tuple(dict.fromkeys((*observation.limitations,'output_budget_exceeded'))),
        details={**observation.details,'evidenceTotal':len(result.evidence),
            'evidenceReturned':len(kept),'hasMore':True})
    return WorkEvidenceRead(tuple(replace(e,availability=state) for e in kept),observation)


def project_hub(source, responses, received, now, ttl):
    if source not in HUBS or len(responses)!=3: raise ValueError('Hub source/parts invalid')
    summary,due,plan=responses
    if any(not isinstance(p,dict) or p.get('ok') is not True for p in responses): raise ValueError('Hub response invalid')
    if not isinstance(summary.get('summary'),dict): raise ValueError('Hub summary invalid')
    for p in (due,plan):
        if not isinstance(p.get('items'),list) or len(p['items'])>20 or type(p.get('count')) is not int or p['count']!=len(p['items']):
            raise ValueError('Hub items/count invalid')
    limits=[]; metrics={}
    for key in ('items','attempts','due_reviews','practice_sessions'):
        value=summary['summary'].get(key)
        if source=='japanese_study' and key=='items':
            # Japanese canonical summary owns items.total; English owns scalar items.
            value=value.get('total') if isinstance(value,dict) else None
        if type(value) is int and 0<=value<=10000000: metrics[key]=value
        elif key in summary['summary']: limits.append('summary_'+key+'_invalid')
    stamp=timestamp(due.get('as_of'))
    if stamp and stamp>received: raise ValueError('Hub future timestamp')
    if stamp is None: limits.append('source_observed_at_missing')
    if len(due['items'])==20 or len(plan['items'])==20: limits.append('bounded_page_may_be_partial')
    until=(stamp or received)+timedelta(seconds=ttl)
    freshness=F.STALE if now>until else F.CURRENT if stamp else F.UNKNOWN
    facts=[]
    for bucket,body in (('due_reviews',due),('plan',plan)):
        seen=set()
        for rank,item in enumerate(body['items']):
            if not isinstance(item,dict): raise ValueError('Hub item invalid')
            uid=stable_id(item.get('item_id')); title=bounded_text(item.get('title'),240)
            if not uid or not title or uid in seen: raise ValueError('Hub item identity invalid')
            seen.add(uid)
            item_stamp=timestamp(item.get('updated_at'))
            if item_stamp and item_stamp>received: raise ValueError('Hub future item')
            raw_due=item.get('due_at')
            if source=='japanese_study' and bucket=='plan' and isinstance(item.get('srs'),dict): raw_due=item['srs'].get('due_at')
            due_at=timestamp(raw_due)
            if raw_due not in (None,'') and due_at is None: raise ValueError('Hub due timestamp invalid')
            source_stamp=stamp if bucket=='due_reviews' else item_stamp
            item_until=(source_stamp or received)+timedelta(seconds=ttl)
            if source_stamp is None and 'item_observed_at_missing' not in limits: limits.append('item_observed_at_missing')
            metadata={'bucket':bucket,'sourceRank':rank,'sourceObservedAt':isoformat_utc(source_stamp),
                      'timestampBasis':'source' if source_stamp else 'retrieval', 'sourceKind':bounded_text(item.get('kind'),40)}
            if source=='english_study': metadata['cefrLevel']=bounded_text(item.get('cefr_level'),16)
            else: metadata['jlptLevel']=bounded_text(item.get('jlpt_level'),16)
            if bucket=='plan': metadata['sourceReason']=bounded_text(item.get('reason'),120)
            key=identity(source,'item',uid)
            facts.append(dict(evidence_id=identity(source,bucket,uid),integration_id=source,kind=EvidenceKind.STUDY_ITEM,
                source_ref=source+':'+uid,dedup_key=key,title=title,summary=bounded_text(item.get('meaning_tc'),240),
                action_kind=ActionKind.STUDY,required=bucket=='due_reviews',due_at=due_at,
                observed_at=source_stamp or received,received_at=received,valid_until=item_until,
                freshness=F.STALE if now>item_until else F.CURRENT if source_stamp else F.UNKNOWN,
                connection=C.CONNECTED,metadata=metadata))
    availability=A.PARTIAL if limits else A.AVAILABLE
    obs=observation(source,received,stamp=stamp,until=until,availability=availability,freshness=freshness,
        connection=C.CONNECTED,limitations=limits,details={'metrics':metrics,'snapshotReceivedAt':isoformat_utc(received),
            'fetchedAt':isoformat_utc(received),'enabled':True,
            'countsAreNotTasks':True,'schemaOwner':HUBS[source][0]})
    return WorkEvidenceRead(tuple(SourceEvidence(**f,availability=availability) for f in facts),obs)
