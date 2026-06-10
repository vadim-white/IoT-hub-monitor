"""Profile extractor — извлекает статистические профили метрик из реальных датасетов
в JSON, на которых работает генератор телеметрии (generate_telemetry).

Запуск (из venv с pandas):
    .venv-analysis/bin/python tools/extract_profiles.py

Выход: iot_hub/apps/telemetry/profiles/*.json — по одному профилю на тип метрики.
Структура профиля и калибровка — см. SIMULATOR_DESIGN.md / DATASETS_ANALYSIS.md.

Профиль НЕ хранит сырые данные — только параметры формы сигнала:
  base_mean/base_std, daily (амплитуда+фаза суточного хода),
  seasonal (годовой ход, опц.), ar1_coef (гладкость), clip (физ. границы), leads.
"""
import os
import json
import math
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASETS = os.path.join(ROOT, "datasets")
OUT = os.path.join(ROOT, "iot_hub", "apps", "telemetry", "profiles")
os.makedirs(OUT, exist_ok=True)


# ──────────────────────────────────────────────
# Общие статистические функции профиля
# ──────────────────────────────────────────────

def ar1_coef(series: pd.Series) -> float:
    """AR(1)-коэффициент = автокорреляция lag-1. Гладкость сигнала."""
    s = series.dropna().to_numpy(dtype=float)
    if len(s) < 2:
        return 0.0
    m = s.mean()
    d = s - m
    den = (d * d).sum()
    if den == 0:
        return 0.0
    return float((d[1:] * d[:-1]).sum() / den)


def daily_shape(dt: pd.Series, val: pd.Series):
    """Суточный ход: амплитуда (макс-мин среднего по часу) и час пика."""
    df = pd.DataFrame({"h": dt.dt.hour, "v": val}).dropna()
    if df.empty:
        return None
    by_hour = df.groupby("h")["v"].mean()
    return {
        "amplitude": float(by_hour.max() - by_hour.min()),
        "peak_hour": int(by_hour.idxmax()),
        "trough_hour": int(by_hour.idxmin()),
    }


def seasonal_shape(dt: pd.Series, val: pd.Series):
    """Годовой ход: средние по месяцам, мин/макс месяц, амплитуда."""
    df = pd.DataFrame({"m": dt.dt.month, "v": val}).dropna()
    if df["m"].nunique() < 6:  # меньше полугода — сезонность недостоверна
        return None
    by_month = df.groupby("m")["v"].mean()
    return {
        "period": "year",
        "min_month": int(by_month.idxmin()),
        "max_month": int(by_month.idxmax()),
        "amplitude": float(by_month.max() - by_month.min()),
        "by_month": {int(k): round(float(v), 2) for k, v in by_month.items()},
    }


def base_profile(metric_type, unit, dt, val, leads=None, source=""):
    s = val.dropna()
    prof = {
        "metric_type": metric_type,
        "unit": unit,
        "source": source,
        "base_mean": round(float(s.mean()), 4),
        "base_std": round(float(s.std(ddof=0)), 4),
        "ar1_coef": round(ar1_coef(val), 4),
        "min_clip": round(float(s.min()), 4),
        "max_clip": round(float(s.max()), 4),
        "leads": leads,
    }
    if dt is not None:
        d = daily_shape(dt, val)
        if d:
            prof["daily"] = d
        se = seasonal_shape(dt, val)
        if se:
            prof["seasonal"] = se
    return prof


def save(prof, name):
    path = os.path.join(OUT, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prof, f, ensure_ascii=False, indent=2)
    daily = prof.get("daily", {})
    print(f"  ✓ {name:<22} mean={prof['base_mean']:<9} std={prof['base_std']:<8} "
          f"ar1={prof['ar1_coef']:<7} "
          f"{'суткиΔ'+str(round(daily.get('amplitude',0),1)) if daily else ''}")


