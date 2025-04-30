import streamlit as st
import pandas as pd
import datetime
import asyncio
import aiohttp
from multiprocessing import Pool, cpu_count

# --- Season mapping ---
month_to_season = {
    12: 'winter', 1: 'winter', 2: 'winter',
    3: 'spring', 4: 'spring', 5: 'spring',
    6: 'summer', 7: 'summer', 8: 'summer',
    9: 'autumn', 10: 'autumn', 11: 'autumn'
}

# --- Helper functions ---

def load_historical_data(uploaded_file):
    df = pd.read_csv(uploaded_file, parse_dates=["timestamp"])
    df['season'] = df['timestamp'].dt.month.map(month_to_season)
    return df

@st.cache_data
def compute_stats(df, window=30):
    df_sorted = df.sort_values('timestamp')
    df_sorted['rolling_mean'] = df_sorted['temperature'].rolling(window).mean()
    df_sorted['rolling_std'] = df_sorted['temperature'].rolling(window).std()
    return df_sorted

@st.cache_data
def seasonal_summary(df):
    return df.groupby(['city', 'season'])['temperature'] \
             .agg(['mean', 'std']).reset_index()

@st.cache_data
def find_anomalies(df):
    df = df.copy()
    df['anomaly'] = ((df['temperature'] > df['rolling_mean'] + 2*df['rolling_std']) |
                     (df['temperature'] < df['rolling_mean'] - 2*df['rolling_std']))
    return df


def analyze_parallel(data_groups):
    with Pool(cpu_count()) as pool:
        return pool.map(lambda x: find_anomalies(compute_stats(x[1])), data_groups)

# Fetch current temperature asynchronously
async def fetch_current_temp_async(city, api_key):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&units=metric&appid={api_key}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()


st.title("Анализ температур и мониторинг климата")

# File uploader
uploaded = st.file_uploader("Загрузите исторические данные (CSV)", type='csv')
if uploaded:
    df = load_historical_data(uploaded)
    cities = df['city'].unique().tolist()
    city = st.selectbox("Выберите город", cities)

    # Seasonal summary
    summary = seasonal_summary(df[df['city'] == city])
    st.subheader("Сезонная статистика")
    st.dataframe(summary)

    # Rolling and anomalies
    df_city = df[df['city'] == city]
    df_stats = compute_stats(df_city)
    df_ano = find_anomalies(df_stats)

    st.subheader("Температура и аномалии")
    st.line_chart(df_stats.set_index('timestamp')['rolling_mean'])
    st.scatter_chart(df_ano[df_ano['anomaly']].set_index('timestamp')['temperature'])


    # API key input
    api_key = st.text_input("OpenWeatherMap API Key", type="password")
    if api_key:
        if st.button("Получить текущую температуру"):
             data = asyncio.run(fetch_current_temp_async(city, api_key))
             if data.get('cod') == 200:
                temp = data['main']['temp']
                st.write(f"Текущая температура в {city}: {temp} °C")
                # Compare to historical range
                month_num = datetime.datetime.utcnow().month
                season_name = month_to_season[month_num]
                row = summary[summary['season'] == season_name]
                mean, std = row[['mean', 'std']].values[0]
                lower, upper = mean - 2*std, mean + 2*std
                st.write(f"Норма для сезона ({season_name}): {lower:.1f} - {upper:.1f} °C")
                st.write("Аномалия!" if not (lower <= temp <= upper) else "В пределах нормы")
             else:
                st.error(data.get('message', 'Ошибка при запросе'))