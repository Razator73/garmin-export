#!/usr/bin/env pipenv-shebang
import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import razator_utils
import undetected_chromedriver as uc
from dotenv import load_dotenv
from garminconnect import Garmin
from pyvirtualdisplay import Display
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
            element = driver.find_element(By.CSS_SELECTOR, css_selector)
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


def update_activity(act_id, act_name, type_id, browser, base_url, replace_tuple=None,
                    logger=razator_utils.log.get_stout_logger('garmin_activities')):
    """
    Update the activity on Garmin Connect with the new activity type

    :param act_id: ID of Activity to be edited (int | str)
    :param act_name: Name of Activity to be edited (str)
    :param type_id: Type ID to update (int)
    :param browser: Selenium browser object (WebDriver)
    :param base_url: Base URL for Garmin Connect (str)
    :param replace_tuple: Tuple of (old_string, new_string) (tuple)
    :param logger: Logger object (logging.Logger)

    :return: None
    """
    act_url = f"{base_url}/modern/activity/{act_id}"
    browser.get(act_url)
    logger.info(f"\tUpdating activity `{act_name}` at {act_url}")
    time.sleep(10)
    if replace_tuple:
        interact_with_element('[class="inline-edit-trigger modal-trigger"]', browser)
        interact_with_element('[class="inline-edit-editable-text page-title-overflow"]', browser, action='send_keys',
                              value=act_name.replace(replace_tuple[0], replace_tuple[1]))
        interact_with_element('[class="inline-edit-save icon-checkmark"]', browser)
    interact_with_element('[class="dropdown-toggle active"]', browser)
    interact_with_element(f'[data-value="{type_id}"]', browser)
    try:
        interact_with_element('[class="btn btn-primary js-saveBtn "]', browser, 3)
    except TimeoutError:
        pass


def update_activities(acts_to_update, update_to_type_id, show_display,
                      logger=razator_utils.log.get_stout_logger('garmin_activities', 'INFO')):
    """
    Updates the disc golf activities aren't listed as such

    :param acts_to_update: list of activities to update (list)
    :param update_to_type_id: the id of the type the activity should be (int)
    :param show_display: whether the virtual display should be shown (boolean)
    :param logger: Logger object (logging.Logger)

    :return: None
    """
    logger.info(f'Updating {len(acts_to_update)} activities...')
    display = Display(visible=show_display)
    display.start()

    base_url = 'https://connect.garmin.com'
    better_signin_url = 'https://sso.garmin.com/sso/signin?webhost=https%3A%2F%2Fconnect.garmin.com' \
                        '&service=https%3A%2F%2Fconnect.garmin.com&source=https%3A%2F%2Fsso.garmin.com%2Fsso%2Fsignin'

    browser = uc.Chrome(subprocess=True)
    browser.get(better_signin_url)
    browser.find_element(By.ID, 'username').send_keys(os.getenv('GARMIN_SIGNIN_EMAIL'))
    password = browser.find_element(By.ID, 'password')
    password.send_keys(os.getenv('GARMIN_SIGNIN_PASSWORD'))
    password.submit()

    try:
        for act in acts_to_update:
            try:
                act_id = act['activity_id']
                act_name = act['activity_name']
            except TypeError:
                act_id = act.activity_id
                act_name = act.activity_name
            update_activity(act_id, act_name, update_to_type_id, browser, base_url, logger=logger)
    except Exception:
        browser.quit()
        display.stop()
        raise
    browser.quit()
    display.stop()


