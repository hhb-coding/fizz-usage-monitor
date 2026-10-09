"""Read-only per-account alerts / 每个账号独立计算，只读告警。"""
from datetime import date, datetime, timedelta


def evaluate_alerts(account, now, threshold_mb=1000, stale_hours=36):
    """Unknown/stale data must never produce a green status.
    缺失、陈旧或失败的数据绝不能显示绿色正常状态。
    """
    notices = []
    status = account['status']
    total = account['total_available_mb']
    batches = account.get('bucket_snapshot', [])
    unknown = total is None or not batches or not status.get('last_success_at')
    stale = bool(account['stale'])
    for batch in batches:
        try:
            stamp = datetime.fromisoformat(batch['collected_at'])
            if stamp.tzinfo is None or stamp > now:
                unknown = True
            elif now - stamp > timedelta(hours=stale_hours):
                stale = True
        except (ValueError, TypeError, KeyError):
            unknown = True
        days = (date.fromisoformat(batch['expires_on']) - now.date()).days
        if batch['remaining_mb'] > 0:
            if days < 0:
                notices.append({'kind':'expiry', 'text':f"{batch['kind']} 批次已过期（{batch['expires_on']}），已排除于总量。"})
            elif days <= 3:
                notices.append({'kind':'expiry', 'text':f"{batch['kind']} 批次将在 {days} 天内到期（{batch['expires_on']}），剩余 {batch['remaining_mb']} MB。"})
    if status.get('failed'):
        label, level = '未知：最近采集失败', 'unknown'
    elif stale:
        label, level = '过期：数据陈旧，请更新', 'unknown'
    elif unknown:
        label, level = '未知：缺少可验证的流量数据', 'unknown'
    elif total < threshold_mb:
        label, level = f'低流量警告：剩余不足 {threshold_mb} MB', 'low'
    elif notices:
        label, level = '注意：流量有效期提醒', 'expiry'
    else:
        label, level = '正常：剩余流量充足', 'normal'
    return {'level':level, 'label':label, 'notices':notices,
            'reliable':not (unknown or stale or status.get('failed'))}
