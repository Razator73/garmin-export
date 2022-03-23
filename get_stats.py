#!/usr/bin/env pipenv-shebang
import argparse
import datetime as dt
import json
import os

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
    browser.save_screenshot('password_submit.png')
    password.submit()

    if metric_ids is None:
        metric_ids = {
            "22": "WELLNESS_ACTIVE_CALORIES", "23": "WELLNESS_BMR_CALORIES", "25": "FOOD_CALORIES_REMAINING",
            "28": "WELLNESS_TOTAL_CALORIES", "29": "WELLNESS_TOTAL_STEPS", "38": "WELLNESS_TOTAL_STEP_GOAL",
            "39": "WELLNESS_TOTAL_DISTANCE", "40": "WELLNESS_AVERAGE_STEPS", "41": "COMMON_TOTAL_CALORIES",
            "42": "COMMON_ACTIVE_CALORIES", "43": "COMMON_TOTAL_DISTANCE", "51": "WELLNESS_MODERATE_INTENSITY_MINUTES",
            "52": "WELLNESS_VIGOROUS_INTENSITY_MINUTES", "53": "WELLNESS_FLOORS_ASCENDED",
            "54": "WELLNESS_FLOORS_DESCENDED", "55": "WELLNESS_USER_INTENSITY_MINUTES_GOAL",
            "56": "WELLNESS_USER_FLOORS_ASCENDED_GOAL", "57": "WELLNESS_MIN_HEART_RATE",
            "58": "WELLNESS_MAX_HEART_RATE", "60": "WELLNESS_RESTING_HEART_RATE", "63": "WELLNESS_AVERAGE_STRESS",
            "64": "WELLNESS_MAX_STRESS", "82": "WELLNESS_MIN_AVG_HEART_RATE", "83": "WELLNESS_MAX_AVG_HEART_RATE",
            "84": "WELLNESS_BODYBATTERY_CHARGED", "85": "WELLNESS_BODYBATTERY_DRAINED",
            "86": "WELLNESS_ABNORMALHR_ALERTS_COUNT"
        }

        metric_ids_str = '&metricId='.join([str(x) for x in metric_ids.keys()])
    else:
        metric_ids_str = '&metricId='.join([str(x) for x in metric_ids])
    browser.save_screenshot('stats_before.png')
    browser.get(base_url + '/proxy/userstats-service/wellness/daily/hunterzero73?'
                           f'fromDate={start_date.isoformat()}&untilDate={end_date.isoformat()}'
                           f'&metricId={metric_ids_str}&grpParentActType=false')
    browser.save_screenshot('stats_after.png')
    try:
        metrics_map = json.loads(browser.find_element(By.XPATH, '//body').text)['allMetrics']['metricsMap']
    except KeyError:
        browser.quit()
        display.stop()
        raise
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
        for old_col, new_col in rename_cols.items():
            day_data[new_col] = day_data.pop(old_col)
        garmin_data.append(day_data)
    return garmin_data


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
    for day_stat in garmin_stats:
        if (day_row := session.query(GarminStat).filter_by(date=day_stat['date'])).first():
            day_row.update(day_stat)
        else:
            session.add(GarminStat(**day_stat))
    session.commit()
    session.close()