def get_daily_stats(api, start_date, end_date, metric_ids,
                    logger=razator_utils.log.get_stout_logger('garmin_daily_stats')):
    """
    Get the daily stats from garmin

    :param api: garmin API Class (Garmin)
    :param start_date: Start date for activities (datetime.date)
    :param end_date: End date for activities (datetime.date)
    :param metric_ids: Metric IDs to pull (dict {"id": "name"})
    :param logger: Logger object (logging.Logger)

    :return: garmin_data: List of daily stats pulled from garmin (list of dicts)
    """
    start_date = max(start_date, dt.date(2017, 9, 5))

    day_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    column_mapping = {
        'wellness_active_calories': 'wellnessActiveKilocalories',
        'wellness_bmr_calories': 'bmrKilocalories',
        'food_calories_remaining': 'remainingKilocalories',
        'wellness_total_calories': 'wellnessKilocalories',
        'total_steps': 'totalSteps',
        'step_goal': 'dailyStepGoal',
        'wellness_total_distance': 'wellnessDistanceMeters',
        'wellness_average_steps': '',
        'common_total_calories': 'totalKilocalories',
        'common_active_calories': 'activeKilocalories',
        'common_total_distance': 'totalDistanceMeters',
        'wellness_moderate_intensity_minutes': 'moderateIntensityMinutes',
        'wellness_vigorous_intensity_minutes': 'vigorousIntensityMinutes',
        'wellness_floors_ascended': 'floorsAscended',
        'wellness_floors_descended': 'floorsDescended',
        'wellness_user_intensity_minutes_goal': 'intensityMinutesGoal',
        'wellness_user_floors_ascended_goal': 'userFloorsAscendedGoal',
        'wellness_min_heart_rate': 'minHeartRate',
        'wellness_max_heart_rate': 'maxHeartRate',
        'wellness_resting_heart_rate': 'restingHeartRate',
        'wellness_average_stress': 'averageStressLevel',
        'wellness_max_stress': 'maxStressLevel',
        'wellness_min_avg_heart_rate': 'minAvgHeartRate',
        'wellness_max_avg_heart_rate': 'maxAvgHeartRate',
        'wellness_bodybattery_charged': 'bodyBatteryChargedValue',
        'wellness_bodybattery_drained': 'bodyBatteryDrainedValue',
        'wellness_abnormalhr_alerts_count': 'abnormalHeartRateAlertsCount'
    }

    # TODO: go through and get new stats model
    garmin_data = []
    for i in range((end_date - start_date).days + 1):
        check_day = start_date + dt.timedelta(days=i)
        day_data = {'date': check_day, 'day_of_week': day_of_week[check_day.weekday()],
                    'wellness_average_steps': 0}
        day_stats = api.get_stats(check_day.isoformat())
        day_data = {**day_data, **{k: day_stats[v] for k, v in column_mapping.items() if v}}
        abnormal_hr_counts = day_stats['abnormalHeartRateAlertsCount']
        day_data['wellness_abnormalhr_alerts_count'] = abnormal_hr_counts if abnormal_hr_counts else 0
        garmin_data.append(day_data)

    return garmin_data


def get_garmin_activities(api, start_date, end_date, show_display,
                          logger=razator_utils.log.get_stout_logger('garmin_activities')):
    """
    Get the activities from garmin

    :param api: garmin API Class (Garmin)
    :param logger: Logger object (logging.Logger)
    :param start_date: Start date for activities (datetime.date)
    :param end_date: End date for activities (datetime.date)
    :param show_display: whether the virtual display should be shown (boolean)

    :return: activities: List of activities pulled from garmin (list of dicts)
    """
    start_date = max(start_date, dt.date(2013, 9, 1))
    acts = api.get_activities_by_date(start_date.isoformat(), end_date.isoformat())

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
        if 'activity_type_sort_order' in flat_act.keys():
            del flat_act['activity_type_sort_order']
        flat_activities.append(flat_act)
    # dg_acts_to_update = [flat_act for flat_act in flat_activities
    #                      if flat_act['activity_type_type_id'] == 4 and 'Disc Golf' in flat_act['activity_name']]
    # ultimate_acts = [flat_act for flat_act in flat_activities
    #                  if flat_act['activity_type_type_id'] == 11 and 'Frisbee' in flat_act['activity_name']]
    # if dg_acts_to_update:
    #     update_activities(dg_acts_to_update, 205, show_display, logger=logger)
    #     for dg_act in dg_acts_to_update:
    #         dg_act['activity_type_type_id'] = 205
    #         dg_act['activity_type_type_key'] = 'disc_golf'
    #         dg_act['activity_type_parent_type_id'] = 4
    # if ultimate_acts:
    #     update_activities(ultimate_acts, 213, show_display, logger=logger)
    #     for ulti_act in ultimate_acts:
    #         ulti_act['activity_type_type_id'] = 213
    #         ulti_act['activity_type_type_key'] = 'ultimate_disc'
    #         ulti_act['activity_type_parent_type_id'] = 206
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
    api = Garmin(os.getenv('GARMIN_SIGNIN_EMAIL'), os.getenv('GARMIN_SIGNIN_PASSWORD'))
    # TODO: set resume using garth
    api.login()

    daily_data = get_daily_stats(api, start_date, end_date, metric_ids, logger)
    activity_data = get_garmin_activities(api, start_date, end_date, show_display, logger)

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
