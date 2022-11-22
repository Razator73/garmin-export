#!/usr/bin/env pipenv-shebang
import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import razator_utils
from dotenv import load_dotenv
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.common.exceptions import (ElementNotInteractableException, StaleElementReferenceException,
                                        ElementClickInterceptedException)
from selenium.webdriver.common.by import By

from model import GarminStat, Activity, init_db


def wait_for_element(css_selector, driver, timeout):
    """
    Wait for an element to appear on the page.

    :param css_selector: CSS selector for the element. (str)
    :param driver: Selenium WebDriver object. (WebDriver)
    :param timeout: Number of seconds to wait before timing out. (int)

    :return: element: Selenium WebElement object. (WebElement)
    """
    start_time = time.time()
    while True:
        # noinspection PyBroadException
        try:
            element = driver.find_element_by_css_selector(css_selector)
            return element
        except Exception:
            if time.time() - start_time > timeout:
                raise TimeoutError(f'Timed out after {timeout} seconds trying to find {css_selector}.')
            time.sleep(0.5)


def interact_with_element(css_selector, driver, timeout=30, action='click', value=''):
    """
    interact with an element on the page.

    :param css_selector: CSS selector for the element. (str)
    :param driver: Selenium WebDriver object. (WebDriver)
    :param timeout: Number of seconds to wait before timing out. (int)
    :param action: Action to take on the element. Can be 'click' or 'send_keys'. (str)
    :param value: Value to send to the element if action is 'send_keys'. (str)

    :return: element: Selenium WebElement object. (WebElement)
    """
    element = wait_for_element(css_selector, driver, timeout)
    start_time = time.time()
    while True:
        try:
            if action == 'click':
                element.click()
            elif action == 'send_keys':
                element.send_keys(value)
            return element
        except (ElementNotInteractableException, StaleElementReferenceException, ElementClickInterceptedException):
            if time.time() - start_time > timeout:
                raise TimeoutError(f'Timed out after {timeout} seconds trying to interact with {css_selector}.')
            time.sleep(0.5)


def update_activity(act, type_id, browser, base_url, replace_tuple=None):
    """
    Update the activity on Garmin Connect with the new activity type

    :param act: Activity to be edited (dict)
    :param type_id: Type ID to update (int)
    :param browser: Selenium browser object (WebDriver)
    :param base_url: Base URL for Garmin Connect (str)
    :param replace_tuple: Tuple of (old_string, new_string) (tuple)

    :return: None
    """
    browser.get(f"{base_url}/modern/activity/{act['activity_id']}")
    if replace_tuple:
        interact_with_element('[class="inline-edit-trigger modal-trigger"]', browser)
        interact_with_element('[class="inline-edit-editable-text page-title-overflow"]', browser, action='send_keys',
                              value=act['activity_name'].replace(replace_tuple[0], replace_tuple[1]))
        interact_with_element('[class="inline-edit-save icon-checkmark"]', browser)
    interact_with_element('[class="dropdown-toggle active"]', browser)
    interact_with_element(f'[data-value="{type_id}"]', browser)
    try:
        interact_with_element('[class="btn btn-primary js-saveBtn "]', browser, 3)
    except TimeoutError:
        pass


