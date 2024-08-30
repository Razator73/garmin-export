import datetime as dt
import os
from pathlib import Path

import pygsheets
from dotenv import load_dotenv
from sqlalchemy import func

from model import Activity, WeighIn, init_db


def average(num_list):
    return sum(num_list) / len(num_list)


def get_activities(types):
    return session.query(Activity)\
        .filter(func.date(Activity.start_time_local) == row_date)\
        .filter(Activity.activity_type_type_id.in_(types))\
        .all()


load_dotenv()
cred_file = Path.home() / '.creds' / 'gdrive.json'
gc = pygsheets.authorize(service_file=cred_file)
weight_sheet = gc.open('Daily Weigh-In').worksheet_by_title('daily_data')
session = init_db(os.getenv('GARMIN_DATABASE_PATH'))

# put in weights
cells = weight_sheet.range(f'A2:D{weight_sheet.rows - 1}')
for row in cells:
    if row[1].value:
        continue
    row_date = dt.datetime.strptime(row[0].value, '%m/%d/%Y').date()
    print(f'Updating {row_date}...')
    run_acts = get_activities([1, 18])
    if run_acts:
        distance = round(sum(act.distance_miles for act in run_acts), 2)
        row[3].set_value(distance)
    ulti_acts = get_activities([213])
    if ulti_acts:
        distance = round(sum(act.distance_miles for act in ulti_acts), 2)
        row[5].set_value(distance)
    weights = session.query(WeighIn).filter_by(calendar_date=row_date).all()
    if weights:
        weight = round(average([w.weight_lbs for w in weights]), 1)
        row[1].set_value(weight)
session.close()
print('done')

start_date = dt.date(2017, 1, 13)
today = dt.date.today()
cells = weight_sheet.range(f'A2:A{weight_sheet.rows - 1}')
running_by_day = session.query(
    func.date(Activity.start_time_local),
    func.sum(Activity.distance)
)\
    .filter(Activity.activity_type_type_id.in_([1, 18]))\
    .filter(Activity.start_time_local >= '2017-01-13')\
    .group_by(func.date(Activity.start_time_local))\
    .all()
ulti_by_day = session.query(
    func.date(Activity.start_time_local),
    func.sum(Activity.distance)
)\
    .filter_by(activity_type_type_id=213)\
    .filter(Activity.start_time_local >= '2017-01-13')\
    .group_by(func.date(Activity.start_time_local))\
    .all()
running_by_day = {dt.date.fromisoformat(r[0]): round(r[1] * 0.000621371, 2) for r in running_by_day}
ulti_by_day = {dt.date.fromisoformat(r[0]): round(r[1] * 0.000621371, 2) for r in ulti_by_day}
distance_values = []
for row in cells:
    row_date = dt.datetime.strptime(row[0].value, '%m/%d/%Y').date()
    distance_values.append([running_by_day.get(row_date), ulti_by_day.get(row_date)])
weight_sheet.update_values(f'D2:E{weight_sheet.rows - 1}', distance_values)
