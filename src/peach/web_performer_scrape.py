"""独立女优档案与头像补全，影片资料与媒体读取流水线保持独立。"""
from __future__ import annotations

from pathlib import Path
import contextlib
import sqlite3
import time

from . import avatar_followup, avatar_picker, gfriends, performer_profile_followup as profiles
from .jobs import DiskGuard, TaskRunConflict
from .migrations import sqlite_backup
from .performer_profiles import read_profile

TASK = 'performer-scrape'
MAX_IDS = 100000


def _targets(contract, body):
    raw = body.get('entity_ids')
    all_people = body.get('all') is True
    if all_people == (raw is not None):
        raise ValueError('请选择单个女优、指定女优或全部女优')
    with contract.read_connection() as db:
        if all_people:
            return [int(row[0]) for row in db.execute(
                "SELECT e.id FROM entity e JOIN asset_entity ae ON ae.entity_id=e.id "
                "JOIN asset a ON a.id=ae.asset_id WHERE e.kind='performer' "
                "AND a.medium='video' AND a.disposal IS NULL GROUP BY e.id "
                "ORDER BY count(DISTINCT a.id) DESC,e.id")]
        if (not isinstance(raw, list) or not raw or len(raw) > MAX_IDS
                or any(type(value) is not int or value <= 0 for value in raw)):
            raise ValueError('女优编号必须是正整数列表，至多100000位')
        wanted = list(dict.fromkeys(raw))
        found = set()
        for offset in range(0, len(wanted), 500):
            chunk = wanted[offset:offset + 500]
            found.update(int(row[0]) for row in db.execute(
                f"SELECT id FROM entity WHERE kind='performer' AND id IN ({','.join('?' for _ in chunk)})", chunk))
        if found != set(wanted):
            raise ValueError('部分女优档案已不存在或身份类型不匹配')
        return wanted


def q_performer_scrape(contract, _args):
    return contract.performer_scrape_job.snapshot() or {'status': 'idle'}


def w_performer_scrape(contract, body):
    job = contract.performer_scrape_job
    state = job.snapshot() or {}
    action = body.get('action', 'start')
    if action in ('stop', 'retry'):
        if not body.get('job_id') or body['job_id'] != state.get('job_id'):
            raise ValueError('任务已变化，请刷新后重试')
        if action == 'stop':
            if state.get('status') != 'running':
                return state
            job.update(state['job_id'], stop_requested=True, message='当前女优处理结束后停止')
            return job.snapshot()
        if state.get('status') == 'running':
            raise ValueError('请等待当前任务结束')
        ids = list(dict.fromkeys([*state.get('retry_ids', []),
            *(value for value in state.get('entity_ids', []) if value not in state.get('completed_ids', []))]))
        if not ids:
            raise ValueError('没有待重试的女优')
        body = {**body, 'all': False, 'entity_ids': ids}
    elif action != 'start':
        raise ValueError('无法识别女优采集操作')
    if body.get('confirmed') is not True:
        raise ValueError('刮削女优资料需要确认')
    ids = _targets(contract, body)
    if not ids:
        raise ValueError('媒体库中没有可补全的女优')
    if state.get('status') == 'running' and state.get('entity_ids') != ids:
        raise TaskRunConflict(TASK, state.get('run_id'))
    return job.start(lambda identity: _run(contract, identity), restart=True,
        initial={'entity_ids': ids, 'completed_ids': [], 'retry_ids': [], 'results': [],
                 'checked': 0, 'total': len(ids), 'profiles': 0, 'avatars': 0, 'failed': 0,
                 'stop_requested': False, 'message': '准备刮削女优资料'},
        recovery={'confirmed': True, 'entity_ids': ids})


class _Handle:
    def __init__(self, job, identity):
        self.job, self.identity = job, identity
        self.run_id = (job.snapshot() or {}).get('run_id') or identity

    def progress(self, **values):
        self.job.update(self.identity, message=values.get('label') or '正在刮削女优资料')


def _profile(contract, entity_id):
    with contract.read_connection() as db:
        found = read_profile(db, entity_id) or {}
    return {key: value for key, value in found.items()
            if key not in ('entity_id', 'source', 'source_url', 'fetched_at')
            and value not in (None, '', [], {})}


