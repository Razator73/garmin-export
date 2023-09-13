FROM python:3.11

RUN pip install --upgrade pip setuptools pipenv
RUN mkdir /project
WORKDIR /project

COPY ./Pipfile.lock .
COPY ./Pipfile .

RUN pipenv install --dev
