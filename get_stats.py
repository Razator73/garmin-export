#!/usr/bin/env pipenv-shebang
import argparse
import datetime as dt
import json
import os

import pandas as pd
from dotenv import load_dotenv
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.common.by import By

from model import GarminStat, init_db


def get_garmin_stats(start_date=None, end_date=None, metric_ids=None):
    start_date = dt.date.today() - dt.timedelta(days=1) if not start_date else start_date
    end_date = dt.date.today() - dt.timedelta(days=1) if not end_date else end_date
    start_date = dt.date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
    end_date = dt.date.fromisoformat(end_date) if isinstance(end_date, str) else end_date
    if (not isinstance(start_date, dt.date)) or (not isinstance(end_date, dt.date)):
        raise TypeError('Start or End date have to be datetime objects or iso date strings (yyyy-dd-mm)')
    start_date, end_date = (end_date, start_date) if end_date < start_date else (start_date, end_date)

    # browser_opts = webdriver.ChromeOptions()
    # browser_opts.headless = False
    # browser = webdriver.Chrome(options=browser_opts)
    display = Display(visible=False)
    display.start()
    browser = webdriver.Chrome()

    base_url = 'https://connect.garmin.com'
    better_signin_url = 'https://sso.garmin.com/sso/signin?webhost=https%3A%2F%2Fconnect.garmin.com' \
                        '&service=https%3A%2F%2Fconnect.garmin.com&source=https%3A%2F%2Fsso.garmin.com%2Fsso%2Fsignin'

    browser.get(better_signin_url)
    browser.find_element(By.ID, 'username').send_keys(os.getenv('GARMIN_SIGNIN_EMAIL'))
    password = browser.find_element(By.ID, 'password')
    password.send_keys(os.getenv('GARMIN_SIGNIN_PASSWORD'))
    password.submit()
    browser.save_screenshot('password_submit.png')

    if metric_ids is None:
        with open('wellness_ids.json') as f:
            metric_ids = json.load(f)

        metric_ids_str = '&metricId='.join([str(x) for x in metric_ids.keys()])
    else:
        metric_ids_str = '&metricId='.join([str(x) for x in metric_ids])
    browser.save_screenshot('stats_before.png')
    browser.get(base_url + '/proxy/userstats-service/wellness/daily/hunterzero73?'
                           f'fromDate={start_date.isoformat()}&untilDate={end_date.isoformat()}'
                           f'&metricId={metric_ids_str}&grpParentActType=false')
    browser.save_screenshot('stats_after.png')
    metrics_map = json.loads(browser.find_element(By.XPATH, '//body').text)['allMetrics']['metricsMap']
    day_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    rename_cols = {'wellness_total_steps': 'total_steps', 'wellness_total_step_goal': 'step_goal'}
    browser.quit()
    display.stop()

    garmin_data = []
    for i in range((end_date - start_date).days + 1):
        check_day = start_date + dt.timedelta(days=i)
        day_data = {'date': check_day, 'day_of_week': day_of_week[check_day.weekday()]}
        for metric, data in metrics_map.items():
            try:
                metric_value = [x for x in data if x['calendarDate'] == check_day.isoformat()][0]['value']
                day_data[metric.lower()] = int(metric_value) if metric_value else 0
            except IndexError:
                day_data[metric.lower()] = 0
        garmin_data.append(day_data)
    garmin_df = pd.DataFrame(garmin_data)
    garmin_df.rename(columns=rename_cols, inplace=True)
    garmin_df = garmin_df[garmin_df.total_steps != 0]
    # garmin_df['met_step_goal'] = (garmin_df.total_steps >= garmin_df.step_goal) & (garmin_df.step_goal != 0)
    garmin_df['date'] = pd.to_datetime(garmin_df.date)
    return garmin_df


if __name__ == '__main__':
    load_dotenv()
    if not os.getenv('GARMIN_SIGNIN_EMAIL'):
        raise KeyError('Please make sure GARMIN_SIGNIN_EMAIL is set in the environment variables')
    if not os.getenv('GARMIN_SIGNIN_PASSWORD'):
        raise KeyError('Please make sure GARMIN_SIGNIN_PASSWORD is set in the environment variables')
    if not os.getenv('GARMIN_DATABASE_PATH'):
        raise KeyError('Please make sure GARMIN_DATABASE_PATH is set in the environment variables')
    arg_parser = argparse.ArgumentParser(prog='garmin_export', description='Scrape my garmin stats')
    arg_parser.add_argument('-f', '--from_date', default=None, help='Start date for the stats (default yesterday)')
    arg_parser.add_argument('-e', '--end_date', default=None, help='End date for the stats (default yesterday)')
    arg_parser.add_argument('-i', '--metric_ids', nargs='+', help='The metric ids to be pulled')
    args = arg_parser.parse_args()

    garmin_stats = get_garmin_stats(start_date=args.from_date, end_date=args.end_date, metric_ids=args.metric_ids)

    session = init_db(os.getenv('GARMIN_DATABASE_PATH'))
    for day_stat in garmin_stats.to_dict('records'):
        if (day_row := session.query(GarminStat).filter_by(date=day_stat['date'])).first():
            day_row.update(day_stat)
        else:
            session.add(GarminStat(**day_stat))
    session.commit()
    session.close()