def get_daily_stats(base_url, browser, start_date, end_date, metric_ids,
                    logger=razator_utils.log.get_stout_logger('garmin_daily_stats')):
    """
    Get the daily stats from garmin

    :param base_url: Base URL for Garmin Connect (str)
    :param browser: Browser object (webdriver)
    :param start_date: Start date for activities (datetime.date)
    :param end_date: End date for activities (datetime.date)
    :param metric_ids: Metric IDs to pull (dict {"id": "name"})
    :param logger: Logger object (logging.Logger)

    :return: garmin_data: List of daily stats pulled from garmin (list of dicts)
    """
    start_date = max(start_date, dt.date(2017, 9, 5))
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
    day_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    rename_cols = {'wellness_total_steps': 'total_steps', 'wellness_total_step_goal': 'step_goal'}
    time.sleep(15)
    browser.get(base_url + '/proxy/userstats-service/wellness/daily/hunterzero73?'
                           f'fromDate={start_date.isoformat()}&untilDate={end_date.isoformat()}'
                           f'&metricId={metric_ids_str}&grpParentActType=false')
    try:
        metrics_map = json.loads(browser.find_element(By.XPATH, '//body').text)['allMetrics']['metricsMap']
    except KeyError:
        logger.exception('Metrics didn\'t load properly')
        return []

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
            try:
                day_data[new_col] = day_data.pop(old_col)
            except KeyError:
                logger.exception("Couldn't pull the metrics due to missing column")
                return []
        garmin_data.append(day_data)

    return garmin_data


def get_garmin_activities(base_url, browser, start_date, end_date,
                          logger=razator_utils.log.get_stout_logger('garmin_activities')):
    """
    Get the activities from garmin

    :param base_url: Base URL for Garmin Connect (str)
    :param browser: Selenium browser object (webdriver)
    :param logger: Logger object (logging.Logger)
    :param start_date: Start date for activities (datetime.date)
    :param end_date: End date for activities (datetime.date)

    :return: activities: List of activities pulled from garmin (list of dicts)
    """
    start_date = max(start_date, dt.date(2013, 9, 1))
    start = 0
    limit = 200
    url_activities = base_url + '/proxy/activitylist-service/activities/search/activities'
    acts = []
    while True:
        activities_url = f'{url_activities}?start={start}&limit={limit}'
        logger.debug(activities_url)
        browser.get(activities_url)
        acts_batch = json.loads(browser.find_element(By.XPATH, '//body').text)
        good_rows = [row for row in acts_batch if
                     start_date <= dt.datetime.fromisoformat(row['startTimeLocal']).date() <= end_date]
        if good_rows:
            acts += good_rows
            start += limit
        else:
            break

    logger.info(f'Pulled {len(acts)} activities')

    keep_cols = [
        'activityId', 'activityName', 'startTimeLocal', 'startTimeGMT',
        'activityType', 'eventType', 'distance', 'duration',
        'movingDuration', 'elevationGain', 'elevationLoss', 'averageSpeed',
        'maxSpeed', 'calories',
        'averageHR', 'maxHR',
        'steps', 'timeZoneId',
        'beginTimestamp', 'vO2MaxValue', 'workoutId', 'deviceId',
        'minElevation', 'maxElevation', 'locationName', 'lapCount',
        'caloriesConsumed',
        'minActivityLapDuration', 'hasSplits',
        'moderateIntensityMinutes', 'vigorousIntensityMinutes',
        'pr', 'manualActivity', 'autoCalcCalories', 'elevationCorrected']
    time_columns = ['startTimeLocal', 'startTimeGMT']
    flat_activities = []
    while acts:
        flat_act = razator_utils.flatten_dict({k: v for k, v in acts.pop(0).items() if k in keep_cols})
        rename_columns = {col: razator_utils.camel_to_snake(col) for col in flat_act.keys()}
        for col in time_columns:
            flat_act[col] = dt.datetime.fromisoformat(flat_act[col])
        flat_act = {rename_columns.get(k, k): v for k, v in flat_act.items()}
        del flat_act['activity_type_sort_order']
        if flat_act['activity_type_type_id'] == 4 and 'Disc Golf' in flat_act['activity_name']:
            update_activity(flat_act, 205, browser, base_url)
            flat_act['activity_type_type_id'] = 205
            flat_act['activity_type_type_key'] = 'disc_golf'
            flat_act['activity_type_parent_type_id'] = 4
        flat_activities.append(flat_act)
    return flat_activities


