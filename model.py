from sqlalchemy import Column, Integer, String, create_engine, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class GarminStat(Base):
    __tablename__ = 'garmin_stats'
    date = Column(Date, primary_key=True)
    day_of_week = Column(String(9), nullable=False)
    wellness_active_calories = Column(Integer, nullable=False)
    wellness_bmr_calories = Column(Integer, nullable=False)
    food_calories_remaining = Column(Integer, nullable=False)
    wellness_total_calories = Column(Integer, nullable=False)
    total_steps = Column(Integer, nullable=False)
    step_goal = Column(Integer, nullable=False)
    wellness_total_distance = Column(Integer, nullable=False)
    wellness_average_steps = Column(Integer, nullable=False)
    common_total_calories = Column(Integer, nullable=False)
    common_active_calories = Column(Integer, nullable=False)
    common_total_distance = Column(Integer, nullable=False)
    wellness_moderate_intensity_minutes = Column(Integer, nullable=False)
    wellness_vigorous_intensity_minutes = Column(Integer, nullable=False)
    wellness_floors_ascended = Column(Integer, nullable=False)
    wellness_floors_descended = Column(Integer, nullable=False)
    wellness_user_intensity_minutes_goal = Column(Integer, nullable=False)
    wellness_user_floors_ascended_goal = Column(Integer, nullable=False)
    wellness_min_heart_rate = Column(Integer, nullable=False)
    wellness_max_heart_rate = Column(Integer, nullable=False)
    wellness_resting_heart_rate = Column(Integer, nullable=False)
    wellness_average_stress = Column(Integer, nullable=False)
    wellness_max_stress = Column(Integer, nullable=False)
    wellness_min_avg_heart_rate = Column(Integer, nullable=False)
    wellness_max_avg_heart_rate = Column(Integer, nullable=False)
    wellness_bodybattery_charged = Column(Integer, nullable=False)
    wellness_bodybattery_drained = Column(Integer, nullable=False)
    wellness_abnormalhr_alerts_count = Column(Integer, nullable=False)


def init_db(db_path):
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)

    db_session = sessionmaker(bind=engine)
    return db_session()