# ──────────────────────────────────────────────
# 1. RP5 — уличные temperature / humidity (климат РФ)
# ──────────────────────────────────────────────

def extract_rp5():
    print("RP5 (улица, климат РФ):")
    f = [x for x in os.listdir(DATASETS) if "БАЛЧУГ" in x and x.endswith(".csv")][0]
    path = os.path.join(DATASETS, f)
    # rp5-выгрузка: в строке-заголовке на одно имя больше, чем колонок данных,
    # поэтому pandas делает дату-строку ИНДЕКСОМ, а все данные съезжают на -1 позицию.
    # Итог по позициям: iloc[:,0]=температура, [:,1]=Po, [:,2]=P, [:,4]=влажность U.
    df = pd.read_csv(path, sep=";", comment="#", quotechar='"',
                     encoding="utf-8", low_memory=False)
    df["dt"] = pd.to_datetime(df.index.astype(str),
                              format="%d.%m.%Y %H:%M", errors="coerce")
    df = df.sort_values("dt")
    temp = pd.to_numeric(df.iloc[:, 0], errors="coerce")   # температура
    hum = pd.to_numeric(df.iloc[:, 4], errors="coerce")    # влажность U
    save(base_profile("temperature", "°C", df["dt"], temp,
                      leads=None, source="rp5_moscow_2025"), "temperature_outdoor")
    save(base_profile("humidity", "%", df["dt"], hum,
                      leads=None, source="rp5_moscow_2025"), "humidity_outdoor")


# ──────────────────────────────────────────────
# 2. energydata — комнатные temperature / humidity / power
# ──────────────────────────────────────────────

def extract_energydata():
    print("energydata (комната, Бельгия):")
    path = os.path.join(DATASETS, "energydata_complete.csv")
    df = pd.read_csv(path)
    df["dt"] = pd.to_datetime(df["date"])
    # T1 — комната (ведомая от улицы), RH_1 — влажность комнаты, Appliances — мощность
    save(base_profile("temperature", "°C", df["dt"], df["T1"],
                       leads="temperature_outdoor", source="energydata_T1"),
         "temperature_indoor")
    save(base_profile("humidity", "%", df["dt"], df["RH_1"],
                       leads=None, source="energydata_RH1"),
         "humidity_indoor")
    save(base_profile("power", "Wh", df["dt"], df["Appliances"],
                       leads=None, source="energydata_Appliances"),
         "power")


# ──────────────────────────────────────────────
# 3. household power — voltage / current
# ──────────────────────────────────────────────

def extract_household():
    print("household power (электрика):")
    path = os.path.join(DATASETS, "household_power_consumption.txt")
    # 2млн строк — читаем нужные колонки, сэмплируем каждую 5-ю для скорости
    df = pd.read_csv(path, sep=";", na_values=["?"],
                     usecols=["Date", "Time", "Voltage", "Global_intensity"],
                     low_memory=False)
    df = df.iloc[::5].copy()
    df["dt"] = pd.to_datetime(df["Date"] + " " + df["Time"],
                              format="%d/%m/%Y %H:%M:%S", errors="coerce")
    df["Voltage"] = pd.to_numeric(df["Voltage"], errors="coerce")
    df["Global_intensity"] = pd.to_numeric(df["Global_intensity"], errors="coerce")
    save(base_profile("voltage", "V", df["dt"], df["Voltage"],
                       leads=None, source="household_voltage"), "voltage")
    save(base_profile("current", "A", df["dt"], df["Global_intensity"],
                       leads=None, source="household_intensity"), "current")


# ──────────────────────────────────────────────
# Запуск всех
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Выход: {OUT}\n")
    extract_rp5()
    extract_energydata()
    extract_household()
    print(f"\nГотово. Профили в {OUT}")
    print("rssi/uptime/error_count — калибруются вручную в генераторе "
          "(см. SIMULATOR_DESIGN.md), отдельных профилей не требуют.")