def get_garmin_stats(start_date, end_date, metric_ids=None, show_display=False,
                     logger=razator_utils.log.get_stout_logger('garmin_api')):
    """
    Get the stats from garmin

    :param start_date: Start date for stats (datetime.date)
    :param end_date: End date for stats (datetime.date)
    :param metric_ids: Metric IDs to pull (dict {"id": "name"})
    :param show_display: Show the display (bool)
    :param logger: Logger object (logging.Logger)

    :return: daily_data, activity_data: Daily and activity data from garmin (each a list of dicts)
    """
    start_date, end_date = (end_date, start_date) if end_date < start_date else (start_date, end_date)
    display = Display(visible=show_display)
    display.start()

    base_url = 'https://connect.garmin.com'
    better_signin_url = 'https://sso.garmin.com/sso/signin?webhost=https%3A%2F%2Fconnect.garmin.com' \
                        '&service=https%3A%2F%2Fconnect.garmin.com&source=https%3A%2F%2Fsso.garmin.com%2Fsso%2Fsignin'

    browser = webdriver.Chrome()
    browser.get(better_signin_url)
    browser.find_element(By.ID, 'username').send_keys(os.getenv('GARMIN_SIGNIN_EMAIL'))
    password = browser.find_element(By.ID, 'password')
    password.send_keys(os.getenv('GARMIN_SIGNIN_PASSWORD'))
    password.submit()

    daily_data = get_daily_stats(base_url, browser, start_date, end_date, metric_ids, logger)
    activity_data = get_garmin_activities(base_url, browser, start_date, end_date, logger)

    browser.quit()
    display.stop()

    return daily_data, activity_data


if __name__ == '__main__':
    load_dotenv()
    log_file = Path.home() / '.logs' / 'garmin_extract.log'
    log_file.parent.mkdir(exist_ok=True)
    file_logger = razator_utils.log.get_file_logger('garmin_extract', log_file, 'INFO')
    # noinspection PyBroadException
    try:
        if not os.getenv('GARMIN_SIGNIN_EMAIL'):
            raise KeyError('Please make sure GARMIN_SIGNIN_EMAIL is set in the environment variables')
        if not os.getenv('GARMIN_SIGNIN_PASSWORD'):
            raise KeyError('Please make sure GARMIN_SIGNIN_PASSWORD is set in the environment variables')
        if not os.getenv('GARMIN_DATABASE_PATH'):
            raise KeyError('Please make sure GARMIN_DATABASE_PATH is set in the environment variables')
        default_date = dt.date.today() - dt.timedelta(days=1)
        arg_parser = argparse.ArgumentParser(prog='garmin_export', description='Scrape my garmin stats')
        arg_parser.add_argument('-f', '--from_date', default=default_date,  type=dt.date.fromisoformat,
                                help='Start date (in iso 8601 format) for the stats (default yesterday)')
        arg_parser.add_argument('-e', '--end_date', default=default_date, type=dt.date.fromisoformat,
                                help='End date (in iso 8601 format) for the stats (default yesterday)')
        arg_parser.add_argument('-i', '--metric_ids', nargs='+', help='The metric ids to be pulled')
        arg_parser.add_argument('-d', '--show_display', action='store_true', help='Show the display')
        args = arg_parser.parse_args()

        file_logger.info('Starting the extract of Garmin stats')

        daily_stats, activities = get_garmin_stats(logger=file_logger, start_date=args.from_date,
                                                   end_date=args.end_date, metric_ids=args.metric_ids,
                                                   show_display=args.show_display)

        session = init_db(os.getenv('GARMIN_DATABASE_PATH'))
        for day_stat in daily_stats:
            if (day_row := session.query(GarminStat).filter_by(date=day_stat['date'])).first():
                day_row.update(day_stat)
            else:
                session.add(GarminStat(**day_stat))
        for activity in activities:
            if (activity_row := session.query(Activity).filter_by(activity_id=activity['activity_id'])).first():
                activity_row.update(activity)
            else:
                session.add(Activity(**activity))
        session.commit()
        session.close()
    except Exception:
        file_logger.exception('Garmin extract failed')
        sys.exit(1)
    file_logger.info('Finished extract')