def _collect(contract, entity_id, handle):
    with contract.read_connection() as db:
        row = db.execute("SELECT canonical_name FROM entity WHERE id=? AND kind='performer'", (entity_id,)).fetchone()
    if row is None:
        return {'entity_id': entity_id, 'name': '', 'profile': False, 'avatar': False,
                'retryable': False, 'message': '女优档案已不存在'}
    before_profile = _profile(contract, entity_id)
    before_avatar = avatar_picker.installed_digest(contract.avatar_root, 'performer', entity_id)
    failures, messages = [], []
    try:
        summary = profiles.run(contract, profiles.followup_key(entity_id), handle, fill_missing=True)
        messages.append(str(summary.get('outcome') or '档案未取得'))
        if any(str(value).startswith(profiles.UNFETCHED) for value in summary.get('sites', {}).values()):
            failures.append('档案来源暂不可用')
    except Exception:
        failures.append('档案采集失败，请重试')
    try:
        summary = avatar_followup.run(contract, avatar_followup.followup_key('performer', entity_id), handle)
        messages.append(str(summary.get('outcome') or '头像未取得'))
        if summary.get('source_unavailable') or summary.get('face_match_unavailable'):
            failures.append('头像来源或匹配服务暂不可用')
    except Exception:
        failures.append('头像采集失败，请重试')
    after_profile = _profile(contract, entity_id)
    after_avatar = avatar_picker.installed_digest(contract.avatar_root, 'performer', entity_id)
    changed_profile = before_profile != after_profile
    changed_avatar = bool(after_avatar and before_avatar != after_avatar)
    unresolved = not after_profile or not after_avatar
    return {'entity_id': entity_id, 'name': str(row[0]), 'profile': changed_profile,
            'avatar': changed_avatar, 'retryable': bool(failures) or unresolved,
            'message': '；'.join([*messages, *failures])[:400]}


def _run(contract, identity):
    job = contract.performer_scrape_job
    state = job.snapshot() or {}
    guard = DiskGuard(contract.candidate_root, .25)
    guard.check(force=True)
    backup = Path(contract.db_path).parent / f'ledger.pre-performer-scrape-{identity}.db'
    if not state.get('backup'):
        if not backup.exists():
            sqlite_backup(Path(contract.db_path), backup)
        with contextlib.closing(sqlite3.connect(backup)) as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or not db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='asset'").fetchone():
                raise ValueError('数据库备份未通过完整性检查，已停止采集')
        if not job.checkpoint(identity, backup=str(backup)):
            return
    if not state.get('index_ready'):
        fresh = gfriends.ensure_index(Path(contract.candidate_root) / 'provider-cache' / 'performer-avatars' / avatar_picker.GFRIENDS_CACHE)
        if not job.checkpoint(identity, index_ready=True, index_fresh=fresh):
            return
    handle = _Handle(job, identity)
    streak = 0
    for entity_id in state.get('entity_ids', []):
        current = job.snapshot() or {}
        if current.get('job_id') != identity:
            return
        if current.get('stop_requested'):
            contract.cache_bust()
            job.update(identity, status='complete', stopped=True, message='已停止刮削女优资料', completed_at=time.time())
            return
        if entity_id in current.get('completed_ids', []):
            continue
        guard.check()
        if not job.checkpoint(identity, current_entity_id=entity_id, message='正在刮削女优资料'):
            return
        result = _collect(contract, entity_id, handle)
        current = job.snapshot() or {}
        if current.get('job_id') != identity:
            return
        done = [*current.get('completed_ids', []), entity_id]
        retry = [*current.get('retry_ids', []), *([entity_id] if result['retryable'] else [])]
        if not job.checkpoint(identity, completed_ids=done, retry_ids=retry, checked=len(done),
            profiles=current.get('profiles', 0) + int(result['profile']),
            avatars=current.get('avatars', 0) + int(result['avatar']), failed=len(retry),
            results=[*current.get('results', []), result]):
            return
        streak = streak + 1 if result['retryable'] else 0
        if streak >= 5:
            contract.cache_bust()
            job.update(identity, status='failed', error='连续5位未取得完整结果，请检查来源连接后重试', completed_at=time.time())
            return
    contract.cache_bust()
    job.update(identity, status='complete', message='已完成女优资料刮削', completed_at=time.time())
