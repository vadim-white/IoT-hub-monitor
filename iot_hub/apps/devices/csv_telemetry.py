"""Load real 30-day telemetry from CSV when a new device is created."""
import os
import random
from datetime import datetime, timezone as dt_timezone, timedelta, date

# Columns available per device-type keyword (matched against device_type.name.lower())
DEVICE_TYPE_COLUMNS = {
    'температура': ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T_out'],
    'влажность':   ['RH_1', 'RH_2', 'RH_3', 'RH_4', 'RH_5', 'RH_6', 'RH_7', 'RH_8', 'RH_9'],
    'давление':    ['Press_mm_hg'],
    'роз':         ['Appliances'],
    'led':         ['lights'],
    'контролл':    ['Windspeed'],
}

DEFAULT_COLUMNS = ['T1', 'T2', 'T3', 'T_out']

# CSV spans 2016-01-11 to 2016-05-27 (~136 days); pick random 30-day window
CSV_FIRST_DAY = date(2016, 1, 11)
CSV_LAST_DAY  = date(2016, 5, 27)
WINDOW_DAYS   = 30


def _get_csv_path():
    # Try Django BASE_DIR first (most reliable)
    try:
        from django.conf import settings
        candidate = os.path.join(str(settings.BASE_DIR), 'energydata_complete.csv')
        if os.path.exists(candidate):
            return candidate
    except Exception:
        pass

    # Walk up from this file's location
    base = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        candidate = os.path.join(base, 'energydata_complete.csv')
        if os.path.exists(candidate):
            return candidate
        base = os.path.dirname(base)
    return None


def _pick_column(device_type_name: str) -> str:
    name = (device_type_name or '').lower()
    for key, cols in DEVICE_TYPE_COLUMNS.items():
        if key in name:
            return random.choice(cols)
    return random.choice(DEFAULT_COLUMNS)


def load_csv_telemetry_for_device(device):
    """
    Load a random 30-day window of real CSV telemetry into the device's first metric.
    Silently skips if CSV is missing, metric is missing, or telemetry already exists.
    """
    from iot_hub.apps.telemetry.models import Telemetry

    if Telemetry.objects.filter(device=device).exists():
        return

    metric = device.metrics.first()
    if not metric:
        return

    csv_path = _get_csv_path()
    if not csv_path:
        return

    try:
        import pandas as pd
    except ImportError:
        return

    try:
        df = pd.read_csv(csv_path, parse_dates=['date'])
    except Exception:
        return

    device_type_name = device.device_type.name if device.device_type else ''
    csv_column = _pick_column(device_type_name)

    if csv_column not in df.columns:
        csv_column = random.choice(DEFAULT_COLUMNS)
    if csv_column not in df.columns:
        return

    # Pick a random start day that leaves room for a full 30-day window
    max_offset = (CSV_LAST_DAY - CSV_FIRST_DAY).days - WINDOW_DAYS
    if max_offset <= 0:
        offset = 0
    else:
        offset = random.randint(0, max_offset)

    window_start = CSV_FIRST_DAY + timedelta(days=offset)
    window_end   = window_start + timedelta(days=WINDOW_DAYS - 1)

    ts_start = pd.Timestamp(window_start)
    ts_end   = pd.Timestamp(window_end) + pd.Timedelta(hours=23, minutes=59)

    period_data = df[(df['date'] >= ts_start) & (df['date'] <= ts_end)].copy()
    if period_data.empty:
        return

    daily_avg = period_data.groupby(period_data['date'].dt.date)[csv_column].agg(['mean', 'std', 'count'])

    telemetries = []
    for day, row in daily_avg.iterrows():
        try:
            naive_dt = datetime(day.year, day.month, day.day, 12, 0, 0)
            recorded_at = naive_dt.replace(tzinfo=dt_timezone.utc)
            value = float(row['mean'])
            std_val   = float(row['std'])   if not pd.isna(row['std'])   else 0.0
            count_val = int(row['count'])   if not pd.isna(row['count']) else 0

            telemetries.append(Telemetry(
                device=device,
                metric=metric,
                value=round(value, 4),
                unit=metric.unit,
                status='ok',
                recorded_at=recorded_at,
                raw_data={'std': std_val, 'count': count_val, 'csv_column': csv_column},
            ))
        except Exception:
            continue

    if telemetries:
        Telemetry.objects.bulk_create(telemetries, batch_size=500)
