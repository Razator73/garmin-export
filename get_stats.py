#!/usr/bin/env pipenv-shebang
import argparse
import datetime as dt
import os
import pytz
import sys
from pathlib import Path

import razator_utils
from dotenv import load_dotenv
from garminconnect import Garmin

from model import GarminStat, Activity, WeighIn, init_db


def get_daily_stats(api, start_date, end_date):
    """
    Get the daily stats from garmin

    :param api: garmin API Class (Garmin)
    :param start_date: Start date for activities (datetime.date)
    :param end_date: End date for activities (datetime.date)

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
        day_data = {**day_data, **{k: day_stats[v] if day_stats[v] else 0
                                   for k, v in column_mapping.items() if v}}
        abnormal_hr_counts = day_stats['abnormalHeartRateAlertsCount']
        day_data['wellness_abnormalhr_alerts_count'] = abnormal_hr_counts if abnormal_hr_counts else 0
        garmin_data.append(day_data)

    return garmin_data


def get_garmin_activities(api, start_date, end_date,
                          logger=razator_utils.log.get_stout_logger('garmin_activities')):
    """
    Get the activities from garmin

    :param api: garmin API Class (Garmin)
    :param start_date: Start date for activities (datetime.date)
    :param end_date: End date for activities (datetime.date)
    :param logger: Logger object (logging.Logger)

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
    ultimate_acts = [flat_act for flat_act in flat_activities
                     if flat_act['activity_type_type_id'] == 11 and 'Frisbee' in flat_act['activity_name']]
    for ulti_act in ultimate_acts:
        api.set_activity_type(
            activity_id = ulti_act['activity_id'],
            type_id = 213,
            type_key='ultimate_disc',
            parent_type_id=206
        )
        ulti_act['activity_type_type_id'] = 213
        ulti_act['activity_type_type_key'] = 'ultimate_disc'
        ulti_act['activity_type_parent_type_id'] = 206
        logger.info(f'Updated activity {ulti_act["activity_id"]} to ultimate')
    return flat_activities


def get_weigh_ins(api, start_date, end_date,
                  logger=razator_utils.log.get_stout_logger('garmin_activities')):
    """
    Get the activities from garmin

    :param api: garmin API Class (Garmin)
    :param logger: Logger object (logging.Logger)
    :param start_date: Start date for activities (datetime.date)
    :param end_date: End date for activities (datetime.date)

    :return: activities: List of weigh-ins pulled from garmin (list of dicts)
    """
    logger.info('Getting weigh-ins')
    start_date = max(start_date, dt.date(2017, 1, 13))
    raw_weigh_ins = api.get_weigh_ins(start_date.isoformat(), end_date.isoformat())
    weigh_ins_list = []
    for weight_day in raw_weigh_ins['dailyWeightSummaries']:
        weigh_ins_list += weight_day['allWeightMetrics']
    logger.info(f'Found {len(weigh_ins_list)} weigh-ins')
    weigh_ins = []
    for weigh_in in weigh_ins_list:
        if timestamp_gmt := weigh_in['timestampGMT']:
            timestamp_utc = dt.datetime.utcfromtimestamp(timestamp_gmt / 1000)
        else:
            timestamp_utc = dt.datetime.utcfromtimestamp(weigh_in['date'] / 1000)
        timestamp_utc = pytz.utc.localize(timestamp_utc)
        weigh_ins.append({
            "weigh_in_id": weigh_in['samplePk'],
            "weight_timestamp_utc": timestamp_utc,
            "weight_timestamp_mountain": timestamp_utc.astimezone(pytz.timezone('America/Denver')),
            "calendar_date": dt.date.fromisoformat(weigh_in['calendarDate']),
            "weight_kg": round(weigh_in['weight'] / 1000, 2),
            "weight_lbs": round(weigh_in['weight'] * 0.00220462, 1)
        })
    return weigh_ins


def get_garmin_stats(start_date, end_date,
                     logger=razator_utils.log.get_stout_logger('garmin_api')):
    """
    Get the stats from garmin

    :param start_date: Start date for stats (datetime.date)
    :param end_date: End date for stats (datetime.date)
    :param logger: Logger object (logging.Logger)

    :return: daily_data, activity_data: Daily and activity data from garmin (each a list of dicts)
    """
    start_date, end_date = (end_date, start_date) if end_date < start_date else (start_date, end_date)
    api = Garmin()
    api.login(tokenstore='~/.garminconnect')

    daily_data = get_daily_stats(api, start_date, end_date)
    activity_data = get_garmin_activities(api, start_date, end_date, logger)
    weigh_ins = get_weigh_ins(api, start_date, end_date, logger)

    return daily_data, activity_data, weigh_ins


if __name__ == '__main__':
    load_dotenv()
    # noinspection PyBroadException
    try:
        if not os.getenv('GARMIN_SIGNIN_EMAIL'):
            raise KeyError('Please make sure GARMIN_SIGNIN_EMAIL is set in the environment variables')
        if not os.getenv('GARMIN_SIGNIN_PASSWORD'):
            raise KeyError('Please make sure GARMIN_SIGNIN_PASSWORD is set in the environment variables')
    except KeyError as e:
        if alert_url := os.getenv('DISCORD_ALERT_URL'):
            razator_utils.discord_message(alert_url, 'Garmin Extract Failed. Please check environment variables')
        raise

    try:
        arg_parser = argparse.ArgumentParser(prog='garmin_export', description='Scrape my garmin stats')
        arg_parser.add_argument('-f', '--from_date', default=dt.date.today() - dt.timedelta(days=1),  type=dt.date.fromisoformat,
                                help='Start date (in iso 8601 format) for the stats (default yesterday)')
        arg_parser.add_argument('-e', '--end_date', default=dt.date.today(),
                                type=dt.date.fromisoformat,
                                help='End date (in iso 8601 format) for the stats (default yesterday)')
        arg_parser.add_argument('-v', '--stout-output', action='store_true', help='Export logging to terminal')
        args = arg_parser.parse_args()

        if args.stout_output:
            file_logger = razator_utils.log.get_stout_logger('garmin_extract', 'INFO')
        else:
            log_file = Path.home() / 'logs' / 'garmin_extract.log'
            log_file.parent.mkdir(exist_ok=True)
            file_logger = razator_utils.log.get_file_logger('garmin_extract', log_file, 'INFO')
    except Exception:
        if alert_url := os.getenv('DISCORD_ALERT_URL'):
            razator_utils.discord_message(alert_url, 'Garmin Extract Failed. Please check arguments')
        raise

    try:
        file_logger.info('Starting the extract of Garmin stats')

        daily_stats, activities, weights = get_garmin_stats(
            logger=file_logger, start_date=args.from_date, end_date=args.end_date
        )

        session = init_db()
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
        for weight in weights:
            if (weight_row := session.query(WeighIn).filter_by(weigh_in_id=str(weight['weigh_in_id']))).first():
                weight_row.update(weight)
            else:
                session.add(WeighIn(**weight))
        session.commit()
        session.close()
    except Exception:
        file_logger.exception('Garmin extract failed')
        if alert_url := os.getenv('DISCORD_ALERT_URL'):
            razator_utils.discord_message(alert_url, 'Garmin Extract Failed. Check logs for details.')
        sys.exit(1)
    file_logger.info('Finished extract')
