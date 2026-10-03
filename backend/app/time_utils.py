from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')


def today_kst() -> date:
    return datetime.now(KST).date()


def date_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, KST)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Timezone-aware Telegram timestamp required')
    return value
